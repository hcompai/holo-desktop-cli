"""End-to-end fake-mode gate for the SDK migration (the Task 4/5 before-and-after check).

Runs `holo run --fake` as a subprocess against the real hai-agent-runtime
binary (no model, no desktop): spawn, session create, event streaming, answer,
teardown. Skipped when the binary is not on PATH; the runtime download is
deliberately not exercised here (Task 2 covers install behavior at the SDK
boundary). Follows the subprocess style of tests/test_integration_real.py.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _holo_executable() -> str:
    found = shutil.which("holo")
    if found:
        return found
    candidate = Path(sys.executable).with_name("holo")
    if candidate.exists():
        return str(candidate)
    raise AssertionError("could not locate the 'holo' console script")


@pytest.mark.timeout(120)
def test_fake_mode_run_completes_end_to_end() -> None:
    if shutil.which("hai-agent-runtime") is None:
        pytest.skip("put hai-agent-runtime (or a wrapper script) on PATH for the fake-mode gate")

    completed = subprocess.run(
        [_holo_executable(), "run", "--fake", "--quiet", "--port", str(_free_port()), "--no-kill-switch", "say hi"],
        capture_output=True,
        text=True,
        timeout=110,
        check=False,
    )

    assert completed.returncode == 0, f"holo run --fake failed ({completed.returncode}):\n{completed.stderr}"
