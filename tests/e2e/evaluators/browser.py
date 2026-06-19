from __future__ import annotations

from pathlib import Path

from .._domain import EvaluationResult, FailureCategory


class DownloadedFileEvaluator:
    """Evaluator that checks a browser downloaded the expected fixture file."""

    name = "downloaded_file"

    def __init__(self, path: Path, expected_content: str) -> None:
        self.path = path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata = {"path": str(self.path), "expected_content": self.expected_content}
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"downloaded file does not exist: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if not self.path.is_file():
            return EvaluationResult(
                passed=False,
                message=f"download target is not a file: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        observed_content = self.path.read_text(encoding="utf-8", errors="replace")
        if observed_content != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="downloaded file content did not match fixture",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "observed_content": observed_content},
            )
        return EvaluationResult(passed=True, message="downloaded file matched fixture", metadata=metadata)
