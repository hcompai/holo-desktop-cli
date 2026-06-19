from __future__ import annotations

from .. import _macos
from .._domain import EvaluationResult, FailureCategory, FlatMetadata


class CalculatorResultEvaluator:
    """Evaluator that checks Calculator's display result exactly."""

    name = "calculator_result"

    def __init__(self, *, a: int, b: int, expected: int) -> None:
        self.a = a
        self.b = b
        self.expected = expected

    def evaluate(self) -> EvaluationResult:
        display = _macos.calculator_display()
        metadata: FlatMetadata = {"a": self.a, "b": self.b, "expected": self.expected}
        if display is None:
            # Inconclusive, not an agent failure. Stash the full static-text dump so
            # the artifact tells us how to fix the read instead of just "unreadable".
            raw_values = _macos.calculator_static_text_values()
            return EvaluationResult(
                passed=False,
                message="Calculator display unreadable via accessibility (StandardInputView AX read)",
                failure_category=FailureCategory.EVALUATOR,
                metadata={
                    **metadata,
                    "ax_static_text_values": raw_values,
                    "calculator_running": _macos._pid_for_process("Calculator") is not None,
                },
            )
        result_part = calculator_result_part(display)
        if result_part != str(self.expected):
            return EvaluationResult(
                passed=False,
                message=(
                    f"Calculator result mismatch for {self.a}+{self.b}: "
                    f"expected {self.expected!r}, got {result_part!r} from display {display!r}"
                ),
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "display": display, "result_part": result_part},
            )
        return EvaluationResult(
            passed=True,
            message="Calculator result matched",
            metadata={**metadata, "display": display, "result_part": result_part},
        )


def calculator_result_part(display: str) -> str:
    """Normalize Calculator's display value for exact comparison.

    The StandardInputView read returns just the result text, salted with U+200E
    bidi marks (e.g. ``'\\u200e1\\u200e3'`` for 13) — strip those and whitespace.
    """

    return _strip_bidi_marks(display).strip()


def _strip_bidi_marks(value: str) -> str:
    return value.replace("\u200e", "").replace("\u200f", "")
