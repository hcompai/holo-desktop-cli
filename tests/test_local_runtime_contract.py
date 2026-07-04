"""Contract tests pinning the hai-agents local-runtime behaviors Holo relies on.

Ported from tests/test_launcher_spawn.py, test_launcher_token.py, and
test_launcher_pid.py before those files (and the launcher/runtime_install
implementations they cover) are deleted in Task 9. Each test names the
launcher test it replaces; together they are the spec the SDK must keep
honoring for HoloDesktop. Failures here are upstream hai-agents bugs
(plan 002), not Holo bugs.
"""

from __future__ import annotations

import socket
from pathlib import Path

from hai_agents.local import LocalRuntime


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_attach_returns_none_when_no_runtime_listens(tmp_path: Path) -> None:
    # Replaces the launcher's "spawn when /health is unreachable" branch: no
    # discovery state + nothing listening must read as "no runtime", never a
    # half-alive handle.
    assert LocalRuntime.attach(port=_free_port(), cache_dir=tmp_path) is None
