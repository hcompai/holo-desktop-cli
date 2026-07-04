"""macOS TCC heuristics and the first-run walkthrough marker (product UX Holo keeps).

The SDK owns spawning and exposes runtime.log_path; Holo keeps deciding what a
permission failure looks like and when to run the first-run restart walkthrough.
"""

from __future__ import annotations

from pathlib import Path

# Heuristic markers of macOS TCC failures in the binary's stderr.
PERMISSION_ERROR_HINTS = (
    "accessibility",
    "screen recording",
    "screencapture",
    "could not create image from display",
    "tcc",
    "not permitted",
    "permission",
)

# One marker, not version-keyed: grants re-prompt per binary path anyway, and the
# walkthrough retry also triggers off the log-keyword heuristic regardless of the marker.
FIRST_RUN_MARKER = Path.home() / ".holo" / ".first-run-complete"


def text_suggests_permissions(text: str) -> bool:
    """True when ``text`` (stderr tail, session error, ...) looks like a macOS permission failure."""
    lowered = text.lower()
    return any(hint in lowered for hint in PERMISSION_ERROR_HINTS)


def log_tail_suggests_permissions(log_path: Path | None) -> bool:
    """True when the runtime's recent stderr looks like a macOS permission failure."""
    if log_path is None:
        return False
    try:
        data = log_path.read_bytes()[-8192:]
    except OSError:
        return False
    return text_suggests_permissions(data.decode("utf-8", errors="replace"))


def first_run_pending() -> bool:
    """True until a task completes against an SDK-managed runtime on this machine."""
    return not FIRST_RUN_MARKER.exists()


def mark_first_run_complete() -> None:
    FIRST_RUN_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FIRST_RUN_MARKER.touch()
