"""Real-agent integration (opt-in): full path to completion.

Drives the complete stack: ``holo run`` starts the real runtime through the SDK,
runs one task on the real desktop against a live model, and prints the answer.

Skipped by default: it needs a model + a desktop session + credentials, none of
which exist in unit CI. Opt in by exporting:

- ``HOLO_RUN_INTEGRATION=1``                     enable this module
- ``HOLO_IT_BASE_URL=<url>`` (optional)          self-hosted endpoint (needs HOLO_IT_MODEL)
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
    reason="opt-in: set HOLO_RUN_INTEGRATION=1 (needs a model, a desktop, and credentials)",
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
    cmd = [_holo_executable(), "run", os.environ.get("HOLO_IT_TASK") or _DEFAULT_TASK, "--quiet"]
    if base_url := os.environ.get("HOLO_IT_BASE_URL", "").strip():
        cmd += ["--base-url", base_url]
    if model := os.environ.get("HOLO_IT_MODEL", "").strip():
        cmd += ["--model", model]

    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)

    assert completed.returncode == 0, f"holo run failed ({completed.returncode}):\n{completed.stderr}"
    assert completed.stdout.strip(), f"expected a non-empty answer on stdout; stderr was:\n{completed.stderr}"
