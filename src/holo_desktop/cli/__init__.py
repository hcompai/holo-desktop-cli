"""Holo CLI dispatcher."""

import contextlib
import io
import sys

import tyro

from holo_desktop.cli.agent_api import agent_api
from holo_desktop.cli.doctor import doctor
from holo_desktop.cli.guard import guard
from holo_desktop.cli.install import install
from holo_desktop.cli.login import login
from holo_desktop.cli.retina_proxy import retina_proxy
from holo_desktop.cli.run import run
from holo_desktop.cli.serve import serve
from holo_desktop.cli.stop import stop
from holo_desktop.cli.whoami import whoami

# Lazy wrappers: keep the heavy ACP/MCP SDK imports off every `holo` invocation.
# Docstrings mirror the real entrypoints; tyro reads them for `holo --help`.


def acp() -> None:
    """Run as a stdio ACP server. Spawns the hai-agent-runtime binary on first use."""
    from holo_desktop.cli.acp import acp as _acp

    _acp()


def mcp() -> None:
    """Run as a stdio MCP server. Auto-spawns the hai-agent-runtime binary if none is listening."""
    from holo_desktop.cli.mcp import mcp as _mcp

    _mcp()


def _ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr so Rich glyphs survive Windows cp1252 consoles and CI runners."""
    for stream in (sys.stdout, sys.stderr):
        # Replaced streams (pytest capture, wrapped pipes) may not be TextIOWrapper; only it supports reconfigure.
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _ensure_utf8_stdio()
    tyro.extras.subcommand_cli_from_dict(
        {
            "run": run,
            "stop": stop,
            "guard": guard,
            "serve": serve,
            "agent-api": agent_api,
            "mcp": mcp,
            "acp": acp,
            "install": install,
            "login": login,
            "whoami": whoami,
            "doctor": doctor,
            "retina-proxy": retina_proxy,
        },
    )
