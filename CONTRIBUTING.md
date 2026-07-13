# Contributing

Bug reports, feature ideas, and PRs are welcome. For anything non-trivial, open an issue first so we can sanity-check the direction before you sink time into it.

## Dev setup

```bash
git clone https://github.com/hcompai/holo-desktop-cli && cd holo-desktop-cli
make setup       # uv sync + install pre-commit hooks
uv run holo run "Open hcompany.ai"
```

`make setup` installs the project (editable) plus dev tools (`ruff`, `mypy`, `pre-commit`) into a local `.venv/`. To also provision the workspace examples (`examples/`), run `make setup-examples` — plain `uv sync` installs only the root package.

If you want to run `holo` from arbitrary directories while developing, install the checkout as an editable uv tool:

```bash
make install-dev
holo --help
```

Use the consumer installers (`install/install.sh` and `install/install.ps1`) for release QA and non-developer installs, not for day-to-day editable development. Remove the editable tool with `make uninstall-dev`.

## Before pushing

```bash
make check       # ruff + ruff-format --check + mypy + pytest
```

`make ci` additionally runs the pre-push pre-commit hooks (mypy on changed files). CI runs the same checks against macOS/Linux/Windows.

## Project layout

```
src/holo_desktop/
  agent_client/      launcher + async HTTP client for the hai-agent-runtime agent API
  cli/               `holo` CLI: run, serve, agent-api, mcp, acp, install, login, whoami, doctor
  customization.py   ~/.holo user state (agents.md, memories, rules, skills)
  skills/            bundled SKILL.md, seeded into ~/.holo/skills on first run
  host_skills/       SKILL.md that `holo install` symlinks into MCP hosts
examples/            runnable examples (uv workspace members); see examples/README.md
```
