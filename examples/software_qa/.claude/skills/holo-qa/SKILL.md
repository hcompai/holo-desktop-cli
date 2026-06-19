---
name: holo-qa
description: Use when asked to QA Nimbus Desk, run a qa/*.md behavioral spec, verify UI behavior, check a regression, or confirm a UI fix. Drives the running app through the root Holo MCP tool, holo_desktop(task), and returns a QA report.
---

# holo-qa: behavioral QA through root Holo MCP

Use the normal installed Holo MCP tool: `holo_desktop(task)`. Claude Code should
be set up with `uv run holo install claude-code` from the holo-desktop-cli checkout.
Do not configure or launch a project-local QA MCP server, and do not use a
separate QA runner; this example intentionally has one desktop-agent path.

## Workflow

1. Ensure the Nimbus Desk dev server is running on `http://localhost:5173`. If
   it is not, start `npm run dev` in the background from this directory and wait
   until `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173` returns
   `200`.
2. Pick the closest spec from `qa/*.md`. If the user names a spec, use exactly
   that file. Otherwise map the request by filename and H1 title: `chat-*`
   covers the support chat widget, `auth-*` covers login/session behavior, and
   `tickets-*` covers the ticket list.
3. Read the full markdown spec, including YAML frontmatter. Use the `url`,
   `viewport`, `timeout_s`, and `credentials` fields when composing the Holo
   task.
4. Call `holo_desktop(task)` once with a self-contained task using the template
   below. Wait for the final result.
5. Treat the Holo report as the UI evidence. Do not manually browse the app as a
   substitute. Quote failures verbatim.
6. If asked to fix a failed flow, fix the app code, then rerun the same spec
   once. If the rerun still fails, stop and summarize both reports.

## Holo task template

```text
You are a meticulous read-only black-box QA tester for Nimbus Desk.
Judge only what is visible on screen. Do not open developer tools, read source
code, inspect the DOM, or fix anything. Your job ends at observing and
reporting.

Ensure a Chromium-based browser is open with an incognito/private window showing
<spec url>. Reuse an incognito/private window that is already there; otherwise
open a new one and navigate to that URL. Make the window roughly <viewport> or
larger.

If a sign-in page appears at any point, sign in with these test credentials:
<credentials from spec, if present>

Form hygiene: if a browser autofill or password-manager dropdown appears over a
form, press Escape to dismiss it before clicking. After clicking a form field,
confirm the caret is in that field. After typing into a field, visually confirm
it contains exactly the expected text before moving on. If it does not, select
all and retype.

Follow the Task steps in order. Judge strictly against the Verification rules:
a missing error message or a hung spinner is a failure even if nothing crashed.
Quote on-screen error text verbatim in failure reports.

You are executing this behavioral QA test:

<paste the full qa/*.md spec contents here>

You have <timeout_s> seconds. When done, or when a Verification rule is
conclusively violated, answer with a concise QA report:

VERDICT: PASSED or VERDICT: FAILED
Steps performed
Failures with exact on-screen text
Notes
```

The first line of the report must be exactly `VERDICT: PASSED` or
`VERDICT: FAILED`.

## Demo discipline

Implement requested product changes before searching for unrelated known bugs.
Let Holo QA surface regressions from behavior. Do not edit files in `qa/` to
make a failure pass.
