"""Shared test guards: keep real credentials, runtime state, and guard autostart out of tests."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from hai_agents_common import credentials
from hai_agents_local.runtime.runtime import BASE_URL_ENV, BINARY_PATH_ENV
from hai_agents_local.runtime.state import CACHE_DIR_ENV

from holo_desktop import desktop_lock
from holo_desktop.cli import bootstrap
from holo_desktop.killswitch.autostart import AutostartResult
from holo_desktop.task import BASE_URL_ENV as SELF_HOSTED_URL_ENV
from holo_desktop.task import MODEL_ENV

# `holo_desktop.cli` re-exports the `install` command function under that name, shadowing the
# submodule on the package, so reach the module object directly to patch its imported symbol.
install_mod = importlib.import_module("holo_desktop.cli.install")


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads the developer's API key, runtime, or desktop lock."""
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path / "agent-runtime"))
    for name in (BINARY_PATH_ENV, BASE_URL_ENV, SELF_HOSTED_URL_ENV, MODEL_ENV, "HAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "GLOBAL_ENV_PATH", tmp_path / "hai" / ".env")
    monkeypatch.setattr(bootstrap, "LEGACY_ENV_PATH", tmp_path / "holo" / ".env")
    monkeypatch.setattr(desktop_lock, "LOCK_PATH", tmp_path / "desktop.lock")


@pytest.fixture(autouse=True)
def _no_guard_autostart_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the headless guard hook and `holo install`'s autostart so no test touches the OS."""
    monkeypatch.setattr(bootstrap, "ensure_guard_running", lambda: None)
    monkeypatch.setattr(
        install_mod,
        "ensure_autostart",
        lambda holo_cmd: (AutostartResult.SKIPPED, "(autostart disabled in tests)"),
    )
