# Agent Instructions

Nimbus Desk is a small app-under-test for the Holo QA example. When you make a
UI-facing change, verify the relevant user flow with the markdown specs in
`qa/*.md`.

## Holo QA

Use the local `holo-qa` skill for UI QA. It reads `qa/*.md` specs and calls the
normal installed Holo MCP tool, `holo_desktop(task)`. Set up Claude Code with
`uv run holo install claude-code` from the holo-desktop-cli checkout. Do not
configure or launch a project-local QA MCP server for this example, and do not
use a Python QA runner.

The dev server must already be running on `http://localhost:5173`:

```bash
npm run dev
```

Do not manually browse the app as a substitute for Holo QA. The tester's report
is the UI evidence. Do not edit files in `qa/` to make a failure pass.

## Change Workflow

1. Implement the requested product change first.
2. Run the closest QA spec after the change.
3. If the report says `VERDICT: FAILED`, quote the failure, make one minimal
   fix, and re-run the same spec once.
4. If the second run still fails, stop and summarize both reports.

For the demo, do not preemptively search for unrelated known bugs before QA
reports them. The point is to show that black-box behavioral QA catches user
flow regressions that ordinary code edits can miss.
