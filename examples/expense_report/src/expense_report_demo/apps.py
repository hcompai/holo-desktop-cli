"""macOS app lifecycle for pre-task staging: launch, focus, wait, kill.

The agent runtime owns desktop control; this module only prepares the world
before a session starts (and cleans up after), using `open` and AppleScript.
"""

from __future__ import annotations

import subprocess
import time

_OSASCRIPT_TIMEOUT_S = 10.0
_LAUNCH_SETTLE_S = 0.4
_KILL_SETTLE_S = 1.5

APP_WAIT_ATTEMPTS = 40
APP_WAIT_INTERVAL_S = 0.5


def launch_app(bundle_id: str, *, urls: list[str], new_instance: bool, extra_args: list[str]) -> None:
    """Open `urls` (paths or URLs) with the app identified by `bundle_id`.

    `new_instance` spawns a fresh process (`open -n`); with `extra_args` the
    arguments land on that new process's argv (isolated Chrome profiles). URLs
    must travel as argv too in that case: LaunchServices would otherwise route
    them to an existing instance.
    """
    cmd = ["open", "-b", bundle_id]
    if new_instance:
        cmd.append("-n")
        if urls or extra_args:
            cmd += ["--args", *extra_args, *urls]
    else:
        if extra_args:
            raise ValueError("extra_args require new_instance=True; existing instances never see argv")
        cmd += urls
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"open failed for {bundle_id} ({result.returncode}): {result.stderr.strip()}")


def wait_for_app(bundle_id: str) -> None:
    """Block until a process with `bundle_id` is running. Raises on timeout."""
    script = (
        'tell application "System Events" to (count of '
        f'(application processes whose bundle identifier is "{bundle_id}"))'
    )
    for _ in range(APP_WAIT_ATTEMPTS):
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=_OSASCRIPT_TIMEOUT_S,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "0"):
            return
        time.sleep(APP_WAIT_INTERVAL_S)
    raise RuntimeError(f"no process for {bundle_id} within {APP_WAIT_ATTEMPTS * APP_WAIT_INTERVAL_S:.0f}s")


def activate_app(bundle_id: str) -> None:
    """Bring the app frontmost (the agent starts on whatever is focused)."""
    script = f'tell application id "{bundle_id}" to activate'
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=_OSASCRIPT_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise RuntimeError(f"activate failed for {bundle_id} ({result.returncode}): {result.stderr.strip()}")
    time.sleep(_LAUNCH_SETTLE_S)


# Mapping bundle_id -> a unique-enough substring of the executable path, so `pkill -f` finds it.
# Bundle ids that aren't here fall back to `osascript 'quit application id "<bundle>"'` (graceful).
_HARD_KILL_PATTERNS: dict[str, str] = {
    "com.google.Chrome": "Google Chrome.app/Contents/MacOS/Google Chrome",
    "com.apple.Safari": "Safari.app/Contents/MacOS/Safari",
    "com.microsoft.edgemac": "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "com.brave.Browser": "Brave Browser.app/Contents/MacOS/Brave Browser",
}


def kill_all(bundle_ids: list[str]) -> None:
    """Forcefully terminate any running instances of the given apps so subsequent
    launches start from a known clean state. Chromium-family apps get `pkill -9`
    (their parent processes spawn renderers that don't quit via AppleScript fast
    enough); everything else gets a polite `osascript ... quit`."""
    if not bundle_ids:
        return
    for bundle_id in bundle_ids:
        pattern = _HARD_KILL_PATTERNS.get(bundle_id)
        if pattern is not None:
            subprocess.run(["pkill", "-9", "-f", pattern], check=False, capture_output=True)
        else:
            subprocess.run(
                ["osascript", "-e", f'try\nquit application id "{bundle_id}"\nend try'],
                check=False,
                capture_output=True,
            )
    time.sleep(_KILL_SETTLE_S)
