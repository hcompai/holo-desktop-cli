# QA with Claude Code

This example shows the closed loop between Claude Code and Holo: Claude Code
edits a running app, asks Holo to test the UI through the normal
`holo_desktop(task)` MCP tool, then uses the visible QA report to fix and verify
the source change.

## What you will do

- Run the Nimbus Desk demo app.
- Open Claude Code from the Nimbus workspace.
- Ask Claude Code to make a small Tickets page change.
- Let Claude Code use Holo to run the relevant behavioral QA spec.
- Have Claude Code fix the bug Holo observes and verify the UI again.

## The scenario

Nimbus Desk is a small support dashboard in this directory. Its Tickets page has
a Status dropdown, and the checked-in spec at `qa/tickets-filter.md` says
selecting `Open` should show exactly the open tickets.

The app contains a realistic status-filter bug. The source looks plausible, but
the visible UI behavior is wrong. The demo is meant to show Holo providing UI
evidence while Claude Code diagnoses and patches the source.

## Start Nimbus

From the `holo-desktop-cli` checkout:

```bash
uv sync
cd examples/software_qa
npm install
npm run dev
```

The app runs at `http://localhost:5173`. Demo credentials are shown on the login
page: `demo@nimbus.test / holo-qa-1`.

## Prepare Holo

For hosted mode, sign in once:

```bash
uv run holo login
uv run holo install claude-code
```

This wires the root Holo MCP server into Claude Code.

The checked-in Claude Code skill at `.claude/skills/holo-qa/SKILL.md` teaches
Claude how to choose a spec from `qa/`, compose a self-contained QA task, and
call `holo_desktop(task)`.

## Run the workflow

Open Claude Code from the Nimbus workspace:

```bash
cd examples/software_qa
claude
```

Then ask Claude Code:

```text
Add a Priority dropdown beside the Status dropdown on the Tickets page, with
options All, High, Medium, and Low.

After the change, use the local Holo QA workflow to run the relevant behavioral
spec for the Tickets page. If Holo reports a failure, inspect the source, make
the minimal fix, and rerun the same spec once to verify the UI.

Do not stop after reporting the bug unless you cannot identify a safe fix.
```

Claude Code should implement the product change, run the Tickets QA spec through
Holo, use the failing UI report to find the status-filter bug, patch the source,
and rerun the same spec. The tester report starts with `VERDICT: PASSED` or
`VERDICT: FAILED`; failures quote visible on-screen text.

## Where the pieces live

- `qa/` contains the behavioral specs.
- `.claude/skills/holo-qa/SKILL.md` contains the Claude Code QA workflow.
- `src/pages/Tickets.jsx` contains the seeded Tickets page bug.

## App under test

Nimbus Desk is deliberately small: no backend, no database, no API keys. All
state is in memory or `sessionStorage`, which keeps the QA loop deterministic.

Three "recently shipped features" are under test:

- **Support chat widget**: a scripted assistant with an escalate-to-human flow
  that issues ticket numbers.
- **Auth**: login with inline validation errors, session gating on all pages,
  and logout.
- **Tickets status filter**: the headline sad path for the demo.

Each file in `qa/` is one behavioral test: YAML frontmatter plus `Setup`, `Task`,
`Expected Result`, and `Verification` sections. The tester report starts with
`VERDICT: PASSED` or `VERDICT: FAILED`; failures quote visible on-screen text.

Simulated regressions can be activated with a query parameter, for example:

```text
http://localhost:5173/login?regression=auth-silent-fail
```
