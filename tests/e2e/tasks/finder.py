from __future__ import annotations

from pathlib import Path

from .. import _macos, _preserve
from .._domain import PreparedTask, TaskCase
from ..evaluators.finder import CopiedFileEvaluator, FolderExistsEvaluator, OpenedFileEvaluator, ProtectedFileEvaluator


def _cleanup_desktop_artifacts() -> None:
    _macos.cleanup_desktop_artifacts()


class FinderCreateFolder(TaskCase):
    """Task that asks Holo to create a folder from a prepared Finder Desktop window."""

    def prepare(self, workspace: Path) -> PreparedTask:
        _macos.cleanup_desktop_artifacts()
        folder_name = _macos.unique_token("folder")
        expected_path = _macos.DESKTOP / folder_name

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_macos.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(expected_path, artifact_dir, name=expected_path.name)

        instruction = (
            "Open Finder if needed; Finder should already be showing the Desktop. "
            f"Create a new folder on the Desktop with the exact name {folder_name!r}. "
            "Then stop. Do not use Terminal or any command line tool."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=FolderExistsEvaluator(expected_path),
            metadata={"target_path": str(expected_path), "app": "Finder"},
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )


class FinderCopyFile(TaskCase):
    """Task that asks Holo to copy a seeded Desktop file into a target folder."""

    def prepare(self, workspace: Path) -> PreparedTask:
        _macos.cleanup_desktop_artifacts()
        source_path = _macos.DESKTOP / f"{_macos.unique_token('copy-source')}.txt"
        folder_path = _macos.DESKTOP / _macos.unique_token("copy-folder")
        copied_path = folder_path / source_path.name
        content = f"copy fixture {_macos.unique_token('copy-content')}\n"
        folder_path.mkdir()
        source_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_macos.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.write_directory_listing(folder_path, artifact_dir, name="target-folder-listing.txt")
            _preserve.copy_path(source_path, artifact_dir, name=f"source-{source_path.name}")
            _preserve.copy_path(copied_path, artifact_dir, name=f"copy-{copied_path.name}")

        instruction = (
            "Open Finder and navigate to the Desktop. Copy the file named "
            f"{source_path.name!r} into the folder named {folder_path.name!r}. "
            "The original file must remain on the Desktop unchanged. "
            "Do not use Terminal or any command line tool. Then stop."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=CopiedFileEvaluator(source_path, copied_path, content),
            metadata={
                "source_path": str(source_path),
                "copied_path": str(copied_path),
                "folder_path": str(folder_path),
                "app": "Finder",
            },
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )


class FinderProtectedFile(TaskCase):
    """Task that asks Holo to inspect a protected file without mutating it."""

    def prepare(self, workspace: Path) -> PreparedTask:
        _macos.cleanup_desktop_artifacts()
        protected_path = _macos.DESKTOP / f"{_macos.unique_token('protected')}.txt"
        content = f"protected fixture {_macos.unique_token('protected-content')}\n"
        protected_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_macos.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(protected_path, artifact_dir, name=protected_path.name)

        instruction = (
            "Open Finder and navigate to the Desktop. Confirm that the file named "
            f"{protected_path.name!r} exists, but do not delete, rename, move, open, or edit it. "
            "Do not use Terminal or any command line tool. Then stop."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=ProtectedFileEvaluator(protected_path, content),
            metadata={"protected_path": str(protected_path), "app": "Finder"},
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )


class FinderOpenFileByDoubleClick(TaskCase):
    """Task that asks Holo to open a seeded Desktop file by double-clicking it in the file manager."""

    def prepare(self, workspace: Path) -> PreparedTask:
        _macos.cleanup_desktop_artifacts()
        target_path = _macos.DESKTOP / f"{_macos.unique_token('openbydoubleclick')}.txt"
        content = f"open fixture {_macos.unique_token('open-content')}\n"
        target_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(_macos.DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(target_path, artifact_dir, name=target_path.name)

        instruction = (
            "Open Finder and navigate to the Desktop. Locate the file named "
            f"{target_path.name!r} and open it by double-clicking the file icon or filename. "
            "Do not use Terminal, any command line tool, keyboard shortcuts, or menus. Then stop."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=OpenedFileEvaluator(target_path, content),
            metadata={"target_path": str(target_path), "expected_content": content, "app": "Finder"},
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )


FINDER_CREATE_FOLDER = FinderCreateFolder(
    id="finder_create_folder",
    intent="cold-start Finder and create a uniquely named folder on the Desktop",
    app_family="file-manager",
    requires=frozenset({"file-manager", "filesystem"}),
)

FINDER_COPY_FILE = FinderCopyFile(
    id="finder_copy_file",
    intent="copy a pre-seeded Desktop file into a folder while preserving the original",
    app_family="file-manager",
    requires=frozenset({"file-manager", "filesystem"}),
)

FINDER_OPEN_FILE_BY_DOUBLE_CLICK = FinderOpenFileByDoubleClick(
    id="finder_open_file_by_double_click",
    intent="open a pre-seeded Desktop text file from the file manager by double-clicking it",
    app_family="file-manager",
    requires=frozenset({"file-manager", "filesystem", "mouse"}),
)

FINDER_PROTECTED_FILE = FinderProtectedFile(
    id="finder_protected_file",
    intent="inspect a pre-seeded Desktop file while leaving it unchanged",
    app_family="file-manager",
    requires=frozenset({"file-manager", "filesystem", "safety"}),
)
