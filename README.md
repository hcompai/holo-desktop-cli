<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-dark.gif?raw=true" />
    <img src="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-light.gif?raw=true" alt="HoloDesktop CLI" width="800" />
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/hai-agents/"><img src="https://img.shields.io/pypi/v/hai-agents?label=hai-agents" alt="hai-agents on PyPI" /></a>
  <a href="https://hub.hcompany.ai/agents-api/cli"><img src="https://img.shields.io/badge/docs-Holo%20CLI-blue" alt="Holo CLI docs" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License: Apache-2.0" /></a>
</p>

> [!IMPORTANT]
> **HoloDesktop CLI is now part of the [Agents API](https://hub.hcompany.ai/agents-api/introduction).** The `holo` command ships with the [`hai-agents`](https://github.com/hcompai/hai-agents-python) Python SDK. This package installs it.

## Install

```bash
curl -fsSL https://install.hcompany.ai/install.sh | bash   # Windows: irm https://install.hcompany.ai/install.ps1 | iex
```

Or with pip: `pip install -U "hai-agents[cli,workstation]>=1.4.0"`.

## Drive your desktop

```bash
holo login
holo -a h/holo-desktop "Open Calculator and compute 2+2"
```

Make it the default, so `holo "task"` drives your desktop:

```bash
holo agents use h/holo-desktop
```

Stop a run: press `Esc` twice, or run `holo local stop`.

On macOS, grant Screen Recording, Accessibility, and Input Monitoring to the app that starts `holo`. Details: [Desktop permissions](https://hub.hcompany.ai/agents-api/cli#desktop-permissions).

## Use it from coding agents

```bash
holo mcp install
```

Claude Code, Cursor, and Codex get a `run_agent` tool. Pass `agent="h/holo-desktop"` to drive your desktop. Guide: [Integrate with coding agents](https://hub.hcompany.ai/agents-api/coding-agents).

## Run locally, or with your own model

```bash
holo --local -a h/holo-desktop "Open TextEdit and write a short note"
```

`--local` runs the agent loop on this machine. To also run the model yourself, see [Run the model yourself](https://hub.hcompany.ai/agents-api/cli#run-the-model-yourself).

## Customize every run

- `~/.holo/agents.md`: standing instructions.
- `~/.holo/skills/<name>/SKILL.md`: your skills.

See [Customize every run](https://hub.hcompany.ai/agents-api/cli#customize-every-run).

## Upgrading from 1.0

| 1.0 | Now |
| --- | --- |
| `holo run "task"` | `holo -a h/holo-desktop "task"` |
| `holo run --model <id> "task"` | `holo -a h/holo-desktop -o agent.model=<id> "task"` |
| `holo run --base-url <your server>` | `HAI_AGENT_RUNTIME_BASE_URL=<your server> holo --local -a h/holo-desktop` (still needs `holo login`) |
| `holo install <host>` | `holo mcp install` |
| `holo stop` | `holo local stop` |
| `holo guard` | Built in: `Esc` twice during a run |
| MCP tool `holo_desktop` | `run_agent` with `agent="h/holo-desktop"` |
| `~/.holo/memories.md`, `rules.md` | `~/.holo/agents.md` |

After upgrading:

1. Run `holo login` again.
2. Run `holo mcp install` to refresh your coding agents.
3. Skills that 1.0 copied into `~/.holo/skills` now apply to every agent. Delete the ones you don't want.
4. Delete the old `holo-desktop` skill links from `~/.claude/skills`, `~/.agents/skills`, and your other agents' skill folders.

The installer removes the old `holo guard` login item. With pip, remove it yourself: `~/Library/LaunchAgents/ai.hcompany.holo.guard.plist` on macOS, `holo-guard.cmd` in your Startup folder on Windows, `~/.config/autostart/holo-guard.desktop` on Linux.

## Docs

- [Holo CLI](https://hub.hcompany.ai/agents-api/cli)
- [Integrate with coding agents](https://hub.hcompany.ai/agents-api/coding-agents)
- [Security and privacy](https://hub.hcompany.ai/agents-api/cli/security)
- [Changelog](https://hub.hcompany.ai/agents-api/changelog)
- [Example: UI QA with a coding agent](https://hub.hcompany.ai/agents-api/cli/example-ui-qa)
