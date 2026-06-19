"""Behavioural tests for the demo verifiers against synthetic worlds.

Real openpyxl files on disk; no agent run required. The Mail-draft decision
logic is exercised here against synthetic draft lists; the AppleScript that
observes real drafts needs a live Mail automation grant and is covered by real
demo runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook

from expense_report_demo.demos.expense_report import GOLD_RECEIPT_TOTALS
from expense_report_demo.demos.verify import DraftRef, check_new_xlsx_rows_match_totals, evaluate_mail_draft

_TEMPLATE_ROWS = [
    ("Bookkeeping simple", None, None, None, None),
    ("Description", "Category", "Type", "Amount", "Balance"),
    ("Office Supplies Purchase", "Office Supplies", "Expense", -150, 850),
    ("Client Payment Received", "Sales", "Income", 500, 1350),
    ("Internet Bill", "Utilities", "Expense", -60, 1290),
    ("Freelance Services", "Services", "Income", 300, 1590),
    ("Rent Payment", "Rent", "Expense", -700, 890),
    ("Software Subscription", "Software", "Expense", -100, 790),
]


def _write_sheet(path: Path, extra_rows: Sequence[tuple[object, ...]]) -> Path:
    wb = Workbook()
    ws = wb.active
    for row in (*_TEMPLATE_ROWS, *extra_rows):
        ws.append(row)
    wb.save(path)
    return path


def _check(path: Path, totals: list[float]):
    return check_new_xlsx_rows_match_totals(
        name="ledger_rows",
        sheet_path=path,
        template_row_count=len(_TEMPLATE_ROWS),
        amount_column=3,
        expected_totals=totals,
    )


def test_passes_when_all_totals_present_as_negative_amounts(tmp_path: Path) -> None:
    totals = list(GOLD_RECEIPT_TOTALS.values())
    rows = [(f"receipt {i}", "other", "Expense", -t, None) for i, t in enumerate(totals)]
    result = _check(_write_sheet(tmp_path / "ok.xlsx", rows), totals)
    assert result.passed, result.reason
    assert result.failure_category is None


def test_passes_regardless_of_row_order_and_sign(tmp_path: Path) -> None:
    totals = [5.70, 186.93, 8.10]
    rows = [
        ("groceries", "food", "Expense", 186.93, None),
        ("mcdonalds", "food", "Expense", -8.10, None),
        ("soup", "food", "Expense", -5.70, None),
    ]
    result = _check(_write_sheet(tmp_path / "order.xlsx", rows), totals)
    assert result.passed, result.reason


def test_fails_agent_on_missing_row(tmp_path: Path) -> None:
    totals = [5.70, 186.93]
    rows = [("soup", "food", "Expense", -5.70, None)]
    result = _check(_write_sheet(tmp_path / "missing.xlsx", rows), totals)
    assert not result.passed
    assert result.failure_category == "agent"
    assert "expected 2 new rows" in result.reason


def test_fails_agent_on_wrong_amount(tmp_path: Path) -> None:
    totals = [5.70]
    rows = [("soup", "food", "Expense", -9.99, None)]
    result = _check(_write_sheet(tmp_path / "wrong.xlsx", rows), totals)
    assert not result.passed
    assert result.failure_category == "agent"
    assert "9.99" in result.reason


def test_fails_agent_on_non_numeric_amount(tmp_path: Path) -> None:
    totals = [5.70]
    rows = [("soup", "food", "Expense", "$5.70", None)]
    result = _check(_write_sheet(tmp_path / "text.xlsx", rows), totals)
    assert not result.passed
    assert result.failure_category == "agent"
    assert "not numeric" in result.reason


def test_tolerates_cent_rounding(tmp_path: Path) -> None:
    totals = [5.70]
    rows = [("soup", "food", "Expense", -5.7000000001, None)]
    result = _check(_write_sheet(tmp_path / "tol.xlsx", rows), totals)
    assert result.passed, result.reason


def test_missing_sheet_is_harness_failure(tmp_path: Path) -> None:
    result = _check(tmp_path / "nope.xlsx", [5.70])
    assert not result.passed
    assert result.failure_category == "harness"


_MAIL_TO = "expenses@example.com"
_MAIL_SUBJECT = "Expenses"


def _eval(drafts: list[DraftRef], baseline: frozenset[str]):
    return evaluate_mail_draft(
        name="mail_draft",
        to_address=_MAIL_TO,
        subject=_MAIL_SUBJECT,
        drafts=drafts,
        baseline_message_ids=baseline,
    )


def test_mail_draft_passes_on_new_draft_with_attachment() -> None:
    drafts = [DraftRef(message_id="new@h.ai", attachment_count=1)]
    result = _eval(drafts, frozenset())
    assert result.passed, result.reason
    assert result.failure_category is None


def test_mail_draft_ignores_stale_baseline_drafts() -> None:
    """A draft already present before the run (its id in the baseline) must not satisfy the check."""
    stale = DraftRef(message_id="stale@h.ai", attachment_count=1)
    result = _eval([stale], frozenset({"stale@h.ai"}))
    assert not result.passed
    assert result.failure_category == "agent"
    assert "no new draft" in result.reason


def test_mail_draft_passes_on_new_draft_even_when_stale_present() -> None:
    stale = DraftRef(message_id="stale@h.ai", attachment_count=1)
    fresh = DraftRef(message_id="fresh@h.ai", attachment_count=2)
    result = _eval([stale, fresh], frozenset({"stale@h.ai"}))
    assert result.passed, result.reason
    assert "2 attachment" in result.reason


def test_mail_draft_fails_when_new_draft_has_no_attachment() -> None:
    fresh = DraftRef(message_id="fresh@h.ai", attachment_count=0)
    result = _eval([fresh], frozenset())
    assert not result.passed
    assert result.failure_category == "agent"
    assert "attachment" in result.reason


def test_mail_draft_fails_when_no_drafts_at_all() -> None:
    result = _eval([], frozenset())
    assert not result.passed
    assert result.failure_category == "agent"
    assert "no new draft" in result.reason


def test_gold_totals_cover_all_manifest_receipts() -> None:
    """Every receipt pinned in the manifest must have a gold total, or the
    verifier under-counts the expected rows."""
    import tomllib

    example_root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((example_root / "manifests/expense_report.toml").read_text(encoding="utf-8"))
    receipt_names = {Path(pull["dest"]).name for pull in manifest["pull"] if str(pull["dest"]).startswith("receipts/")}
    assert receipt_names == set(GOLD_RECEIPT_TOTALS)
