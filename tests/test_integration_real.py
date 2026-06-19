"""Real-agent integration (opt-in): full path to completion.

Drives the complete client stack — ``holo run`` (this client) spawns the
real ``hai-agent-runtime`` binary on loopback, creates a session, streams ``/changes``,
and prints the answer — against a live Holo3 model and a real desktop.

Skipped by default: it needs a model + a desktop session + credentials, none of
which exist in unit CI. Opt in by exporting:

- ``HOLO_RUN_INTEGRATION=1``                     enable this module
- ``hai-agent-runtime`` on ``PATH``                 the real binary (or a wrapper script around
                                                 "python -m hai_agent_runtime" from a dev checkout)
- ``HOLO_IT_BASE_URL=<url>`` (optional)          self-hosted Holo3 endpoint; omit to use hosted
- ``HOLO_IT_MODEL=<name>``   (optional)          model override
- ``HOLO_IT_TASK=<text>``    (optional)          overrides the default trivial task
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_INTEGRATION") != "1",
    reason="opt-in: set HOLO_RUN_INTEGRATION=1 (needs a model + desktop + the real hai-agent-runtime binary)",
)

_DEFAULT_TASK = "Look at the current screen and describe in one short sentence what is visible."
_TIMEOUT_S = 300.0


def _holo_executable() -> str:
    found = shutil.which("holo")
    if found:
        return found
    candidate = Path(sys.executable).with_name("holo")
    if candidate.exists():
        return str(candidate)
    raise AssertionError("could not locate the 'holo' console script for the integration run")


def test_real_run_completes_with_answer() -> None:
    if shutil.which("hai-agent-runtime") is None:
        pytest.skip("put hai-agent-runtime (or a wrapper script) on PATH for the integration run")

    cmd = [_holo_executable(), "run", os.environ.get("HOLO_IT_TASK") or _DEFAULT_TASK, "--quiet"]
    if base_url := os.environ.get("HOLO_IT_BASE_URL", "").strip():
        cmd += ["--base-url", base_url]
    if model := os.environ.get("HOLO_IT_MODEL", "").strip():
        cmd += ["--model", model]

    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)

    assert completed.returncode == 0, f"holo run failed ({completed.returncode}):\n{completed.stderr}"
    assert completed.stdout.strip(), f"expected a non-empty answer on stdout; stderr was:\n{completed.stderr}"
