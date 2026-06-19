"""Expense report demo.

Pre-launch: stage receipts (downloaded from OSWorld's HF dataset) into
~/Desktop/holo-demo-receipts/, open Finder pointed there, open LibreOffice Calc
with the starter bookkeeping ledger, open Mail. Holo reads each receipt,
appends one ledger row per receipt, saves, and starts a draft to
expenses@example.com with the file attached. We never send anything — the demo
stops at Drafts.

LibreOffice (rather than Numbers) is used because it opens xlsx natively
without a format-conversion prompt, has stable keyboard navigation across
locales, and is cross-platform — the same demo flow ports to Linux later.

Verification is deterministic: the receipts are sha256-pinned fixtures, so
every gold total below is a constant; the Mail draft is read via AppleScript.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from expense_report_demo.demos.runner import AppLaunchSpec, Demo
from expense_report_demo.demos.verify import (
    VerifyCheck,
    check_mail_draft,
    check_new_xlsx_rows_match_totals,
    snapshot_matching_draft_ids,
    template_row_extent,
)

_SLUG = "expense_report"
_FIXTURES = Path("fixtures") / _SLUG
_STAGE_DIR = Path.home() / "Desktop" / "holo-demo-receipts"
_TEMPLATE_DEST = Path.home() / "Desktop" / "holo-demo-bookkeeping.xlsx"
# Pre-run snapshot of existing matching draft ids, written by setup() and read by verify() (the two
# hooks share no in-process state). Lets the mail check count only drafts created during this run.
_DRAFT_BASELINE_PATH = Path.home() / ".holo" / "runs" / f"{_SLUG}-draft-baseline.json"

_MAIL_TO = "expenses@example.com"
_MAIL_SUBJECT = "Expenses"

# The bookkeeping template ships with a title row, a header row
# (Description / Category / Type / Amount / Balance), and six ledger entries.
_TEMPLATE_ROW_COUNT = 8
_AMOUNT_COLUMN = 3  # zero-based: column D

# Grand total per receipt file in manifests/expense_report.toml, in staging
# order. The fixtures are sha256-pinned, so these never drift silently.
GOLD_RECEIPT_TOTALS: dict[str, float] = {
    "01-receipt-8e116af7.jpeg": 186.93,  # grocery store receipt
    "02-receipt-8e116af7.jpg": 3670.00,  # Cash App cash-out screenshot (a transfer, not an expense)
    "03-receipt-8e116af7.jpg": 5.70,  # soup takeout receipt
    "04-receipt-8e116af7.pdf": 154.06,  # East Repair Inc. bike service
    "05-receipt-8e116af7.jpg": 8.10,  # McDonald's takeout
    "06-invoice-4e9f0faf.pdf": 1315.00,  # web design services invoice
    "07-invoice-TII-20220301-90.pdf": 8480.00,  # Tech Innovators laptops
    "08-invoice-GES-20220215-82.pdf": 3180.00,  # Green Energy solar panels
    "09-invoice-243729.pdf": 500.00,  # Staples office supplies
}

# Staged + verified subset; the Cash App cash-out is excluded so the demo only books genuine expenses.
_DEMO_RECEIPT_FILES = ("01-receipt-8e116af7.jpeg", "03-receipt-8e116af7.jpg", "04-receipt-8e116af7.pdf")
_DEMO_RECEIPT_TOTALS: dict[str, float] = {name: GOLD_RECEIPT_TOTALS[name] for name in _DEMO_RECEIPT_FILES}


DEMO = Demo(
    slug=_SLUG,
    title="Expense Report Automation",
    description=(
        "Read a folder of receipts, append one row per receipt to a LibreOffice Calc "
        "bookkeeping ledger (description, category, type, amount), save, and start an "
        "unsent Mail draft with the sheet attached. Deterministically verified."
    ),
    fixtures_manifest=Path("manifests") / f"{_SLUG}.toml",
    pre_launch=[
        AppLaunchSpec(
            bundle_id="com.apple.finder",
            urls=[str(_STAGE_DIR)],
            isolated_browser_session=False,
        ),
        AppLaunchSpec(
            bundle_id="org.libreoffice.script",
            urls=[str(_TEMPLATE_DEST)],
            isolated_browser_session=False,
        ),
        AppLaunchSpec(
            bundle_id="com.apple.mail",
            urls=None,
            isolated_browser_session=False,
        ),
    ],
    focus_bundle_id="org.libreoffice.script",
    task=(
        f"There are receipts and invoices (images and PDFs) in {_STAGE_DIR}. The currently-open "
        "LibreOffice Calc sheet is a bookkeeping ledger with columns Description / Category / Type / "
        "Amount / Balance. For each receipt, single-select it in Finder and press Space to open "
        "Quick Look (do not double-click, do not open it in Preview) to read what was bought and the "
        "grand total, then append one row to the ledger: a short description, a category (food, "
        "travel, software, office, other), Type 'Expense', and the grand total as a negative Amount "
        "(this ledger books expenses negative; leave Balance empty). To fill a row, type each cell "
        "value and press Tab to move to the next cell, then Enter to start the next row. Save the "
        "sheet with Cmd+S (keep "
        f"the .xlsx format if Calc asks), then switch to Mail and start a new draft to {_MAIL_TO} "
        f"with subject '{_MAIL_SUBJECT}' and the saved sheet attached. DO NOT click Send — leave it "
        "in Drafts. Answer with the row count and the sum of all amounts."
    ),
    max_steps=150,
    max_time_s=1800.0,
)


def setup(_demo: Demo) -> None:
    """Copy receipts + template out of fixtures/ onto the Desktop in known locations."""
    if not _FIXTURES.is_dir():
        raise RuntimeError(
            f"fixtures dir {_FIXTURES} missing — run `uv run expense-report-demo pin-fixtures "
            f"manifests/{_SLUG}.toml` then `uv run expense-report-demo run {_SLUG}` again"
        )
    receipts_src = _FIXTURES / "receipts"
    if not receipts_src.is_dir():
        raise RuntimeError(f"expected {receipts_src} after fixture download — manifest may be malformed")
    staged = {p.name for p in receipts_src.iterdir() if p.is_file()}
    missing = set(_DEMO_RECEIPT_TOTALS) - staged
    if missing:
        raise RuntimeError(f"receipts missing from {receipts_src} (re-run pin-fixtures): {sorted(missing)}")
    if _STAGE_DIR.exists():
        shutil.rmtree(_STAGE_DIR)
    _STAGE_DIR.mkdir(parents=True)
    for name in _DEMO_RECEIPT_TOTALS:
        shutil.copy2(receipts_src / name, _STAGE_DIR / name)

    template_src = _FIXTURES / "templates" / "bookkeeping.xlsx"
    if not template_src.is_file():
        raise RuntimeError(f"expected {template_src} after fixture download — manifest may be malformed")
    shutil.copy2(template_src, _TEMPLATE_DEST)

    # Baseline invariant: the template's populated rows are exactly rows 1.._TEMPLATE_ROW_COUNT,
    # contiguous and gap-free, so a row index past _TEMPLATE_ROW_COUNT at verify time is the agent's
    # own work. Checking both count and last index guards against an interior blank row drifting them apart.
    populated, last_index = template_row_extent(_TEMPLATE_DEST)
    if populated != _TEMPLATE_ROW_COUNT or last_index != _TEMPLATE_ROW_COUNT:
        raise RuntimeError(
            f"staged template has {populated} populated rows ending at row {last_index}, "
            f"expected {_TEMPLATE_ROW_COUNT} contiguous (polluted fixture or stale _TEMPLATE_ROW_COUNT): "
            f"{_TEMPLATE_DEST}"
        )

    # Baseline the drafts already matching to/subject so the mail check can tell this run's draft
    # apart from leftovers (Gmail drafts can't be reliably deleted, so we diff rather than clear).
    baseline = snapshot_matching_draft_ids(to_address=_MAIL_TO, subject=_MAIL_SUBJECT)
    _DRAFT_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DRAFT_BASELINE_PATH.write_text(json.dumps(sorted(baseline)))


def _read_draft_baseline() -> frozenset[str]:
    """Draft-id baseline written by setup(); missing means setup didn't run — fail loud, not silent."""
    if not _DRAFT_BASELINE_PATH.is_file():
        raise RuntimeError(f"draft baseline missing at {_DRAFT_BASELINE_PATH} — setup() did not run")
    return frozenset(json.loads(_DRAFT_BASELINE_PATH.read_text()))


def verify(_demo: Demo) -> list[VerifyCheck]:
    """Deterministic post-run checks; runs before teardown moves the sheet away."""
    return [
        check_new_xlsx_rows_match_totals(
            name="ledger_rows",
            sheet_path=_TEMPLATE_DEST,
            template_row_count=_TEMPLATE_ROW_COUNT,
            amount_column=_AMOUNT_COLUMN,
            expected_totals=list(_DEMO_RECEIPT_TOTALS.values()),
        ),
        check_mail_draft(
            name="mail_draft",
            to_address=_MAIL_TO,
            subject=_MAIL_SUBJECT,
            baseline_message_ids=_read_draft_baseline(),
        ),
    ]


def _move_to_quarantine(src: Path, quarantine: Path) -> None:
    """Move `src` into `quarantine`, replacing any artifact a prior run left there."""
    if not src.exists():
        return
    dest = quarantine / src.name
    if dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()
    shutil.move(str(src), str(dest))


def teardown(_demo: Demo) -> None:
    """Quarantine the staged files (Holo may have edited the sheet). User can inspect/re-run."""
    quarantine = Path.home() / ".holo" / "runs" / f"{_SLUG}-quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    _move_to_quarantine(_STAGE_DIR, quarantine)
    _move_to_quarantine(_TEMPLATE_DEST, quarantine)
