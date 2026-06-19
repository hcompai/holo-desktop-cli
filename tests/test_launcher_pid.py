"""Behavioural tests for the runtime pid file's on-disk hardening.

The pid file's contents drive a privileged operation: ``holo stop --force`` reads it and
``os.killpg(..., SIGKILL)`` the pid it finds. It therefore earns the same protections as the bearer
token — owner-only permissions and a refusal to follow a symlink planted at its path — so it can never
be steered into killing an arbitrary process group.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file-mode semantics")
def test_pid_file_written_owner_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    path = launcher._write_pid_file(4242, 31337)

    assert path is not None
    assert path.read_text(encoding="utf-8") == "31337"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="O_NOFOLLOW is POSIX-only")
def test_pid_file_write_refuses_symlink_at_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # An attacker pre-plants a symlink at the pid path pointing at a file they want clobbered (and,
    # later, read back by `holo stop --force`). The hardened write must refuse to follow it.
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    victim = tmp_path / "victim"
    victim.write_text("untouched", encoding="utf-8")
    pid_path = launcher.pid_file_path(4242)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(victim, pid_path)

    assert launcher._write_pid_file(4242, 31337) is None
    assert victim.read_text(encoding="utf-8") == "untouched", "symlink target must not be clobbered"
    assert pid_path.is_symlink(), "the planted symlink itself is left as-is, never written through"
