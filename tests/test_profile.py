"""Behavioural tests for `cli.profile.load_profile` failure visibility.

A corrupt or malformed `~/.holo/profile.json` must not fail silently: the
caller still gets None (whoami-style flows degrade), but a warning names the
file so the confusing downstream behaviour is explainable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from holo_desktop.cli import profile


@pytest.fixture()
def profile_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "profile.json"
    monkeypatch.setattr(profile, "PROFILE_PATH", path)
    return path


def test_missing_profile_is_quietly_none(profile_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert profile.load_profile() is None
    assert not caplog.records, "no profile yet is the normal logged-out state"


def test_corrupt_json_returns_none_with_warning(profile_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    profile_path.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert profile.load_profile() is None
    warning = next(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert str(profile_path) in warning
    assert "holo login" in warning


def test_missing_required_key_returns_none_with_warning(profile_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    profile_path.write_text(json.dumps({"email": "a@b.c"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert profile.load_profile() is None
    warning = next(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert str(profile_path) in warning


def test_valid_profile_round_trips(profile_path: Path) -> None:
    profile.save_profile(profile.Profile(email="a@b.c", org_id="org", key_id="key", key_label="label"))
    loaded = profile.load_profile()
    assert loaded is not None
    assert loaded.email == "a@b.c"
