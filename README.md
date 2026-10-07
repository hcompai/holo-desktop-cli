<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-dark.gif?raw=true" />
    <img src="https://github.com/hcompai/holo-desktop-cli/blob/main/assets/banner-light.gif?raw=true" alt="HoloDesktop CLI" width="800" />
  </picture>
</p>

<p align="center">
  <a href="https://github.com/hcompai/holo-desktop-cli/actions/workflows/ci.yml"><img src="https://github.com/hcompai/holo-desktop-cli/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="https://codecov.io/gh/hcompai/holo-desktop-cli"><img src="https://codecov.io/gh/hcompai/holo-desktop-cli/branch/main/graph/badge.svg" alt="Coverage" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License: Apache-2.0" /></a>
</p>

Tell your computer what to do. Holo gets it done. `holo-desktop-cli` puts H Company's [Holo](https://huggingface.co/Hcompany) desktop agent on your machine, as a CLI and an MCP server. It is a thin shell over the [`hai-agents`](https://pypi.org/project/hai-agents/) SDK local mode. Use the hosted API, or run everything on your own machine for full privacy.

**Docs:** The [HoloDesktop CLI docs](https://hub.hcompany.ai/holo-desktop-cli) cover setup guides, run examples, debugging advice, integration guides, and the full CLI reference.

## What's open, what's closed

Holo is three parts:

- **This repo, `holo-desktop-cli`,** is the [Apache-2.0-licensed](LICENSE) client: the CLI plus the MCP server.
- **The [`hai-agents`](https://pypi.org/project/hai-agents/) SDK** (open source) starts the agent runtime and drives your desktop from this process.
- **The agent** runs inside H Company's `hai-agent-runtime` binary. That binary is closed-source and downloads itself on first run (sha256-verified).

Point it at the hosted Holo models, or at [your own server](docs/self-hosting.md) where nothing leaves your machine.

## Quickstart

Install Holo with the consumer installer:

```bash
curl -fsSL https://install.hcompany.ai/install.sh | bash
holo login
holo run "Open Calculator and compute 2+2"
```

On Windows x86_64:

```powershell
irm https://install.hcompany.ai/install.ps1 | iex
holo login
holo run "Open Calculator and compute 2+2"
```

On first run:

1. The installer sets up a private Holo toolchain under `~/.holo/` and exposes `holo` on your shell `PATH`.
2. The `hai-agent-runtime` binary downloads itself to `~/.hai/agent-runtime/` (sha256-verified). Developers can skip this by putting `hai-agent-runtime` (or a wrapper script) on `PATH`.
3. Your browser opens to sign in at [portal.hcompany.ai](https://portal.hcompany.ai). Skip with `--base-url` for a local model.
4. macOS only: grant your terminal *Accessibility* and *Screen Recording* in *System Settings → Privacy & Security* when prompted.

## Two ways to use Holo

| Surface | Command | When |
| ------- | ------- | ---- |
| CLI     | `holo run "task"` | One-shot tasks from your terminal |
| MCP     | `holo install`, or `holo mcp` in your host's config | Delegate from Claude Code, Cursor, Codex, ... |

See the [CLI reference](https://hub.hcompany.ai/holo-desktop-cli/reference/cli) or `holo run --help` for all flags.

## Stopping the agent (kill switch)

Once the agent is driving the screen it's hard to take back control. Holo gives you an out-of-band panic stop: **press `Esc` twice quickly** and the running task cancels.

| Where you're running | What watches for the double-`Esc` |
| -------------------- | --------------------------------- |
| `holo run` (interactive terminal) | A listener embedded in the run; armed automatically (first use prompts for macOS Input Monitoring). |
| `holo mcp` (headless) | The always-on `holo guard`, installed by `holo install` and launched by the OS so it has its own permission identity. |

You can also stop without the keyboard:

```bash
holo stop          # cancel the running task (same as double-Esc)
holo guard         # run the listener yourself in the foreground (e.g. if you skipped holo install)
```

All three write a timestamp to `~/.config/hai/stop`; a running task cancels when it sees a stop filed after it started, so a stale stop never kills the next task. The guard only inspects `Esc` timing, never keystroke content, but it holds Input Monitoring while installed. Disable the embedded listener for one run with `holo run --no-kill-switch`.

## Use from Python

Use the [`hai-agents`](https://pypi.org/project/hai-agents/) SDK directly; `holo` is a thin shell over its local mode:

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

## Models

Holo defaults to the [H Company Models API](https://hcompany.ai/holo-models-api). Your first `holo run` opens your browser, signs you in at [portal.hcompany.ai](https://portal.hcompany.ai), and saves a key to `~/.config/hai/.env` (shared with the `hai` CLI). Run `holo login` to do this ahead of time.

To run on your own hardware instead, point `--base-url` at any OpenAI-compatible server and name the model it serves with `--model`. No `holo login` needed, and no screenshots, keystrokes, or app content leave your machine.

```bash
holo run --base-url http://localhost:8000/v1 --model holo4-35b-a3b "Open Safari and go to hcompany.ai"
```

Serving configs are in [docs/self-hosting.md](docs/self-hosting.md).

## Use inside another agent

Holo runs as a sub-agent of Claude Code, Cursor, Codex, and other [MCP](https://modelcontextprotocol.io) hosts. When your main agent needs to read a screen or click through an app, it delegates to Holo and gets the answer back.

One command wires Holo into every supported host on your machine:

```bash
holo install               # everything detected
holo install cursor        # one host
holo install list          # see what's available
```

Each host gets the MCP server in its config, plus a [Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) (where supported) that teaches the parent when to delegate to Holo.

> **Interrupting a running task:** over MCP a Holo task blocks until it finishes — stopping the turn in the host (Cursor, Codex, ...) does not abort the run already executing on your machine; it keeps clicking until it completes, times out, or the host kills the server process. Stop it with a double `Esc` or `holo stop`.

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
| `nemoclaw`      | NemoClaw (sandbox bridge)                                       | —                            |
| `openclaw`      | [OpenClaw](https://github.com/openclaw/openclaw)                | `~/.openclaw/skills/`        |
| `opencode`      | [OpenCode](https://opencode.ai)                                 | `~/.config/opencode/skills/` |

## Develop

All dependencies resolve from PyPI, so a plain checkout is all you need:

```bash
git clone https://github.com/hcompai/holo-desktop-cli && cd holo-desktop-cli
make setup
uv run holo run "Open Calculator and compute 2+2"
make check   # ruff + mypy + pytest
```

If you want a global command while developing, install the checkout in editable tool mode:

```bash
make install-dev
holo --help
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

The `holo-desktop-cli` client (this repository) is [Apache-2.0-licensed](LICENSE). The `hai-agent-runtime` binary the SDK downloads is closed-source and distributed under H Company's own terms.

## Resources

- Models: [Holo on Hugging Face](https://huggingface.co/Hcompany)
- Docs: [Quickstart](https://hub.hcompany.ai/quickstart) · [Models API](https://hcompany.ai/holo-models-api)
- [H Company](https://hcompany.ai)
