---
name: Expense Report Automation
description: Read a folder of receipt images/PDFs, append rows to a LibreOffice Calc bookkeeping ledger (description, category, type, amount), save, and start a Mail draft with the sheet attached.
publisher: Holo Demos
version: "0.1.0"
---

You're filling out an expense report end-to-end. There's a folder of receipts (images and PDFs) and an open LibreOffice Calc ledger with columns `Description | Category | Type | Amount | Balance`. Your job is one row per receipt, then a Mail draft. You must NOT click Send on the email — leave it in Drafts.

## Reading a receipt

For each file in the receipts folder, single-select it in Finder and press `Space` to open Quick Look. Do NOT double-click and do NOT open it in Preview.app — Quick Look reads faster and avoids spawning extra windows you then have to close. You're hunting two fields, in this priority order:

1. **Grand total** — usually labeled `Total`, `Amount due`, `Grand total`, `Balance Due`, or `Charged`. If there are subtotals, take the final one (the amount actually paid, tax included).
2. **What was bought** — a short description from the merchant name or the line items (`McDonald's takeout`, `Staples office supplies`).

Skip individual line items. If a receipt is unreadable, write `???` in the offending field and flag it in your answer — never invent a number.

## Categories

- **food** — restaurants, coffee, groceries, food delivery
- **travel** — flights, hotels, trains, taxis, rideshare, fuel
- **software** — SaaS subscriptions, app store purchases, plugins
- **office** — physical office supplies, hardware, furniture
- **other** — anything that doesn't fit; flag it in your answer

## Filling the LibreOffice Calc ledger

Calc is keyboard-friendly. Use these shortcuts; don't click around.

- After selecting a cell, `Tab` advances right, `Return` advances down. Don't use the mouse for cell navigation.
- Batch a whole row in ONE step: the grid focus path is deterministic, so emit the row's writes and `Tab`s as a single sequence of tool calls (`write` Description, `Tab`, `write` Category, `Tab`, `write` `Expense`, `Tab`, `write` Amount, `Return`). Don't split each cell into its own step — one step per row, not one step per cell.
- To find the first empty row, `Cmd+End` jumps to the last used cell — go one row below that, then back to column A.
- One row per receipt: `Description` (short), `Category` (see above), `Type` is the literal word `Expense`, `Amount` is the grand total as a NEGATIVE number (this ledger books expenses negative, like the existing rows), `Balance` stays empty.
- Amounts: type the number only (no currency symbol, no thousands separator). Calc will format the column.

Save with `Cmd+S`. The first save on a `.xlsx` file pops a "Use xlsx format / Use ODF format" dialog — pick **Use xlsx Format!** (`Return` defaults to ODF, which is wrong; click the xlsx button or press the underlined keyboard shortcut). Don't accept ODF.

## Mail draft

After saving the sheet:

1. Switch to Mail (`Cmd+Tab`).
2. `Cmd+N` for a new message.
3. To: `expenses@example.com`. Subject: exactly `Expenses` (nothing appended).
4. Body: one line — "X receipts attached, total $Y. Please process." Substitute the numbers.
5. Attach the saved Calc file: drag from Finder into the message body, OR `Cmd+Shift+A` and pick the file.
6. **STOP**. Close the compose window with `Cmd+W` — Mail will auto-save to Drafts. DO NOT click Send.
7. Verify by opening the Drafts folder in Mail and confirming the message is there with the attachment visible.

## Verification

Before answering:

- The Calc sheet has one row per receipt you processed (count them, they should match the file count in the receipts folder).
- The sheet is saved (no asterisk / "modified" indicator in the window title).
- A draft exists in Mail's Drafts folder with the right attachment.

## Answer shape

```
processed: N rows
total: -$XYZ.AB (sum of the new Amount cells)
unreadable: 0 (or list the filenames)
draft: saved (sender@example.com -> expenses@example.com)
```

If anything is wrong (unreadable receipts, foreign currency), say so explicitly. Never invent data.
