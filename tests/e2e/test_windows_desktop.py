from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from .windows_desktop import WindowsDesktopBlocker, WindowsDesktopReadiness, load_windows_desktop_readiness


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "ready": True,
        "blockers": [],
        "os_version": "10.0.26200",
        "architecture": "ARM64",
        "foreground_process": "explorer",
        "foreground_title": "Desktop",
        "explorer_responsive": True,
        "screenshot_path": "desktop-ready.png",
        "processes_path": "processes.json",
        "windows_path": "windows.json",
        "app_probes_path": "app-probes.json",
    }
    payload.update(overrides)
    return payload


def test_ready_desktop_contract_has_no_blockers() -> None:
    readiness = WindowsDesktopReadiness.model_validate(_payload())

    assert readiness.ready is True
    assert readiness.blockers == ()
    assert readiness.explorer_responsive is True


def test_failed_screenshot_is_an_explicit_blocker() -> None:
    readiness = WindowsDesktopReadiness.model_validate(
        _payload(
            ready=False,
            blockers=[WindowsDesktopBlocker.SCREENSHOT_UNAVAILABLE.value],
            screenshot_path=None,
        )
    )

    assert readiness.ready is False
    assert readiness.blockers == (WindowsDesktopBlocker.SCREENSHOT_UNAVAILABLE,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ready": True, "blockers": [WindowsDesktopBlocker.WSL_PROMPT.value]},
        {"ready": False, "blockers": []},
        {"ready": False, "blockers": [WindowsDesktopBlocker.WSL_PROMPT.value], "screenshot_path": None},
        {
            "ready": False,
            "blockers": [WindowsDesktopBlocker.SCREENSHOT_UNAVAILABLE.value],
            "screenshot_path": "desktop-ready.png",
        },
    ],
)
def test_inconsistent_readiness_evidence_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WindowsDesktopReadiness.model_validate(_payload(**overrides))


def test_readiness_loader_rejects_wrong_runner_architecture(tmp_path: Path) -> None:
    path = tmp_path / "windows-desktop-readiness.json"
    path.write_text(json.dumps(_payload(architecture="AMD64")), encoding="utf-8")

    with pytest.raises(ValueError, match="expected 'ARM64', observed 'AMD64'"):
        load_windows_desktop_readiness(path, expected_architecture="ARM64")
