"""`holo doctor` fails only on problems a user must fix, and points at the fix."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from holo_desktop import customization

doctor = importlib.import_module("holo_desktop.cli.doctor")


@pytest.fixture()
def skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skills_dir = tmp_path / "skills"
    (skills_dir / "demo").mkdir(parents=True)
    (skills_dir / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    monkeypatch.setattr(customization, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(doctor, "check_desktop", lambda: doctor.CheckResult("desktop", True, "granted"))
    return skills_dir


def test_signed_in_machine_passes(skills: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")

    doctor.doctor()


def test_missing_login_fails_with_pointer(skills: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        doctor.doctor()

    assert excinfo.value.code == 1
    assert "holo login" in capsys.readouterr().out


def test_self_hosted_model_needs_no_key(skills: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://localhost:8000/v1")

    doctor.doctor()
