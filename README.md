<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-dark.gif?raw=true" />
    <img src="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-light.gif?raw=true" alt="HoloDesktop CLI" width="800" />
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/holo-desktop-cli/"><img src="https://img.shields.io/pypi/v/holo-desktop-cli?label=holo-desktop-cli" alt="holo-desktop-cli on PyPI" /></a>
  <a href="https://github.com/hcompai/hai-agents-python"><img src="https://img.shields.io/pypi/v/hai-agents?label=hai-agents%20SDK" alt="hai-agents SDK on PyPI" /></a>
  <a href="https://hub.hcompany.ai/holo-desktop-cli"><img src="https://img.shields.io/badge/docs-hub.hcompany.ai-blue" alt="Docs" /></a>
  <a href="https://hub.hcompany.ai/agents-api/introduction"><img src="https://img.shields.io/badge/Agents%20API-docs-blue" alt="Agents API docs" /></a>
  <a href="https://github.com/hcompai/holo-desktop-cli/actions/workflows/ci.yml"><img src="https://github.com/hcompai/holo-desktop-cli/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License: Apache-2.0" /></a>
</p>

> [!NOTE]
> **HoloDesktop CLI is now part of the [Agents API](https://hub.hcompany.ai/agents-api/introduction).** Since 1.0.0, `holo` is a thin shell over the [`hai-agents-python`](https://github.com/hcompai/hai-agents-python) SDK's [local mode](https://hub.hcompany.ai/agents-api/local-mode): the same desktop agent, runnable from Python, from the `hai` CLI, or from the cloud. Keep using `holo` for your terminal and MCP hosts; reach for the SDK to build on it.

Tell your computer what to do. Holo gets it done. `holo-desktop-cli` puts H Company's [Holo](https://huggingface.co/Hcompany) desktop agent on your machine, as a CLI and an MCP server. Use the hosted models, or run everything on your own hardware for full privacy.

**Docs:** [hub.hcompany.ai/holo-desktop-cli](https://hub.hcompany.ai/holo-desktop-cli) has the setup guides, examples, troubleshooting, host integrations, and the full CLI reference.

## Quickstart

```bash
curl -fsSL https://install.hcompany.ai/install.sh | bash   # Windows: irm https://install.hcompany.ai/install.ps1 | iex
holo login
holo run "Open Calculator and compute 2+2"
```

On first run, the `hai-agent-runtime` binary downloads itself to `~/.hai/agent-runtime/` (sha256-verified), and macOS asks you to grant your terminal *Accessibility* and *Screen Recording*. See `holo run --help` or the [CLI reference](https://hub.hcompany.ai/holo-desktop-cli/reference/cli) for all flags.

## Stopping the agent

Once the agent is driving the screen it is hard to take back control, so Holo has an out-of-band panic stop: **press `Esc` twice quickly**, or run `holo stop` from any terminal. `holo run` arms the `Esc` listener itself; for `holo mcp`, which has no terminal, `holo install` registers the always-on `holo guard` with the OS. The listener inspects `Esc` timing only, never keystroke content. Wayland has no global key listener; bind `holo stop` to a compositor hotkey.

## Run the model yourself

Point `--base-url` at any OpenAI-compatible server and name the model it serves with `--model`. No `holo login` needed, and no screenshots, keystrokes, or app content leave your machine.

```bash
holo run --base-url http://localhost:8000/v1 --model holo4-35b-a3b "Open Safari and go to hcompany.ai"
```

Serving configs are in [docs/self-hosting.md](docs/self-hosting.md).

## Use inside another agent

Holo runs as a sub-agent of Claude Code, Cursor, Codex, and other [MCP](https://modelcontextprotocol.io) hosts: when your main agent needs to read a screen or click through an app, it delegates to Holo and gets the answer back.

```bash
holo install               # every host detected on this machine
holo install cursor        # one host
holo install list          # see what's available
```

Each host gets the MCP server in its config, plus a [Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) where supported, which teaches the parent when to delegate to Holo.

| id              | host                                                            | skill auto-load              |
| --------------- | --------------------------------------------------------------- | ---------------------------- |
| `antigravity`   | [Antigravity](https://antigravity.google) (Google)              | —                            |
| `claude-code`   | [Claude Code](https://docs.anthropic.com/en/docs/claude-code)   | `~/.claude/skills/`          |
| `claude-desktop`| [Claude Desktop](https://claude.ai/download)                    | —                            |
| `codex`         | [Codex](https://github.com/openai/codex)                        | `~/.agents/skills/`          |
| `copilot`       | [GitHub Copilot CLI](https://github.com/github/copilot-cli)     | —                            |
| `cursor`        | [Cursor](https://cursor.com)                                    | —                            |
| `grok-build`    | [Grok Build](https://github.com/xai-org/grok-build) (xAI)       | `~/.grok/skills/`            |
| `hermes`        | [Hermes](https://nousresearch.com)                              | —                            |
| `openclaw`      | [OpenClaw](https://github.com/openclaw/openclaw)                | `~/.openclaw/skills/`        |
| `opencode`      | [OpenCode](https://opencode.ai)                                 | `~/.config/opencode/skills/` |

Holo drives one desktop: parallel MCP calls queue, and a second `holo run` exits while another task is driving. Stopping the turn in the host does not abort a run already executing on your machine; use the kill switch.

## Use from Python

`holo` is a thin shell over the [`hai-agents`](https://pypi.org/project/hai-agents/) SDK, so you can drive the same agent directly:

```python
from hai_agents import Client

with Client.local() as client:
    result = client.run_session(
        agent={
            "name": "holo",
            "description": "Desktop agent",
            "environments": [{"id": "desktop", "kind": "desktop", "host": "user_device"}],
        },
        messages="Tell me how many unread emails I have",
    )
    print(result.answer)
```

The same agent runs in the cloud, alongside browsers and workstations, through the [Agents API](https://hub.hcompany.ai/agents-api/introduction).

## Develop

```bash
git clone https://github.com/hcompai/holo-desktop-cli && cd holo-desktop-cli
make setup
uv run holo run "Open Calculator and compute 2+2"
make check   # ruff + mypy + pytest
```

`make install-dev` installs the checkout as a global `holo` command. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

This client is [Apache-2.0-licensed](LICENSE). The [`hai-agents`](https://pypi.org/project/hai-agents/) SDK it builds on is open source. The `hai-agent-runtime` binary the SDK downloads, which hosts the agent, is closed-source and distributed under H Company's own terms.

## Resources

- Models: [Holo on Hugging Face](https://huggingface.co/Hcompany)
- Docs: [HoloDesktop CLI](https://hub.hcompany.ai/holo-desktop-cli) · [Agents API](https://hub.hcompany.ai/agents-api/introduction) · [Models API](https://hcompany.ai/holo-models-api)
- [H Company](https://hcompany.ai)
