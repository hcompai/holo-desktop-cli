"""One-release compatibility with pre-SDK ~/.holo cross-process state.

Pre-SDK holo published ~/.holo/agent-token-<port> and ~/.holo/agent-pid-<port>;
the SDK owns discovery state now. This module only lets an upgraded holo stop a
runtime a pre-SDK holo spawned. DELETE this module (and its call sites in
stop.py/doctor.py) in the release after SDK local mode ships.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".holo"


def pid_file_path(port: int) -> Path:
    """Where a spawner publishes the runtime pid so ``holo stop --force`` can signal it."""
    return TOKEN_DIR / f"agent-pid-{port}"


def read_pid_file(port: int) -> int | None:
    """The spawned runtime's pid for ``port``, or None when no readable pid file exists."""
    try:
        return int(pid_file_path(port).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    except OSError as exc:
        logger.warning("could not read pid file %s: %s", pid_file_path(port), exc)
        return None


def discover_runtime_pids(port: int | None) -> list[int]:
    """Pids of spawned runtimes from pid files: one ``port``, or every spawned runtime when None.

    Gotcha: a runtime that exits uncleanly (crash/SIGKILL) leaves its pid file behind, so a later
    ``holo stop --force`` can SIGKILL a recycled pid. There is no proof-of-identity check yet; the
    robust fix (match the process start time) is tracked as follow-up.
    """
    if port is not None:
        pid = read_pid_file(port)
        return [pid] if pid is not None else []
    pids: list[int] = []
    for path in sorted(TOKEN_DIR.glob("agent-pid-*")):
        try:
            pids.append(int(path.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    return pids


def _killpg_posix(pid: int, sig: int) -> bool:
    """Send ``sig`` to ``pid``'s process group; False if the process/group is already gone."""
    try:
        os.killpg(os.getpgid(pid), sig)
    except (OSError, ProcessLookupError):
        return False
    return True


def kill_runtime_by_pid(pid: int) -> bool:
    """Force-kill the runtime's process group by pid; False if it was already gone."""
    if os.name == "posix":
        return _killpg_posix(pid, signal.SIGKILL)
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def legacy_force_kill(port: int | None) -> list[int]:
    """SIGKILL every pre-SDK runtime pid file records for ``port`` (all ports when None)."""
    return [pid for pid in discover_runtime_pids(port) if kill_runtime_by_pid(pid)]
