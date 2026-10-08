"""`holo login`: a rotated key is the one the next run uses."""

from __future__ import annotations

import importlib
import io
import os
from pathlib import Path

import pytest
from hai_agents_common import credentials

from holo_desktop.cli import bootstrap

login_mod = importlib.import_module("holo_desktop.cli.login")


def test_rotated_key_wins_over_a_legacy_holo_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    bootstrap.LEGACY_ENV_PATH.parent.mkdir(parents=True)
    bootstrap.LEGACY_ENV_PATH.write_text("HAI_API_KEY=revoked\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("fresh\n"))

    login_mod.login(force=True, key=True)
    os.environ.pop("HAI_API_KEY", None)
    bootstrap.load_holo_env()

    assert credentials.current_api_key() == "fresh"
