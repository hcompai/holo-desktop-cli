"""Behavioural tests for apps.py — real osascript, real `open`, real processes.

macOS-only (skipped elsewhere). TextEdit ships with every macOS install and is
cheap to launch/kill.
"""

from __future__ import annotations

import platform
import subprocess
import time

import pytest

from expense_report_demo import apps

IS_DARWIN = platform.system() == "Darwin"
darwin_only = pytest.mark.skipif(not IS_DARWIN, reason="requires macOS")

_TEXTEDIT = "com.apple.TextEdit"


def _pgrep_textedit() -> str:
    return subprocess.run(["pgrep", "-x", "TextEdit"], check=False, capture_output=True, text=True).stdout.strip()


@darwin_only
def test_launch_wait_activate_kill_roundtrip() -> None:
    """Full lifecycle against TextEdit: launch, wait until running, activate, kill."""
    apps.launch_app(_TEXTEDIT, urls=[], new_instance=False, extra_args=[])
    apps.wait_for_app(_TEXTEDIT)
    assert _pgrep_textedit(), "TextEdit process expected after launch + wait"

    apps.activate_app(_TEXTEDIT)

    apps.kill_all([_TEXTEDIT])
    time.sleep(0.5)
    assert not _pgrep_textedit(), "TextEdit still running after kill_all"


def test_launch_app_rejects_extra_args_without_new_instance() -> None:
    with pytest.raises(ValueError, match="new_instance"):
        apps.launch_app(_TEXTEDIT, urls=[], new_instance=False, extra_args=["--flag"])


@darwin_only
def test_launch_app_unknown_bundle_fails_loud() -> None:
    with pytest.raises(RuntimeError, match="open failed"):
        apps.launch_app("com.example.does-not-exist-xyz", urls=[], new_instance=False, extra_args=[])


@darwin_only
def test_kill_all_no_op_for_empty_list() -> None:
    """kill_all([]) is a no-op — must not sleep or run subprocesses."""
    apps.kill_all([])


@darwin_only
def test_kill_all_terminates_textedit() -> None:
    """Launch TextEdit (always installed), kill it, verify it's gone."""
    subprocess.run(
        ["osascript", "-e", 'tell application "TextEdit" to launch'],
        check=True,
        capture_output=True,
    )
    time.sleep(1.0)
    if not _pgrep_textedit():
        pytest.skip("TextEdit didn't actually launch on this machine")

    apps.kill_all([_TEXTEDIT])
    assert not _pgrep_textedit(), "TextEdit still running after kill_all"
