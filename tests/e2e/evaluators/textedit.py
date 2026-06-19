from __future__ import annotations

from pathlib import Path

from .. import _macos
from .._domain import EvaluationResult, FailureCategory


class FileContainsEvaluator:
    """Evaluator that checks a file contains an expected sentinel."""

    name = "file_contains"

    def __init__(self, path: Path, expected_text: str) -> None:
        self.path = path
        self.expected_text = expected_text

    def evaluate(self) -> EvaluationResult:
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"expected file to exist: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata={"path": str(self.path), "expected_text": self.expected_text},
            )
        text = self.path.read_text(errors="replace")
        if self.expected_text not in text:
            return EvaluationResult(
                passed=False,
                message=f"sentinel {self.expected_text!r} not found in {self.path}: {text!r}",
                failure_category=FailureCategory.AGENT,
                metadata={"path": str(self.path), "expected_text": self.expected_text, "observed_length": len(text)},
            )
        return EvaluationResult(
            passed=True,
            message="expected text found",
            metadata={"path": str(self.path), "expected_text": self.expected_text, "observed_length": len(text)},
        )


class TextEditContainsEvaluator:
    """Evaluator that checks open TextEdit documents contain a sentinel."""

    name = "textedit_contains"

    def __init__(self, expected_text: str) -> None:
        self.expected_text = expected_text

    def evaluate(self) -> EvaluationResult:
        result = _macos.textedit_documents_text()
        if isinstance(result, _macos.TextEditDocumentsError):
            return EvaluationResult(
                passed=False,
                message=result.message,
                failure_category=FailureCategory.EVALUATOR,
                metadata={"expected_text": self.expected_text},
            )
        if not any(self.expected_text in doc for doc in result.documents):
            return EvaluationResult(
                passed=False,
                message=f"sentinel {self.expected_text!r} not found in TextEdit docs: {result.documents!r}",
                failure_category=FailureCategory.AGENT,
                metadata={"expected_text": self.expected_text, "document_count": len(result.documents)},
            )
        return EvaluationResult(
            passed=True,
            message="expected text found in TextEdit",
            metadata={"expected_text": self.expected_text, "document_count": len(result.documents)},
        )
