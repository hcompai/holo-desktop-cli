from __future__ import annotations

from pathlib import Path

from .. import _macos, _preserve
from .._domain import PreparedTask, TaskCase
from ..evaluators.textedit import FileContainsEvaluator


def _cleanup_textedit_and_desktop() -> None:
    _macos.quit_app("TextEdit", discard_unsaved_changes=True)
    _macos.cleanup_desktop_artifacts()


class ForegroundVisibleEditorWitness(TaskCase):
    """Task that proves Holo can cold-start TextEdit and edit a seeded file."""

    def prepare(self, workspace: Path) -> PreparedTask:
        sentinel = _macos.unique_token("visible_editor_witness")
        target_path = _macos.DESKTOP / f"{_macos.unique_token('witnessfile')}.txt"
        target_path.write_text("", encoding="utf-8")

        instruction = (
            "Open TextEdit, open the Desktop file named "
            f"{target_path.name!r}, type the exact text {sentinel!r} into the document, "
            "save the file with Command-S, then stop. Do not use Terminal or any command line tool."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "TextEdit"},
            cleanup=_cleanup_textedit_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )


class TextEditTypeSentinel(TaskCase):
    """Task that asks Holo to type a sentinel into a prepared TextEdit document."""

    def prepare(self, workspace: Path) -> PreparedTask:
        sentinel = _macos.unique_token("textedit_type")
        target_path = _macos.DESKTOP / f"{_macos.unique_token('typefile')}.txt"
        target_path.write_text("", encoding="utf-8")

        instruction = (
            "Open TextEdit if needed; the target document should already be active. "
            f"Type the exact text {sentinel!r} into the document, save the file with Command-S, then stop. "
            "Do not use Terminal or any command line tool."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "TextEdit"},
            cleanup=_cleanup_textedit_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )


FOREGROUND_VISIBLE_EDITOR_WITNESS = ForegroundVisibleEditorWitness(
    id="foreground_visible_editor_witness",
    intent="prove Holo can cold-start TextEdit and edit a seeded file",
    app_family="text-editor",
    requires=frozenset({"text-editor", "filesystem"}),
)

TEXTEDIT_TYPE_SENTINEL = TextEditTypeSentinel(
    id="textedit_type_sentinel",
    intent="type a unique sentinel into an open TextEdit document",
    app_family="text-editor",
    requires=frozenset({"text-editor"}),
)
