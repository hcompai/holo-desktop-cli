from __future__ import annotations

import json
import re
from pathlib import Path

from .. import _linux
from .._domain import EvaluationResult, FailureCategory, FlatMetadata
from .calculator import calculator_result_part


def opened_file_window(filename: str, titles: list[str] | None = None) -> str | None:
    path = Path(filename)
    candidates = (path.name, path.stem)
    visible_titles = titles if titles is not None else [title for _, title in _linux.visible_windows()]
    for title in visible_titles:
        folded = title.casefold()
        if "mousepad" in folded and any(candidate.casefold() in folded for candidate in candidates if candidate):
            return title
    return None


class LinuxOpenedFileEvaluator:
    """Proves a seeded file is open in a visible Mousepad window."""

    name = "linux_opened_file"

    def __init__(self, path: Path, expected_content: str) -> None:
        self.path = path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata: FlatMetadata = {"path": str(self.path)}
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"file disappeared before open check: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if self.path.read_text(encoding="utf-8", errors="replace") != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="seeded file content changed before open check",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        titles = [title for _, title in _linux.visible_windows()]
        matching_title = opened_file_window(self.path.name, titles)
        metadata["visible_window_titles"] = titles
        if matching_title is None:
            return EvaluationResult(
                passed=False,
                message="seeded file was not visible in a Mousepad window",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        return EvaluationResult(
            passed=True,
            message="file opened in Mousepad",
            metadata={**metadata, "mousepad_window_title": matching_title},
        )


class LinuxCalculatorResultEvaluator:
    """Checks KCalc's visible result through the independent AT-SPI tree."""

    name = "linux_calculator_result"

    def __init__(self, *, a: int, b: int, expected: int) -> None:
        self.a = a
        self.b = b
        self.expected = expected

    def evaluate(self) -> EvaluationResult:
        entries = kcalc_accessible_entries()
        display = kcalc_display_from_entries(entries)
        metadata: FlatMetadata = {
            "a": self.a,
            "b": self.b,
            "expected": self.expected,
            "accessible_entries": [json.dumps(entry, sort_keys=True) for entry in entries],
        }
        if display is None:
            return EvaluationResult(
                passed=False,
                message="KCalc display unreadable via AT-SPI",
                failure_category=FailureCategory.EVALUATOR,
                metadata=metadata,
            )
        result_part = kcalc_result_part(display)
        if result_part != str(self.expected):
            return EvaluationResult(
                passed=False,
                message=f"KCalc result mismatch: expected {self.expected!r}, got {result_part!r}",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "display": display, "result_part": result_part},
            )
        return EvaluationResult(
            passed=True,
            message="KCalc result matched",
            metadata={**metadata, "display": display, "result_part": result_part},
        )


def kcalc_accessible_entries() -> list[dict[str, str]]:
    script = r"""
import json
import pyatspi

rows = []

def visit(node, depth=0):
    if depth > 20:
        return
    try:
        name = node.name or ""
        role = node.getRoleName() or ""
    except Exception:
        return
    text = ""
    try:
        text_iface = node.queryText()
        text = text_iface.getText(0, text_iface.characterCount)
    except Exception:
        pass
    if name or text:
        rows.append({"name": name, "role": role, "text": text})
    try:
        for child in node:
            visit(child, depth + 1)
    except Exception:
        pass

desktop = pyatspi.Registry.getDesktop(0)
for app in desktop:
    try:
        if "kcalc" in (app.name or "").lower():
            visit(app)
    except Exception:
        pass
print(json.dumps(rows))
"""
    proc = _linux.run_command(["/usr/bin/python3", "-c", script], timeout=10.0)
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [
        {key: str(value) for key, value in item.items() if key in {"name", "role", "text"}}
        for item in payload
        if isinstance(item, dict)
    ]


def kcalc_display_from_entries(entries: list[dict[str, str]]) -> str | None:
    display_candidates: list[str] = []
    text_candidates: list[str] = []
    numeric_candidates: list[str] = []
    for entry in entries:
        role = entry.get("role", "").casefold()
        values = [entry.get("text", "").strip(), entry.get("name", "").strip()]
        for value in values:
            if not value:
                continue
            if "display" in entry.get("name", "").casefold() or "display" in role:
                display_candidates.append(value)
            if any(kind in role for kind in ("text", "entry", "edit")) and "button" not in role:
                text_candidates.append(value)
            if "button" not in role and re.fullmatch(r"[\s\u200e\u200f\d.,+\-*/=]+", value):
                numeric_candidates.append(value)
    for candidates in (display_candidates, text_candidates, numeric_candidates):
        for candidate in reversed(candidates):
            if re.search(r"\d", candidate):
                return candidate
    return None


def kcalc_result_part(display: str) -> str:
    result = calculator_result_part(display)
    if "=" in result:
        result = result.rsplit("=", 1)[-1]
    return result.strip()


def preserve_kcalc_display(artifact_dir: Path) -> None:
    entries = kcalc_accessible_entries()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "kcalc-atspi.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    display = kcalc_display_from_entries(entries)
    (artifact_dir / "kcalc-display.txt").write_text(f"{display or ''}\n", encoding="utf-8")


def preserve_window_titles(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    titles = [title for _, title in _linux.visible_windows()]
    (artifact_dir / "visible-window-titles.txt").write_text("\n".join(titles) + "\n", encoding="utf-8")
