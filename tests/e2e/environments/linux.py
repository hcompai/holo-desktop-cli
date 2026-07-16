from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from .. import _linux, _preserve
from .._domain import PreparedTask, TaskCase
from ..evaluators.finder import CopiedFileEvaluator, FolderExistsEvaluator, ProtectedFileEvaluator
from ..evaluators.textedit import FileContainsEvaluator
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
from ..tasks.browser import prepare_browser_download_task

LINUX_FOREGROUND_TASKS = (
    FOREGROUND_VISIBLE_EDITOR_WITNESS,
    TEXTEDIT_TYPE_SENTINEL,
    FINDER_CREATE_FOLDER,
    FINDER_COPY_FILE,
    FINDER_OPEN_FILE_BY_DOUBLE_CLICK,
    FINDER_PROTECTED_FILE,
    CALCULATOR_CI_SMOKE,
    BROWSER_DOWNLOAD_FILE,
)


class LinuxEnvironmentRunner:
    """Environment runner for the hosted Linux X11 foreground desktop."""

    environment_id = "linux-foreground"
    task_cases: tuple[TaskCase, ...] = LINUX_FOREGROUND_TASKS

    def supports(self, case: TaskCase) -> bool:
        return case in self.task_cases

    def preflight(self, case: TaskCase) -> None:
        if not self.supports(case):
            raise ValueError(f"{self.environment_id} does not support {case.id}")
        _linux.require_desktop()
        command = {
            "text-editor": "mousepad",
            "file-manager": "thunar",
            "calculator": "kcalc",
            "browser": "google-chrome",
        }.get(case.app_family)
        if command is not None:
            _linux.require_app(command)
        _linux.cleanup_test_apps()

    def prepare(self, case: TaskCase, workspace: Path) -> PreparedTask:
        if case == FOREGROUND_VISIBLE_EDITOR_WITNESS:
            return self._prepare_foreground_visible_editor_witness(case, workspace)
        if case == TEXTEDIT_TYPE_SENTINEL:
            return self._prepare_textedit_type_sentinel(case, workspace)
        if case == FINDER_CREATE_FOLDER:
            return self._prepare_finder_create_folder(case, workspace)
        if case == FINDER_COPY_FILE:
            return self._prepare_finder_copy_file(case, workspace)
        if case == FINDER_OPEN_FILE_BY_DOUBLE_CLICK:
            return self._prepare_finder_open_file_by_double_click(case, workspace)
        if case == FINDER_PROTECTED_FILE:
            return self._prepare_finder_protected_file(case, workspace)
        if case == CALCULATOR_CI_SMOKE:
            return self._prepare_calculator_ci_smoke(case, workspace)
        if case == BROWSER_DOWNLOAD_FILE:
            return self._prepare_browser_download_file(case, workspace)
        raise ValueError(f"unsupported task case for {self.environment_id}: {case.id}")

    def cleanup(self, prepared: PreparedTask | None) -> None:
        if prepared is not None:
            with suppress(Exception):
                prepared.clean_up()

    def _prepare_foreground_visible_editor_witness(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_editor_and_desktop()
        sentinel = _linux.unique_token("visibleeditorwitness")
        target_path = _linux.DESKTOP / f"{_linux.unique_token('witnessfile')}.txt"
        target_path.write_text("", encoding="utf-8")
        instruction = (
            f"Use the visible {_linux.LAUNCHER_TITLE} window to open Mousepad. In Mousepad, open the Desktop file "
            f"named {target_path.name!r}, type the exact text {sentinel!r}, save with Ctrl+S, then stop. "
            "Do not use a terminal or any command line tool."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "Mousepad"},
            cleanup=_linux.cleanup_editor_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )

    def _prepare_textedit_type_sentinel(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_editor_and_desktop()
        sentinel = _linux.unique_token("textedittype")
        target_path = _linux.DESKTOP / f"{_linux.unique_token('typefile')}.txt"
        target_path.write_text("", encoding="utf-8")
        _linux.open_in_mousepad(target_path)
        instruction = (
            f"The Desktop file {target_path.name!r} is open in Mousepad. Type the exact text {sentinel!r}, "
            "save with Ctrl+S, then stop. Do not use a terminal or any command line tool."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "Mousepad"},
            cleanup=_linux.cleanup_editor_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )

    def _prepare_finder_create_folder(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_file_manager_and_desktop()
        folder_name = _linux.unique_token("folder")
        expected_path = _linux.DESKTOP / folder_name
        _linux.open_desktop_in_thunar()

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_linux.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(expected_path, artifact_dir, name=expected_path.name)

        return PreparedTask(
            case=case,
            instruction=(
                "Thunar is open to the Desktop. Create a new folder with the exact name "
                f"{folder_name!r}, then stop. Do not use a terminal or any command line tool."
            ),
            workspace=workspace,
            evaluator=FolderExistsEvaluator(expected_path),
            metadata={"target_path": str(expected_path), "app": "Thunar"},
            cleanup=_linux.cleanup_file_manager_and_desktop,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_copy_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_file_manager_and_desktop()
        source_path = _linux.DESKTOP / f"{_linux.unique_token('copysource')}.txt"
        folder_path = _linux.DESKTOP / _linux.unique_token("copyfolder")
        copied_path = folder_path / source_path.name
        content = f"copy fixture {_linux.unique_token('copycontent')}\n"
        folder_path.mkdir()
        source_path.write_text(content, encoding="utf-8")
        _linux.open_desktop_in_thunar()

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_linux.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.write_directory_listing(folder_path, artifact_dir, name="target-folder-listing.txt")
            _preserve.copy_path(source_path, artifact_dir, name=f"source-{source_path.name}")
            _preserve.copy_path(copied_path, artifact_dir, name=f"copy-{copied_path.name}")

        return PreparedTask(
            case=case,
            instruction=(
                f"Thunar is open to the Desktop. Copy {source_path.name!r} into {folder_path.name!r}; leave the "
                "original unchanged on the Desktop. Do not use a terminal or any command line tool. Then stop."
            ),
            workspace=workspace,
            evaluator=CopiedFileEvaluator(source_path, copied_path, content),
            metadata={
                "source_path": str(source_path),
                "copied_path": str(copied_path),
                "folder_path": str(folder_path),
                "app": "Thunar",
            },
            cleanup=_linux.cleanup_file_manager_and_desktop,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_open_file_by_double_click(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_opened_file_task()
        target_path = _linux.DESKTOP / f"{_linux.unique_token('openbydoubleclick')}.txt"
        content = f"open fixture {_linux.unique_token('opencontent')}\n"
        target_path.write_text(content, encoding="utf-8")
        _linux.open_desktop_in_thunar()

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_linux.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(target_path, artifact_dir, name=target_path.name)
            _linux.preserve_window_titles(artifact_dir)

        return PreparedTask(
            case=case,
            instruction=(
                f"Thunar is open to the Desktop. Open {target_path.name!r} by double-clicking its icon or filename. "
                "Do not use keyboard shortcuts, menus, a terminal, or any command line tool. Then stop."
            ),
            workspace=workspace,
            evaluator=_linux.LinuxOpenedFileEvaluator(target_path, content),
            metadata={"target_path": str(target_path), "expected_content": content, "app": "Thunar"},
            cleanup=_linux.cleanup_opened_file_task,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_protected_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_file_manager_and_desktop()
        protected_path = _linux.DESKTOP / f"{_linux.unique_token('protected')}.txt"
        content = f"protected fixture {_linux.unique_token('protectedcontent')}\n"
        protected_path.write_text(content, encoding="utf-8")
        _linux.open_desktop_in_thunar()

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_linux.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(protected_path, artifact_dir, name=protected_path.name)

        return PreparedTask(
            case=case,
            instruction=(
                f"Thunar is open to the Desktop. Confirm {protected_path.name!r} exists, but do not delete, rename, "
                "move, open, or edit it. Do not use a terminal or any command line tool. Then stop."
            ),
            workspace=workspace,
            evaluator=ProtectedFileEvaluator(protected_path, content),
            metadata={"protected_path": str(protected_path), "app": "Thunar"},
            cleanup=_linux.cleanup_file_manager_and_desktop,
            preserve_artifacts=preserve,
        )

    def _prepare_calculator_ci_smoke(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_calculator()
        a, b = 2, 2
        expected = a + b
        return PreparedTask(
            case=case,
            instruction=(
                f"Use the visible {_linux.LAUNCHER_TITLE} window to open KCalc. Use only KCalc's visible buttons to "
                f"compute {a} plus {b}. Clear first if needed, then click {a}, +, {b}, and =. Do not use a terminal, "
                "Python, or any command line tool. Then stop."
            ),
            workspace=workspace,
            evaluator=_linux.LinuxCalculatorResultEvaluator(a=a, b=b, expected=expected),
            metadata={"a": a, "b": b, "expected": expected, "app": "KCalc"},
            cleanup=_linux.cleanup_calculator,
            preserve_artifacts=_linux.preserve_kcalc_display,
        )

    def _prepare_browser_download_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _linux.cleanup_chrome()
        filename = f"{_linux.unique_token('download')}.txt"
        prepared = prepare_browser_download_task(
            case=case,
            workspace=workspace,
            filename=filename,
            content=f"download fixture {_linux.unique_token('downloadcontent')}\n",
            target_path=_linux.DOWNLOADS / filename,
            browser_name="Google Chrome using the visible Holo E2E Applications launcher",
            command_line_warning="a terminal, Python,",
        )
        metadata = {**prepared.metadata, "app": "Google Chrome"}

        def cleanup() -> None:
            if prepared.cleanup is not None:
                prepared.cleanup()
            _linux.cleanup_chrome()

        return PreparedTask(
            case=prepared.case,
            instruction=prepared.instruction,
            workspace=prepared.workspace,
            evaluator=prepared.evaluator,
            metadata=metadata,
            cleanup=cleanup,
            preserve_artifacts=prepared.preserve_artifacts,
        )
