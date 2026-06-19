---
id: tickets-filter
url: http://localhost:5173/tickets
timeout_s: 240
viewport: { width: 1280, height: 900 }
backend: command
credentials: demo@nimbus.test / holo-qa-1
---

# Tickets: filter by status

## Setup

The Nimbus Desk dev server is running at `http://localhost:5173`. Sign in with
the credentials above if presented with the login page, then go to the Tickets
page. The table initially lists 5 tickets with mixed statuses (Open, Reopened,
Closed) and a "Status" dropdown sits above the table, set to "All".

## Task

1. Confirm the table shows 5 tickets with mixed status badges.
2. Open the Status dropdown and select "Open".
3. Observe the table and the area between the dropdown and the table.

## Expected Result

The table shows exactly the three Open tickets (#2042, #2040, #2036) and no
others. No error message appears.

## Verification

- FAIL if an error banner appears after selecting a status (quote its text verbatim).
- FAIL if the table shows no rows after filtering.
- FAIL if any non-Open ticket remains visible while "Open" is selected.
- PASS only if the filtered table contains exactly the three Open tickets.
