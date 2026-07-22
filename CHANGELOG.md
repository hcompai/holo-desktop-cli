# Changelog

Notable changes per release. Versions follow [SemVer](https://semver.org). Dates are UTC.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.0.4] - 2026-07-22

- Fixed the Windows installer incorrectly rejecting x86_64 systems when PSReadLine shadows .NET's architecture information type.

## [0.0.1] - Unreleased

Initial public release.

`holo-desktop-cli` is an Apache-2.0-licensed thin client for [Holo3](https://huggingface.co/Hcompany/Holo3-35B-A3B): it launches H Company's closed `hai-agent-runtime` binary on loopback and drives it over the open [`hai-agent-api`](https://pypi.org/project/hai-agent-api/) HTTP contract.

- **Four surfaces.** `holo run` (one-shot CLI), `holo serve` (A2A on `127.0.0.1`), `holo mcp`, and `holo acp` — every surface speaks the same agent API.
- **Download-on-first-run.** When `hai-agent-runtime` is not on `PATH`, the client streams the pinned version to `~/.holo/runtime/<version>/`, sha256-verified and atomically installed.
- **Host wiring.** `holo install` wires Holo into supported MCP/ACP hosts (Claude Code, Cursor, Codex, Hermes, OpenClaw, OpenCode, ...), with SKILL.md auto-load where supported.
- **Kill switch.** Double-`Esc` (or `holo stop`) pauses then cancels the running turn; `holo guard` provides an always-on listener for headless hosts.
- **Models.** Hosted [H Company Models API](https://hcompany.ai/holo-models-api) by default (`holo login`), or `--base-url` to point at a self-hosted OpenAI-compatible server.
- macOS (Apple Silicon) and Windows ship managed runtime artifacts; macOS Intel and Linux work with a `hai-agent-runtime` on `PATH`.

[0.0.1]: https://github.com/hcompai/holo-desktop-cli/releases/tag/v0.0.1
[0.0.4]: https://github.com/hcompai/holo-desktop-cli/releases/tag/v0.0.4
