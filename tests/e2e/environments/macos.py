from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import pytest

from .. import _macos
from .._domain import PreparedTask, TaskCase
from ..tasks import (
    BROWSER_DOWNLOAD_FILE,
    CALCULATOR_CI_SMOKE,
    FINDER_COPY_FILE,
    FINDER_CREATE_FOLDER,
    FINDER_OPEN_FILE_BY_DOUBLE_CLICK,
    FINDER_PROTECTED_FILE,
    FOREGROUND_VISIBLE_EDITOR_WITNESS,
    TEXTEDIT_TYPE_SENTINEL,
)

MACOS_FOREGROUND_TASKS = (
    FOREGROUND_VISIBLE_EDITOR_WITNESS,
    TEXTEDIT_TYPE_SENTINEL,
    FINDER_CREATE_FOLDER,
    FINDER_COPY_FILE,
    FINDER_OPEN_FILE_BY_DOUBLE_CLICK,
    FINDER_PROTECTED_FILE,
    CALCULATOR_CI_SMOKE,
    BROWSER_DOWNLOAD_FILE,
)


class MacOSEnvironmentRunner:
    """Environment runner for live foreground tasks on macOS."""

    environment_id = "macos-foreground"
    task_cases: tuple[TaskCase, ...] = MACOS_FOREGROUND_TASKS

    def supports(self, case: TaskCase) -> bool:
        return case in self.task_cases

    def preflight(self, case: TaskCase) -> None:
        if not self.supports(case):
            pytest.skip(f"{self.environment_id} does not support {case.id}")
        app_name = _required_app_for_case(case)
        if app_name:
            _macos.require_app(app_name)
        if not _macos.screencapture_available():
            pytest.skip(
                "macOS screencapture is unavailable. Grant Screen Recording to the terminal/Codex host "
                "before running foreground live tests."
            )

    def prepare(self, case: TaskCase, workspace: Path) -> PreparedTask:
        prepared = case.prepare(workspace)
        _prepare_foreground_state(prepared)
        return prepared

    def cleanup(self, prepared: PreparedTask | None) -> None:
        if prepared is not None:
            with suppress(Exception):
                prepared.clean_up()


def _required_app_for_case(case: TaskCase) -> str | None:
    match case.app_family:
        case "text-editor":
            return "TextEdit"
        case "file-manager":
            return "Finder"
        case "calculator":
            return "Calculator"
        case "image-viewer":
            return "Preview"
        case "notes":
            return "Notes"
        case "browser":
            return "Safari"
        case _:
            return None


def _prepare_foreground_state(prepared: PreparedTask) -> None:
    if prepared.case.id == "textedit_type_sentinel":
        target_path = prepared.metadata.get("target_path")
        if isinstance(target_path, str):
            _macos.open_file_in_textedit(Path(target_path))
            _macos.ensure_frontmost_app("TextEdit")
    elif prepared.case.id in {"finder_create_folder", "finder_open_file_by_double_click"}:
        _macos.open_finder_desktop()
        _macos.ensure_frontmost_app("Finder")
