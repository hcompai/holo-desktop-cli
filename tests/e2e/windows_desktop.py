from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WindowsDesktopBlocker(StrEnum):
    """A condition that makes a hosted Windows desktop unsafe for a live task."""

    PRIVACY_OOBE = "privacy_oobe"
    EDGE_FIRST_RUN = "edge_first_run"
    WSL_PROMPT = "wsl_prompt"
    EXPLORER_MISSING = "explorer_missing"
    EXPLORER_UNRESPONSIVE = "explorer_unresponsive"
    SCREENSHOT_UNAVAILABLE = "screenshot_unavailable"
    UNEXPECTED_FOREGROUND_APP = "unexpected_foreground_app"
    APP_PROBE_FAILED = "app_probe_failed"
    ARCHITECTURE_MISMATCH = "architecture_mismatch"
    NORMALIZATION_FAILED = "normalization_failed"
    DESKTOP_ORACLE_UNAVAILABLE = "desktop_oracle_unavailable"


class WindowsDesktopReadiness(BaseModel):
    """Versioned evidence emitted before a Windows live E2E task starts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(description="Readiness artifact schema version.", examples=[1])
    ready: bool = Field(description="Whether the desktop satisfies every readiness invariant.", examples=[True])
    blockers: tuple[WindowsDesktopBlocker, ...] = Field(
        description="Exact conditions preventing model execution.",
        examples=[[]],
    )
    os_version: str = Field(description="Windows version reported by the runner.", examples=["10.0.26200"])
    architecture: str = Field(description="Native process architecture.", examples=["ARM64"])
    foreground_process: str | None = Field(
        description="Foreground process name after normalization.",
        examples=["explorer"],
    )
    foreground_title: str | None = Field(
        description="Foreground top-level window title after normalization.",
        examples=["Desktop"],
    )
    explorer_responsive: bool = Field(
        description="Whether a visible Explorer shell window exists and is responsive.",
        examples=[True],
    )
    screenshot_path: str | None = Field(
        description="Readiness screenshot path, or null when screenshot capture itself failed.",
        examples=["desktop-ready.png"],
    )
    processes_path: str = Field(
        description="Path to the bounded process snapshot.",
        examples=["processes.json"],
    )
    windows_path: str = Field(
        description="Path to the top-level window snapshot.",
        examples=["windows.json"],
    )
    app_probes_path: str = Field(
        description="Path to the native application probe results.",
        examples=["app-probes.json"],
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> WindowsDesktopReadiness:
        if self.ready == bool(self.blockers):
            raise ValueError("ready must be true exactly when blockers is empty")
        if self.screenshot_path is None and WindowsDesktopBlocker.SCREENSHOT_UNAVAILABLE not in self.blockers:
            raise ValueError("screenshot_path may be null only for screenshot_unavailable")
        if self.screenshot_path is not None and WindowsDesktopBlocker.SCREENSHOT_UNAVAILABLE in self.blockers:
            raise ValueError("screenshot_unavailable requires a null screenshot_path")
        return self

    def require_architecture(self, expected_architecture: str) -> WindowsDesktopReadiness:
        if self.architecture.casefold() != expected_architecture.casefold():
            raise ValueError(
                f"Windows desktop architecture mismatch: expected {expected_architecture!r}, "
                f"observed {self.architecture!r}"
            )
        return self


def load_windows_desktop_readiness(
    path: Path,
    *,
    expected_architecture: str,
) -> WindowsDesktopReadiness:
    payload = json.loads(path.read_text(encoding="utf-8"))
    readiness = WindowsDesktopReadiness.model_validate(payload)
    return readiness.require_architecture(expected_architecture)
