"""Holo's spawn-env bridge into hai-agents local mode.

Ports the runtime_child_env specs from test_launcher.py: DDTrace default-off,
the hosted-gateway default, and the self-hosted rule that a custom
HAI_AGENT_RUNTIME_BASE_URL must never see the portal HAI_API_KEY. Also keeps
the attach guard: explicit CLI config must not be silently ignored by an
already-running runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from holo_desktop.agent_client import sdk_runtime
from holo_desktop.agent_client.sdk_runtime import SpawnConfig, ensure_local_runtime
from holo_desktop.settings import load_holo_settings


class _FakeRuntime:
    base_url = "http://127.0.0.1:18795"
    api_key = "k"
    owned = True


def _capture_spawn(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    def fake_ensure_started(*, port, spawn_env, inherit_env, timeout_s, **_ignored):
        captured["port"] = port
        captured["spawn_env"] = spawn_env
        captured["inherit_env"] = inherit_env
        return _FakeRuntime()

    monkeypatch.setattr(sdk_runtime.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: None))
    monkeypatch.setattr(sdk_runtime.LocalRuntime, "ensure_started", staticmethod(fake_ensure_started))


def test_custom_base_url_strips_portal_key_from_spawn_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "portal-secret")
    captured: dict = {}
    _capture_spawn(monkeypatch, captured)

    ensure_local_runtime(
        SpawnConfig(port=18795, base_url="https://self-hosted.example/v1"),
        settings=load_holo_settings(),
    )

    env = captured["spawn_env"]
    assert env["HAI_AGENT_RUNTIME_BASE_URL"] == "https://self-hosted.example/v1"
    assert "HAI_API_KEY" not in env, "the portal key must never leak to a self-hosted endpoint"
    # Without inherit_env=False the SDK would merge os.environ back in and undo the strip.
    assert captured["inherit_env"] is False


def test_hosted_path_defaults_gateway_and_keeps_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "portal-secret")
    monkeypatch.delenv("HAI_BASE_URL", raising=False)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("DD_TRACE_ENABLED", raising=False)
    captured: dict = {}
    _capture_spawn(monkeypatch, captured)

    ensure_local_runtime(SpawnConfig(port=18795), settings=load_holo_settings())

    env = captured["spawn_env"]
    assert env["HAI_API_KEY"] == "portal-secret"
    assert env["HAI_BASE_URL"] == sdk_runtime.PRODUCTION_GATEWAY_URL
    assert env["DD_TRACE_ENABLED"] == "false"


def test_flags_and_runs_dir_reach_spawn_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    captured: dict = {}
    _capture_spawn(monkeypatch, captured)

    ensure_local_runtime(
        SpawnConfig(port=19001, model="holo-3", fake=True, fast=True, runs_dir=tmp_path / "runs"),
        settings=load_holo_settings(),
    )

    env = captured["spawn_env"]
    assert captured["port"] == 19001
    assert env["HAI_AGENT_RUNTIME_MODEL"] == "holo-3"
    assert env["HAI_AGENT_RUNTIME_FAKE"] == "1"
    assert env["HAI_AGENT_RUNTIME_FAST"] == "1"
    assert env["HAI_AGENT_RUNTIME_RUNS_DIR"] == str(tmp_path / "runs")


def test_attach_with_explicit_flags_refuses_silent_ignore(monkeypatch: pytest.MonkeyPatch) -> None:
    # Preserved ensure_running guard: a running runtime keeps its spawn-time
    # config, so explicit CLI flags must error, never be silently dropped.
    monkeypatch.setattr(
        sdk_runtime.LocalRuntime,
        "attach",
        staticmethod(lambda *, port=None, cache_dir=None: _FakeRuntime()),
    )

    with pytest.raises(RuntimeError, match="silently ignored"):
        ensure_local_runtime(SpawnConfig(port=18795, model="holo-3"), settings=load_holo_settings())


def test_attach_without_flags_reuses_the_running_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _FakeRuntime()
    monkeypatch.setattr(sdk_runtime.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: runtime))

    assert ensure_local_runtime(SpawnConfig(port=18795), settings=load_holo_settings()) is runtime
