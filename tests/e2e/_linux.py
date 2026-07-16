from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

DESKTOP = Path.home() / "Desktop"
DOWNLOADS = Path.home() / "Downloads"
ARTIFACT_PREFIX = "0holoe2e"
LAUNCHER_TITLE = "Holo E2E Applications"


def unique_token(label: str) -> str:
    safe_label = "".join(char for char in label.lower() if char.isalnum())
    return f"{ARTIFACT_PREFIX}{safe_label}{uuid.uuid4().hex[:8]}"


def require_desktop() -> None:
    missing = [command for command in ("xdpyinfo", "xdotool", "scrot") if shutil.which(command) is None]
    if missing:
        _unavailable(f"missing Linux desktop commands: {', '.join(missing)}")
    if not os.environ.get("DISPLAY"):
        _unavailable("DISPLAY is not set")
    for directory in (DESKTOP, DOWNLOADS):
        if not directory.is_dir():
            _unavailable(f"required directory does not exist: {directory}")
    display = run_command(["xdpyinfo"], timeout=5.0)
    if display.returncode != 0:
        _unavailable(f"X11 display is unavailable: {display.stderr.strip()}")
    screenshot = run_command(["scrot", "-o", "/tmp/holo-e2e-preflight.png"], timeout=10.0)
    screenshot_path = Path("/tmp/holo-e2e-preflight.png")
    if screenshot.returncode != 0 or not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
        _unavailable(f"X11 screenshot failed: {screenshot.stderr.strip()}")
    if find_window(LAUNCHER_TITLE) is None:
        _unavailable(f"visible application launcher is missing: {LAUNCHER_TITLE}")


def require_app(command: str) -> None:
    alternatives = (command, "google-chrome-stable") if command == "google-chrome" else (command,)
    if not any(shutil.which(candidate) for candidate in alternatives):
        _unavailable(f"required Linux app is unavailable: {command}")


def open_in_mousepad(path: Path) -> None:
    cleanup_process("mousepad")
    subprocess.Popen(
        ["mousepad", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    wait_for_window(path.name)


def open_desktop_in_thunar() -> None:
    cleanup_process("thunar")
    subprocess.Popen(
        ["thunar", str(DESKTOP)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    wait_for_window("Desktop")


def wait_for_window(pattern: str, *, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        match = find_window(pattern)
        if match is not None:
            _activate_window(match[0])
            return match[1]
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for visible Linux window matching {pattern!r}")


def find_window(pattern: str) -> tuple[str, str] | None:
    for window_id, title in visible_windows():
        if pattern.casefold() in title.casefold():
            return window_id, title
    return None


def visible_windows() -> list[tuple[str, str]]:
    search = run_command(["xdotool", "search", "--onlyvisible", "--name", ".*"], timeout=5.0)
    if search.returncode != 0:
        return []
    windows: list[tuple[str, str]] = []
    for window_id in search.stdout.splitlines():
        window_id = window_id.strip()
        if not window_id:
            continue
        title = run_command(["xdotool", "getwindowname", window_id], timeout=2.0)
        if title.returncode == 0 and title.stdout.strip():
            windows.append((window_id, title.stdout.strip()))
    return windows


def cleanup_desktop_artifacts() -> None:
    for pattern in (f"{ARTIFACT_PREFIX}*", "holo_e2e_*"):
        for path in DESKTOP.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def cleanup_process(name: str, *, timeout: float = 5.0) -> None:
    with suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(["pkill", "-TERM", "-x", name], capture_output=True, check=False, timeout=5.0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        running = run_command(["pgrep", "-x", name], timeout=2.0)
        if running.returncode != 0:
            return
        time.sleep(0.1)
    with suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(["pkill", "-KILL", "-x", name], capture_output=True, check=False, timeout=5.0)


def cleanup_editor_and_desktop() -> None:
    cleanup_process("mousepad")
    cleanup_desktop_artifacts()


def cleanup_file_manager_and_desktop() -> None:
    cleanup_process("thunar")
    cleanup_desktop_artifacts()


def cleanup_opened_file_task() -> None:
    cleanup_process("mousepad")
    cleanup_process("thunar")
    cleanup_desktop_artifacts()


def cleanup_calculator() -> None:
    cleanup_process("kcalc")


def cleanup_chrome() -> None:
    profile = Path(os.environ.get("HOLO_E2E_CHROME_PROFILE", "/tmp/holo-e2e-chrome-profile"))
    with suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(
            ["pkill", "-TERM", "-f", f"--user-data-dir={profile}"],
            capture_output=True,
            check=False,
            timeout=5.0,
        )
    cleanup_process("chrome", timeout=1.0)
    cleanup_process("google-chrome", timeout=1.0)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        chrome_titles = [title for _, title in visible_windows() if "chrome" in title.casefold()]
        if not chrome_titles:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError(f"failed to close Chrome windows: {chrome_titles}")
    shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)


def cleanup_test_apps() -> None:
    cleanup_process("mousepad")
    cleanup_process("thunar")
    cleanup_process("kcalc")
    cleanup_chrome()


def _activate_window(window_id: str) -> None:
    run_command(["xdotool", "windowactivate", "--sync", window_id], timeout=5.0)
    run_command(["xdotool", "windowfocus", "--sync", window_id], timeout=5.0)


def run_command(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", f"{type(exc).__name__}: {exc}")


def _unavailable(message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)
