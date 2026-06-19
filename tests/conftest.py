"""Shared test guards: keep guard-autostart side effects (launchctl, LaunchAgents) out of tests."""

from __future__ import annotations

import importlib

import pytest

from holo_desktop.cli import bootstrap
from holo_desktop.killswitch.autostart import AutostartResult

# `holo_desktop.cli` re-exports the `install` command function under that name, shadowing the
# submodule on the package, so reach the module object directly to patch its imported symbol.
install_mod = importlib.import_module("holo_desktop.cli.install")


@pytest.fixture(autouse=True)
def _no_guard_autostart_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the headless guard hook and `holo install`'s autostart so no test touches the OS.

    The killswitch.autostart unit tests call its functions directly and are unaffected.
    """
    monkeypatch.setattr(bootstrap, "ensure_guard_running", lambda: None)
    monkeypatch.setattr(
        install_mod,
        "ensure_autostart",
        lambda holo_cmd: (AutostartResult.SKIPPED, "(autostart disabled in tests)"),
    )
