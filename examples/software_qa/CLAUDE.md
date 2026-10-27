# Claude Code Notes

Follow `AGENTS.md` in this directory.

When asked to verify UI behavior, run a behavioral spec, check a regression, or
confirm a UI fix, use the local `holo-qa` skill. The skill calls the normal root
Holo MCP tool, `run_agent(task, agent="h/holo-desktop")`.

Set up Claude Code with `holo mcp install claude-code`. Do not configure or launch a project-local QA MCP server for this
example. Do not use a Python QA runner; this demo intentionally has one
desktop-agent path.
