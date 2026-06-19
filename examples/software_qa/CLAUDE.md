# Claude Code Notes

Follow `AGENTS.md` in this directory.

When asked to verify UI behavior, run a behavioral spec, check a regression, or
confirm a UI fix, use the local `holo-qa` skill. The skill calls the normal root
Holo MCP tool, `holo_desktop(task)`.

Set up Claude Code with `uv run holo install claude-code` from the holo-desktop-cli
checkout. Do not configure or launch a project-local QA MCP server for this
example. Do not use a Python QA runner; this demo intentionally has one
desktop-agent path.
