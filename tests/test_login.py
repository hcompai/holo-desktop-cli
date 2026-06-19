"""Behavioural tests for `holo login`'s validate-on-mint policy.

`_verify_model_access` decides, from the gateway probe's verdict, whether sign-in
exits: exit on an `unauthorized` key, pass an `entitled` (or `unverifiable`) one,
and skip the probe entirely in self-hosted mode. Minting revokes the prior portal
key before the gate runs, so the freshly minted key must be persisted first —
exiting must never leave `~/.holo/.env` pointing at the now-dead secret.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import httpx
import pytest
from rich.console import Console

from holo_desktop.cli import bootstrap
from holo_desktop.cli import profile as profile_mod
from holo_desktop.cli.profile import Profile
from holo_desktop.settings import load_holo_settings

# `holo_desktop.cli.__init__` re-exports the `login` command under the submodule
# name; go through importlib to reach the module's helpers.
login = importlib.import_module("holo_desktop.cli.login")


def _console() -> Console:
    return Console(stderr=True)


def _verify_model_access(key: str) -> None:
    login._verify_model_access(key, _console(), settings=load_holo_settings())


def test_entitled_key_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.setattr(login, "probe_model_access", lambda *_: "entitled")
    _verify_model_access("live-key")  # returns normally


def test_unauthorized_key_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.setattr(login, "probe_model_access", lambda *_: "unauthorized")
    with pytest.raises(SystemExit) as excinfo:
        _verify_model_access("dead-key")
    assert excinfo.value.code == 1


def test_unverifiable_key_does_not_block_signin(monkeypatch: pytest.MonkeyPatch) -> None:
    # A flaky/unreachable gateway must not be reported as a credential failure.
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.setattr(login, "probe_model_access", lambda *_: "unverifiable")
    _verify_model_access("maybe-key")  # returns normally


def test_self_hosted_skips_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://127.0.0.1:8000/v1")

    def _must_not_run(*_: object) -> str:
        raise AssertionError("probe must not run in self-hosted mode")

    monkeypatch.setattr(login, "probe_model_access", _must_not_run)
    _verify_model_access("any-key")  # returns normally, no probe


def test_login_loads_dotenv_so_gateway_override_is_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A HAI_BASE_URL stored only in ~/.holo/.env must reach the gateway probe: login has to
    # load the layered env. Asserted on the already-signed-in early return (no OAuth needed).
    for var in ("HAI_API_KEY", "HAI_BASE_URL", "HAI_AGENT_RUNTIME_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('HAI_API_KEY="k"\nHAI_BASE_URL="https://eu.example/v1/models"\n', encoding="utf-8")
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", env_file)
    monkeypatch.setattr(login, "load_profile", lambda: Profile(email="e", org_id="o", key_id="i", key_label="l"))

    login.login(force=False)

    assert os.environ.get("HAI_BASE_URL") == "https://eu.example/v1/models"


def _portal_transport() -> httpx.MockTransport:
    """A portal that signs in, lets the prior key be revoked, and mints `fresh-key`."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/api/auth/desktop/exchange"):
            return httpx.Response(200, json={"access_token": "jwt"})
        if request.method == "GET" and path.endswith("/api/auth/me"):
            return httpx.Response(
                200,
                json={
                    "user": {"email": "e@x", "username": "u", "id": "uid"},
                    "org_id": "org1",
                    "organization": {"name": "Org"},
                },
            )
        if request.method == "DELETE" and "/keys/" in path:
            return httpx.Response(200, json={})
        if request.method == "POST" and path.endswith("/keys/"):
            return httpx.Response(200, json={"key": "fresh-key", "id": "newid"})
        raise AssertionError(f"unexpected portal call: {request.method} {path}")

    return httpx.MockTransport(handler)


def test_unauthorized_key_is_persisted_not_stranded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The regression: minting revokes the prior portal key, so if login exits on a no-entitlement
    # gate *before* saving, ~/.holo/.env keeps the dead secret and the user is signed out in
    # practice. The freshly minted key must be on disk even though the gateway denies it.
    for var in ("HAI_API_KEY", "HAI_BASE_URL", "HAI_AGENT_RUNTIME_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(bootstrap, "HOLO_DIR", tmp_path)
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(profile_mod, "HOLO_DIR", tmp_path)
    monkeypatch.setattr(profile_mod, "PROFILE_PATH", tmp_path / "profile.json")

    monkeypatch.setattr(login, "_await_code", lambda *_: ("code", "http://127.0.0.1:0/"))
    monkeypatch.setattr(login, "probe_model_access", lambda *_: "unauthorized")
    # Prior identity in the same org so the fast-revoke path runs against the mock portal.
    prior = Profile(email="e@x", org_id="org1", key_id="prevkey", key_label="l")
    monkeypatch.setattr(login, "load_profile", lambda: prior)

    transport = _portal_transport()
    real_client = httpx.Client
    monkeypatch.setattr(login.httpx, "Client", lambda **kw: real_client(transport=transport, **kw))

    with pytest.raises(SystemExit) as excinfo:
        login.login(force=True)

    assert excinfo.value.code == 1
    assert bootstrap.read_user_env_key() == "fresh-key"
    assert profile_mod.load_profile() == Profile(
        email="e@x",
        org_id="org1",
        key_id="newid",
        key_label=login._key_label(),
        org_name="Org",
    )
