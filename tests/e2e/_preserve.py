from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import _macos


def copy_path(path: Path, artifact_dir: Path, *, name: str | None = None) -> None:
    """Copy a final file or directory into the e2e artifact directory."""

    if not path.exists():
        (artifact_dir / f"{name or path.name}.missing.txt").write_text(f"missing: {path}\n", encoding="utf-8")
        return

    destination = artifact_dir / (name or path.name)
    if path.is_dir():
        shutil.copytree(path, destination, dirs_exist_ok=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def copy_matching_files(directory: Path, pattern: str, artifact_dir: Path, *, subdir: str) -> None:
    """Copy files matching a pattern into a subdirectory for post-cleanup debugging."""

    destination = artifact_dir / subdir
    destination.mkdir(parents=True, exist_ok=True)
    matches = sorted(directory.glob(pattern))
    if not matches:
        (destination / "matches.txt").write_text(f"no matches for {directory / pattern}\n", encoding="utf-8")
        return
    for path in matches:
        copy_path(path, destination)


def write_directory_listing(directory: Path, artifact_dir: Path, *, name: str = "directory-listing.txt") -> None:
    """Write a shallow directory listing to help debug file-manager tasks."""

    if not directory.exists():
        (artifact_dir / name).write_text(f"missing directory: {directory}\n", encoding="utf-8")
        return
    lines = [f"{directory}/"]
    for path in sorted(directory.iterdir()):
        kind = "dir" if path.is_dir() else "file"
        lines.append(f"{kind}\t{path.name}")
    (artifact_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_textedit_documents(artifact_dir: Path) -> None:
    """Persist currently open TextEdit document text."""

    result = _macos.textedit_documents_text()
    if isinstance(result, _macos.TextEditDocumentsError):
        (artifact_dir / "textedit-documents-error.txt").write_text(result.message + "\n", encoding="utf-8")
        return
    for index, text in enumerate(result.documents, start=1):
        (artifact_dir / f"textedit-document-{index}.txt").write_text(text, encoding="utf-8")


def write_calculator_display(artifact_dir: Path) -> None:
    """Persist Calculator display text if it is readable."""

    values = _macos.calculator_static_text_values()
    (artifact_dir / "calculator-ax-static-text-values.json").write_text(
        json.dumps(values, indent=2),
        encoding="utf-8",
    )
    display = _macos.calculator_display()
    text = "<unreadable>\n" if display is None else f"{display}\n"
    (artifact_dir / "calculator-display.txt").write_text(text, encoding="utf-8")


def write_notes_body(title: str, artifact_dir: Path) -> None:
    """Persist a matched Notes body for debugging before cleanup deletes test notes."""

    body = _macos.notes_body_for_title(title)
    text = "<missing>\n" if body is None else body
    (artifact_dir / "note-body.html").write_text(text, encoding="utf-8")
