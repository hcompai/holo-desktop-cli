from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TextIO

from holo_desktop.agent_client.launcher import runtime_log_path

from .conftest import HoloLiveConfig

_EVENT_LOG_RE = re.compile(r"events streamed to\s+(.+)")
TIMEOUT_SHUTDOWN_GRACE_S = 10.0


def free_port() -> int:
    """Ephemeral port for one task's agent server, so tasks never share a daemon.

    A shared default port means one timed-out task (whose binary the timeout
    kill orphans) poisons every later task with the attach-refusal error.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def kill_port_listener(port: int) -> None:
    """Kill whatever still listens on ``port`` (the binary a timeout kill orphaned).

    ``holo run`` stops its spawned daemon on clean exit; this only matters when
    the harness had to kill ``holo run`` itself, so the grandchild never got the
    memo. Best-effort by design: cleanup failures must never mask the task result.
    """
    try:
        if os.name == "nt":
            find = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue).OwningProcess",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = [pid.strip() for pid in find.stdout.split() if pid.strip().isdigit()]
            for pid in pids:
                subprocess.run(["taskkill", "/PID", pid, "/F", "/T"], capture_output=True, check=False)
            return
        find = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, check=False)
        pids = [pid.strip() for pid in find.stdout.split() if pid.strip().isdigit()]
        for pid in pids:
            subprocess.run(["kill", "-9", pid], capture_output=True, check=False)
    except Exception:
        return


@dataclass(frozen=True)
class HoloRunResult:
    """Captured result from one `uv run holo run` subprocess."""

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    event_log_path: Path | None
    runtime_log_path: Path | None = None


def run_holo_foreground(
    *,
    task: str,
    runs_dir: Path,
    config: HoloLiveConfig,
    max_steps: int = 12,
    max_time_s: float = 90.0,
    stream_output: bool = True,
) -> HoloRunResult:
    """Run Holo through the public CLI, teeing output live while capturing it."""

    holo_max_time_s = _bounded_holo_max_time_s(
        requested_max_time_s=max_time_s,
        subprocess_timeout_s=config.timeout_s,
    )
    port = free_port()
    agent_runtime_log_path = runtime_log_path(port)
    command = [
        "uv",
        "run",
        "holo",
        "run",
        task,
        # Always profile: Holo derives avg action speed from the copied event log
        # and writes it into each task's result.json (QA latency tracking is free).
        "--profile",
        # Per-task port: never attach to (or get refused by) another task's daemon.
        "--port",
        str(port),
        "--runs-dir",
        str(runs_dir),
        "--max-steps",
        str(max_steps),
        "--max-time-s",
        str(holo_max_time_s),
    ]
    if config.quiet:
        command.append("--quiet")
    if config.fast:
        command.append("--fast")
    if config.model:
        command.extend(["--model", config.model])
    if config.base_url:
        command.extend(["--base-url", config.base_url])
    start = time.monotonic()
    if not stream_output:
        try:
            return _run_holo_captured(
                command=command,
                runs_dir=runs_dir,
                agent_runtime_log_path=agent_runtime_log_path,
                timeout_s=config.timeout_s,
                start=start,
            )
        finally:
            kill_port_listener(port)

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    proc = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_thread = _tee_stream(proc.stdout, sys.stdout, stdout_chunks)
    stderr_thread = _tee_stream(proc.stderr, sys.stderr, stderr_chunks)
    try:
        exit_code = proc.wait(timeout=config.timeout_s)
    except subprocess.TimeoutExpired:
        cleanup = _graceful_timeout_cleanup(proc)
        exit_code = 124
        stderr_chunks.append(f"\nTimed out after {config.timeout_s}s; {cleanup}")
    finally:
        kill_port_listener(port)
    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)
    duration = time.monotonic() - start
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    return HoloRunResult(
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_s=duration,
        event_log_path=find_event_log_path(stderr) or find_latest_event_log(runs_dir),
        runtime_log_path=agent_runtime_log_path if agent_runtime_log_path.exists() else None,
    )


def _run_holo_captured(
    *,
    command: list[str],
    runs_dir: Path,
    agent_runtime_log_path: Path,
    timeout_s: float,
    start: float,
) -> HoloRunResult:
    try:
        proc = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr = f"{stderr}\nTimed out after {timeout_s}s".strip()
        return HoloRunResult(
            command=command,
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            event_log_path=find_event_log_path(stderr) or find_latest_event_log(runs_dir),
            runtime_log_path=agent_runtime_log_path if agent_runtime_log_path.exists() else None,
        )
    duration = time.monotonic() - start
    event_log_path = find_event_log_path(proc.stderr) or find_latest_event_log(runs_dir)
    return HoloRunResult(
        command=command,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_s=duration,
        event_log_path=event_log_path,
        runtime_log_path=agent_runtime_log_path if agent_runtime_log_path.exists() else None,
    )


def _graceful_timeout_cleanup(proc: subprocess.Popen[str]) -> str:
    """Ask ``holo run`` to cancel its session before resorting to a force-kill."""

    try:
        if os.name == "nt":
            proc.terminate()
            signal_name = "terminate"
        else:
            proc.send_signal(signal.SIGINT)
            signal_name = "SIGINT"
        proc.wait(timeout=TIMEOUT_SHUTDOWN_GRACE_S)
        return f"{signal_name} cleanup completed"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return f"{signal_name} cleanup exceeded {TIMEOUT_SHUTDOWN_GRACE_S:g}s; force-killed"
    except ProcessLookupError:
        proc.wait()
        return "process exited during timeout cleanup"


def _tee_stream(
    source: IO[str] | None,
    target: TextIO,
    chunks: list[str],
) -> threading.Thread:
    def run() -> None:
        if source is None:
            return
        for line in source:
            chunks.append(line)
            target.write(line)
            target.flush()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def find_event_log_path(stderr: str) -> Path | None:
    """Extract an events.jsonl path printed by Holo stderr."""

    lines = [_strip_ansi(line) for line in stderr.splitlines()]
    for line in lines:
        match = _EVENT_LOG_RE.search(line)
        if match:
            return Path(match.group(1).strip())
    for index, line in enumerate(lines[:-1]):
        if "events streamed to" in line:
            candidate = lines[index + 1].strip()
            if candidate:
                return Path(candidate)
    return None


def find_latest_event_log(runs_dir: Path) -> Path | None:
    """Return the newest events.jsonl under a runs directory."""

    candidates = [path for path in runs_dir.glob("*/events.jsonl") if path.exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _bounded_holo_max_time_s(*, requested_max_time_s: float, subprocess_timeout_s: float) -> float:
    if subprocess_timeout_s <= 1.0:
        return max(0.001, subprocess_timeout_s * 0.8)
    return min(requested_max_time_s, max(1.0, subprocess_timeout_s - 5.0))


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
