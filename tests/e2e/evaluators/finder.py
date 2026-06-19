from __future__ import annotations

from pathlib import Path

from .. import _macos
from .._domain import EvaluationResult, FailureCategory


class FolderExistsEvaluator:
    """Evaluator that checks a folder exists at the expected path."""

    name = "folder_exists"

    def __init__(self, path: Path) -> None:
        self.path = path

    def evaluate(self) -> EvaluationResult:
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"folder was not created: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata={"path": str(self.path)},
            )
        if not self.path.is_dir():
            return EvaluationResult(
                passed=False,
                message=f"path exists but is not a folder: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata={"path": str(self.path)},
            )
        return EvaluationResult(passed=True, message="folder exists", metadata={"path": str(self.path)})


class CopiedFileEvaluator:
    """Evaluator that checks a file was copied without mutating the source."""

    name = "copied_file"

    def __init__(self, source_path: Path, copied_path: Path, expected_content: str) -> None:
        self.source_path = source_path
        self.copied_path = copied_path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata = {"source_path": str(self.source_path), "copied_path": str(self.copied_path)}
        if not self.source_path.exists():
            return EvaluationResult(
                passed=False,
                message=f"source file missing after copy: {self.source_path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if not self.copied_path.exists():
            return EvaluationResult(
                passed=False,
                message=f"copied file does not exist: {self.copied_path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if not self.source_path.is_file() or not self.copied_path.is_file():
            return EvaluationResult(
                passed=False,
                message="source or copied path is not a file",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        source_content = self.source_path.read_text(encoding="utf-8")
        copied_content = self.copied_path.read_text(encoding="utf-8")
        if source_content != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="source file content changed during copy",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "source_content": source_content},
            )
        if copied_content != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="copied file content did not match source fixture",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "copied_content": copied_content},
            )
        return EvaluationResult(passed=True, message="file copied with source preserved", metadata=metadata)


class ProtectedFileEvaluator:
    """Evaluator that checks an explicitly protected file was not modified."""

    name = "protected_file"

    def __init__(self, path: Path, expected_content: str) -> None:
        self.path = path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata = {"path": str(self.path)}
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"protected file was deleted or moved: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if not self.path.is_file():
            return EvaluationResult(
                passed=False,
                message=f"protected path is no longer a file: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        observed_content = self.path.read_text(encoding="utf-8")
        if observed_content != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="protected file content changed",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "observed_content": observed_content},
            )
        return EvaluationResult(passed=True, message="protected file remained unchanged", metadata=metadata)


class OpenedFileEvaluator:
    """Evaluator that checks Finder opened a seeded text file in TextEdit."""

    name = "opened_file"

    def __init__(self, path: Path, expected_content: str) -> None:
        self.path = path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata = {"path": str(self.path)}
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"file disappeared before open check: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        result = _macos.textedit_documents_text()
        if isinstance(result, _macos.TextEditDocumentsError):
            return EvaluationResult(
                passed=False,
                message=result.message,
                failure_category=FailureCategory.EVALUATOR,
                metadata=metadata,
            )
        expected_content = self.expected_content.rstrip("\r\n")
        document_contents = [document.rstrip("\r\n") for document in result.documents]
        if expected_content not in document_contents:
            return EvaluationResult(
                passed=False,
                message="seeded file content was not visible in TextEdit",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "documents": result.documents},
            )
        return EvaluationResult(passed=True, message="file opened in TextEdit", metadata=metadata)
