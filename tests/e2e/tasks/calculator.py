from __future__ import annotations

from pathlib import Path

from .. import _macos, _preserve
from .._domain import PreparedTask, TaskCase
from ..evaluators.calculator import CalculatorResultEvaluator


def _cleanup_calculator() -> None:
    _macos.quit_app("Calculator")


class CalculatorCISmoke(TaskCase):
    """Small cross-platform CI smoke task: open Calculator and compute 2+2."""

    def prepare(self, workspace: Path) -> PreparedTask:
        a = 2
        b = 2
        expected = a + b

        instruction = (
            "Open Calculator in basic mode. Use the visible Calculator app UI to compute "
            f"{a} plus {b}. Click AC first if needed, then click {a}, +, {b}, and =. "
            f"The task is not complete until the visible Calculator result display shows exactly {expected}. "
            "Do not answer or stop while the expression is still in progress, such as showing only "
            f"{a} + or {a} + {b}. Do not use Terminal or any command line tool. Then stop."
        )
        return PreparedTask(
            case=self,
            instruction=instruction,
            workspace=workspace,
            evaluator=CalculatorResultEvaluator(a=a, b=b, expected=expected),
            metadata={"a": a, "b": b, "expected": expected, "app": "Calculator"},
            cleanup=_cleanup_calculator,
            preserve_artifacts=_preserve.write_calculator_display,
        )


CALCULATOR_CI_SMOKE = CalculatorCISmoke(
    id="calculator_ci_smoke",
    intent="cold-start Calculator and compute 2+2 through the visible UI",
    app_family="calculator",
    requires=frozenset({"calculator"}),
)
