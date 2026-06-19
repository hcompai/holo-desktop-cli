# Security Policy

Holo drives real apps on your machine, so a bug here can do more damage than in most tools. If you've found one, thanks for telling us carefully.

## Reporting a vulnerability

**Please don't open a public issue or PR for a security problem.** Report it privately instead:

- **Preferred:** [open a private advisory](https://github.com/hcompai/holo-desktop-cli/security/advisories/new) via GitHub ("Report a vulnerability" on the repo's Security tab).
- **Or email:** [compliance@hcompany.ai](mailto:compliance@hcompany.ai).

Include enough to reproduce it: what you did, what happened, the platform, and a proof-of-concept if you have one.

We'll acknowledge your report within 3 business days and keep you posted as we work on a fix. Please give us reasonable time to ship one before disclosing publicly. We're happy to credit you once it's resolved, unless you'd rather stay anonymous.

## Supported versions

Holo is pre-1.0 and moving fast, so security fixes land on the latest released version only. Upgrade to the newest release before reporting.

## What's in scope

This repository is the **Apache-2.0-licensed `holo-desktop-cli` client**: the CLI and the MCP / ACP / A2A surfaces that launch and drive the agent. The agent itself runs inside the closed `hai-agent-runtime` binary, and the two talk over the open [`hai-agent-api`](https://pypi.org/project/hai-agent-api/) contract.

Report client vulnerabilities here. Issues in the runtime binary or the hosted H Company service reach us through the same channels above, so when in doubt, just send it.

## Security model

A few things below are deliberate, not bugs. Worth knowing before you file:

- **Local API is loopback-only.** The agent API binds `127.0.0.1` and is gated by a per-run bearer token, written owner-only (`0600`, `O_NOFOLLOW`) to `~/.holo/agent-token-<port>`. It isn't meant to be reachable off the machine.
- **Runtime downloads are verified.** The `hai-agent-runtime` binary is fetched over HTTPS (plain HTTP is allowed only against loopback, for local dev), checked against a pinned sha256, and served from an immutable, version-scoped CDN prefix that's never overwritten.
- **The runtime can see your screen and act for you.** On macOS it needs Accessibility and Screen Recording: it takes screenshots and synthesizes clicks and keystrokes while a task runs. That's the whole point of the product, not a vulnerability.
- **Local-model mode stays local.** With `--base-url` pointing at your own server, screenshots, keystrokes, and app content never leave the machine, and the hosted `HAI_API_KEY` is stripped from the runtime's environment so it can't leak to a self-hosted endpoint.

Findings that bypass or weaken any of the first two (loopback isolation, download verification) are very much in scope.
