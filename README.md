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

Tell your computer what to do. Holo gets it done. `holo-desktop-cli` is the open-source client for [Holo3](https://huggingface.co/Hcompany/Holo3-35B-A3B), H Company's open-weight vision-language model. It launches the agent and fronts it as a CLI, MCP, ACP, and A2A surface. Use the hosted API, or run everything on your own machine for full privacy.

**Docs:** The [HoloDesktop CLI docs](https://hub.hcompany.ai/holo-desktop-cli) cover setup guides, run examples, debugging advice, integration guides, and the full CLI reference.

## What's open, what's closed

Holo is three parts:

- **This repo, `holo-desktop-cli`,** is the [Apache-2.0-licensed](LICENSE) client: the CLI plus the MCP / ACP / A2A surfaces. It launches the agent and drives it over loopback.
- **The agent** runs inside H Company's `hai-agent-runtime` binary. That binary is closed-source and downloads itself on first run (sha256-verified).
- **The contract between them** is the open [`hai-agent-api`](https://pypi.org/project/hai-agent-api/) package, so what the client sends is fully inspectable.

Point it at the hosted [Holo3](https://huggingface.co/Hcompany/Holo3-35B-A3B) models, or at [your own server](docs/self-hosting.md) where nothing leaves your machine.

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
2. The `hai-agent-runtime` binary downloads itself to `~/.holo/runtime/` (sha256-verified). Developers can skip this by putting `hai-agent-runtime` (or a wrapper script) on `PATH`.
3. Your browser opens to sign in at [portal.hcompany.ai](https://portal.hcompany.ai). Skip with `--base-url` for a local model.
4. macOS only: grant the agent runtime *Accessibility* and *Screen Recording* in *System Settings → Privacy & Security* when prompted.

## Four ways to use Holo

| Surface | Command | When |
| ------- | ------- | ---- |
| CLI     | `holo run "task"` | One-shot tasks from your terminal |
| MCP     | `holo install`, or `holo mcp` in your host's config | Delegate from Claude Code, Cursor, Codex, ... |
| ACP     | `holo acp` | [ACP](https://agentclientprotocol.com) hosts (Hermes, OpenClaw, Zed, ...) |
| A2A     | `holo serve` | An [A2A](https://a2a-protocol.org) HTTP server on `127.0.0.1` for your own agents |

See the [CLI reference](https://hub.hcompany.ai/holo-desktop-cli/reference/cli) or `holo run --help` for all flags.

## Stopping the agent (kill switch)

Once the agent is driving the screen it's hard to take back control. Holo gives you an out-of-band panic stop: **press `Esc` twice quickly** and the current turn pauses, then cancels.

| Where you're running | What watches for the double-`Esc` |
| -------------------- | --------------------------------- |
| `holo run` (interactive terminal) | A listener embedded in the run; armed automatically (first use prompts for macOS Input Monitoring). |
| `holo mcp` / `holo acp` / `holo serve` (headless) | The always-on `holo guard`, installed by `holo install` and launched by the OS so it has its own permission identity. |

You can also stop without the keyboard:

```bash
holo stop          # ask the running turn to pause then cancel (same as double-Esc)
holo stop --force  # additionally SIGKILL the runtime — instant, but ends the session outright
holo guard         # run the listener yourself in the foreground (e.g. if you skipped holo install)
```

Good to know:

- **The stop is step-bounded.** It halts the *next* action; the runtime still finishes the action already in flight. `holo stop --force` is the only instant stop.
- **`holo stop --force` kills the runtime but leaves a headless host running with a dead backend.** `holo serve` / `holo mcp` / `holo acp` spawn their runtime once at startup and keep pointing at it, so after a force-kill the host process stays up but every later task fails (its requests hit a runtime that no longer exists) until you restart the host. Prefer plain `holo stop` there; reserve `--force` for `holo run` or a wedged runtime.
- **The guard only inspects `Esc` timing**, never keystroke content — but it does hold Input Monitoring continuously while installed. Disable the embedded listener for a single run with `holo run --no-kill-switch`.
- **`holo stop --force` reads a pid file and does not yet verify process identity.** A runtime that exited uncleanly can leave a stale `~/.holo/agent-pid-<port>` behind, so a force-kill may target a recycled pid. Robust start-time matching is tracked as follow-up.
- **Wayland (Linux) has no global key listener.** Use `holo stop` instead, bound to a compositor hotkey.

### How the stop signal works

The trigger and the lever are decoupled through a single one-line file, `~/.holo/stop`, holding a **wall-clock timestamp**:

- **Writing it (the trigger):** `holo stop`, the `holo run` listener, and `holo guard` all write `time.time()` to that file. They're separate processes, so a wall-clock value is what lets them and the running turn agree on ordering.
- **Reading it (the lever):** every turn records its own `started_at` and, while running, polls the file ~4×/s. It acts **only if the file's timestamp is newer than its `started_at`** — then it pauses, then cancels at the next action boundary.
- **Clearing it:** the file is *never deleted*. It's cleared by time — the next turn starts later, so a leftover request is automatically stale and can't kill it. This is also why a `holo stop` fired *before* a run begins is ignored: nothing was running to stop.

`holo stop --force` is the exception to the step-bounded model: it reads the runtime's pid file (`~/.holo/agent-pid-<port>`) and SIGKILLs the process directly, so it doesn't wait for an action boundary.

## Use from Python

`holo_desktop.agent_client` is the same client every CLI surface is built on: it spawns (or attaches to) the `hai-agent-runtime` binary on loopback and drives sessions over the agent API.

```python
import asyncio

from holo_desktop.agent_client import AgentApiClient, SpawnConfig, ensure_running
from holo_desktop.agent_client.requests import build_session_request


async def main() -> None:
    daemon = await ensure_running(SpawnConfig(port=18795))
    try:
        async with AgentApiClient(daemon.base_url, daemon.token) as client:
            request = build_session_request(
                task="Tell me how many unread emails I have", max_steps=None, max_time_s=None
            )
            stream = client.stream(await client.create_session(request))
            async for event in stream.events():
                print(event.type)
            print(stream.answer)
    finally:
        await daemon.aclose()


asyncio.run(main())
```

`AgentApiClient` also exposes `pause` / `resume` / `cancel` and mid-run `send_message` for interactive embedding.

## Models

Holo defaults to the [H Company Models API](https://hcompany.ai/holo-models-api). Your first `holo run` opens your browser, signs you in at [portal.hcompany.ai](https://portal.hcompany.ai), and saves a key to `~/.holo/.env`. Run `holo login` to do this ahead of time. Holo3-35B is on the free tier; the 122B requires a paid plan.

To run on your own hardware instead, point `--base-url` at any OpenAI-compatible server. No `holo login` needed, and no screenshots, keystrokes, or app content leave your machine.

```bash
holo run --base-url http://localhost:8000/v1 "Open Safari and go to hcompany.ai"
```

Hardware notes and ready-to-run vLLM and llama.cpp configs are in [docs/self-hosting.md](docs/self-hosting.md).

## Use inside another agent

Holo runs as a sub-agent of Claude Code, Cursor, Codex, and other [MCP](https://modelcontextprotocol.io) / [ACP](https://agentclientprotocol.com) hosts. When your main agent needs to read a screen or click through an app, it delegates to Holo and gets the answer back.

One command wires Holo into every supported host on your machine:

```bash
holo install               # everything detected
holo install cursor        # one host
holo install list          # see what's available
```

Each host gets the MCP server in its config, plus a [Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) (where supported) that teaches the parent when to delegate to Holo.

> **Interrupting a running task:** over MCP a Holo task blocks until it finishes — stopping the turn in the host (Cursor, Codex, ...) does not abort the run already executing on your machine; it keeps clicking until it completes, times out, or the host kills the server process. Use [ACP](#acp) if you need a host-driven cancel.

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

### ACP

> **Beta.** ACP support is still stabilising — interfaces and behaviour may change. `holo acp` prints this notice to stderr on startup.

`holo acp` runs Holo as an [ACP](https://agentclientprotocol.com) sub-agent over stdio. Unlike MCP, ACP hosts can cancel an in-flight task.

**Hermes** ([NousResearch](https://github.com/NousResearch/hermes-agent)):

```python
delegate_task(acp_command="holo acp", task="Open Authy and grab my AWS 2FA code")
```

**OpenClaw** — `~/.openclaw/openclaw.json`:

```json
{ "runtimes": { "holo": { "runtime": "acp-standard", "command": "holo", "args": ["acp"] } } }
```

## Develop

All dependencies resolve from PyPI (the agent-API wire types come from `hai-agent-api`), so a plain checkout is all you need:

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

The `holo-desktop-cli` client (this repository) is [Apache-2.0-licensed](LICENSE). The `hai-agent-runtime` binary it downloads and drives is closed-source and distributed under H Company's own terms; the wire contract between the two is the open [`hai-agent-api`](https://pypi.org/project/hai-agent-api/) package.

## Resources

- Models: [Holo3-35B-A3B](https://huggingface.co/Hcompany/Holo3-35B-A3B) · [Holo3-122B-A10B](https://huggingface.co/Hcompany/Holo3-122B-A10B)
- Docs: [Quickstart](https://hub.hcompany.ai/quickstart) · [Models API](https://hcompany.ai/holo-models-api)
- [H Company](https://hcompany.ai)
