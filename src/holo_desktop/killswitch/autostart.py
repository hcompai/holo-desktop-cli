"""Install the `holo guard` kill switch as an OS autostart service so it survives across sessions.

The guard must be launched by the OS (launchd / login item), not as a child of a host like Hermes:
on macOS only an OS-launched process gets its own Input Monitoring identity (TCC attributes a child's
permission to the launching app). Windows and Linux/X11 have no such gate; Wayland has no global listener.
"""

from __future__ import annotations

import enum
import logging
import os
import platform
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

GUARD_LABEL = "ai.hcompany.holo.guard"
HOLO_DIR = Path.home() / ".holo"
GUARD_LOG_PATH = HOLO_DIR / "logs" / "holo-guard.log"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
WINDOWS_STARTUP_DIR = (
    Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
)
LINUX_AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "autostart"


class AutostartResult(enum.Enum):
    """Outcome of an autostart-install attempt."""

    INSTALLED = "installed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


def ensure_autostart(holo_cmd: str) -> tuple[AutostartResult, str]:
    """Install and activate the guard autostart for the current OS, idempotently.

    Args:
        holo_cmd: Absolute path to the ``holo`` executable to launch as ``holo guard``.

    Returns:
        The outcome and a human-readable detail (the artifact path, or why it was skipped).
    """
    system = platform.system()
    if system == "Darwin":
        return _ensure_macos(holo_cmd)
    if system == "Windows":
        return _ensure_windows(holo_cmd)
    if system == "Linux":
        if _is_wayland():
            return (
                AutostartResult.UNSUPPORTED,
                "Wayland has no global listener; bind `holo stop` to a compositor hotkey",
            )
        return _ensure_linux(holo_cmd)
    return AutostartResult.UNSUPPORTED, f"autostart unsupported on {system}"


def ensure_loaded() -> None:
    """Best-effort: load an already-installed guard; no-op when it was never installed.

    Installation is ``holo install``'s job. Headless startups only nudge an installed guard to run,
    so a machine that never opted in stays untouched.
    """
    if platform.system() != "Darwin":
        # Windows Startup entries and Linux XDG autostart are loaded by the OS at login; nothing to nudge.
        return
    path = macos_plist_path()
    if not path.exists():
        return
    _run_quietly(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])


def macos_plist_path() -> Path:
    """Path of the guard LaunchAgent plist."""
    return LAUNCH_AGENTS_DIR / f"{GUARD_LABEL}.plist"


def render_macos_plist(holo_cmd: str, log_path: Path) -> str:
    """A LaunchAgent plist that runs ``holo guard`` at login and keeps it alive."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        f"    <key>Label</key>\n    <string>{GUARD_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        f"    <array>\n        <string>{escape(holo_cmd)}</string>\n        <string>guard</string>\n    </array>\n"
        "    <key>RunAtLoad</key>\n    <true/>\n"
        "    <key>KeepAlive</key>\n    <true/>\n"
        "    <key>ProcessType</key>\n    <string>Interactive</string>\n"
        f"    <key>StandardErrorPath</key>\n    <string>{escape(str(log_path))}</string>\n"
        "</dict>\n</plist>\n"
    )


def windows_launcher_path() -> Path:
    """Path of the guard Startup-folder launcher."""
    return WINDOWS_STARTUP_DIR / "holo-guard.cmd"


def render_windows_launcher(holo_cmd: str) -> str:
    """A Startup-folder batch file that launches ``holo guard`` detached at login."""
    return f'@echo off\r\nstart "" "{holo_cmd}" guard\r\n'


def linux_desktop_path() -> Path:
    """Path of the guard XDG autostart entry."""
    return LINUX_AUTOSTART_DIR / "holo-guard.desktop"


def render_linux_desktop(holo_cmd: str) -> str:
    """An XDG autostart entry that launches ``holo guard`` at graphical login."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Holo kill switch\n"
        f"Exec={holo_cmd} guard\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _ensure_macos(holo_cmd: str) -> tuple[AutostartResult, str]:
    GUARD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    path = macos_plist_path()
    changed = _write_if_changed(path, render_macos_plist(holo_cmd, GUARD_LOG_PATH))
    uid = os.getuid()
    if changed:
        _run_quietly(["launchctl", "bootout", f"gui/{uid}/{GUARD_LABEL}"])
    _run_quietly(["launchctl", "bootstrap", f"gui/{uid}", str(path)])
    return (AutostartResult.INSTALLED if changed else AutostartResult.SKIPPED), str(path)


def _ensure_windows(holo_cmd: str) -> tuple[AutostartResult, str]:
    path = windows_launcher_path()
    changed = _write_if_changed(path, render_windows_launcher(holo_cmd))
    return (AutostartResult.INSTALLED if changed else AutostartResult.SKIPPED), str(path)


def _ensure_linux(holo_cmd: str) -> tuple[AutostartResult, str]:
    path = linux_desktop_path()
    changed = _write_if_changed(path, render_linux_desktop(holo_cmd))
    return (AutostartResult.INSTALLED if changed else AutostartResult.SKIPPED), str(path)


def _write_if_changed(path: Path, content: str) -> bool:
    """Write ``content`` to ``path`` only when it differs; return True if a write happened."""
    try:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"could not write guard autostart file {path}: {exc}") from exc
    return True


def _run_quietly(cmd: list[str]) -> None:
    """Run a best-effort activation command; failures (already-loaded, missing tool) are non-fatal."""
    try:
        subprocess.run(cmd, capture_output=True, check=False)
    except OSError as exc:
        logger.debug("guard autostart command failed: %s (%s)", " ".join(cmd), exc)


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
