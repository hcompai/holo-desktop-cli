from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

DESKTOP = Path.home() / "Desktop"
ARTIFACT_PREFIX = "holoe2e"
RENAME_CONTENT = "HOLO_E2E_RENAME_FIXTURE_CONTENT_v1"


@dataclass(frozen=True)
class TextEditDocuments:
    """Text content read from the currently open TextEdit documents."""

    documents: list[str]


@dataclass(frozen=True)
class TextEditDocumentsError:
    """Failure observed while reading TextEdit document text."""

    message: str


TextEditDocumentsResult = TextEditDocuments | TextEditDocumentsError


def require_app(name: str) -> None:
    proc = subprocess.run(
        ["osascript", "-e", f'id of application "{name}"'],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"{name} is not available on this macOS host")


def unique_token(label: str) -> str:
    safe_label = "".join(char for char in label.lower() if char.isalnum())
    return f"0{ARTIFACT_PREFIX}{safe_label}{uuid.uuid4().hex[:8]}"


def cleanup_desktop_artifacts() -> None:
    for pattern in (f"{ARTIFACT_PREFIX}*", f"0{ARTIFACT_PREFIX}*", "holo_e2e_*"):
        for path in DESKTOP.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def quit_app(name: str, *, discard_unsaved_changes: bool = False) -> None:
    command = f'tell application "{name}" to quit'
    if discard_unsaved_changes:
        command = f"{command} saving no"
    run_osascript(command, check=False, timeout_s=5.0)
    time.sleep(0.4)


def activate_app(name: str) -> None:
    run_osascript(
        f"""
        tell application "{name}" to activate
        tell application "System Events"
          if exists process "{name}" then
            set frontmost of process "{name}" to true
            try
              perform action "AXRaise" of window 1 of process "{name}"
            end try
          end if
        end tell
        """,
        check=False,
    )
    time.sleep(0.4)


def frontmost_app_name() -> str | None:
    proc = run_osascript(
        """
        tell application "System Events"
          name of first application process whose frontmost is true
        end tell
        """,
        check=False,
        timeout_s=3.0,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def ensure_frontmost_app(name: str, *, timeout_s: float = 3.0) -> None:
    """Activate an app and fail the test if macOS does not make it frontmost."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        activate_app(name)
        if frontmost_app_name() == name:
            return
        time.sleep(0.2)
    pytest.fail(f"expected {name} to be frontmost before live e2e; got {frontmost_app_name()!r}")


def open_file_in_textedit(path: Path) -> None:
    require_app("TextEdit")
    subprocess.run(["open", "-a", "TextEdit", str(path)], check=False)
    activate_app("TextEdit")


def open_finder_desktop() -> None:
    require_app("Finder")
    run_osascript(
        """
        tell application "Finder"
          activate
          set desktopFolder to (path to desktop folder as alias)
          if (count of Finder windows) is 0 then
            make new Finder window to desktopFolder
          else
            set target of front Finder window to desktopFolder
          end if
          set bounds of front Finder window to {80, 80, 1180, 820}
        end tell
        """,
        check=False,
        timeout_s=5.0,
    )
    activate_app("Finder")


def open_calculator_basic() -> None:
    require_app("Calculator")
    quit_app("Calculator")
    subprocess.run(["open", "-a", "Calculator"], check=False)
    activate_app("Calculator")
    run_osascript(
        """
        tell application "System Events"
          keystroke "1" using command down
          key code 53
        end tell
        """,
        check=False,
        timeout_s=5.0,
    )
    time.sleep(0.4)


def open_notes() -> None:
    require_app("Notes")
    subprocess.run(["open", "-a", "Notes"], check=False)
    activate_app("Notes")


def open_preview_image(path: Path) -> None:
    require_app("Preview")
    subprocess.run(["open", "-a", "Preview", str(path)], check=False)
    activate_app("Preview")


def new_textedit_document() -> None:
    require_app("TextEdit")
    quit_app("TextEdit", discard_unsaved_changes=True)
    run_osascript(
        """
        tell application "TextEdit"
          activate
          make new document
        end tell
        """,
        check=False,
        timeout_s=5.0,
    )
    time.sleep(0.6)


def textedit_documents_text() -> TextEditDocumentsResult:
    """Return open TextEdit document text, preserving AppleScript failures."""

    script = """
    tell application "TextEdit"
      if not running then return "__HOLO_TEXTEDIT_NOT_RUNNING__"
      set out to {}
      repeat with d in documents
        set end of out to text of d
      end repeat
      set AppleScript's text item delimiters to "__HOLO_DOC_SEPARATOR__"
      return out as text
    end tell
    """
    proc = run_osascript(script, check=False, timeout_s=20.0)
    if proc.returncode == 124:
        time.sleep(1.0)
        proc = run_osascript(script, check=False, timeout_s=30.0)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr or stdout or "no output"
        return TextEditDocumentsError(f"TextEdit AppleScript failed with code {proc.returncode}: {detail}")
    if "__HOLO_TEXTEDIT_NOT_RUNNING__" in proc.stdout:
        return TextEditDocumentsError("TextEdit is not running")
    body = proc.stdout.rstrip("\n")
    if not body:
        return TextEditDocuments([])
    return TextEditDocuments(body.split("__HOLO_DOC_SEPARATOR__"))


def calculator_display() -> str | None:
    """Return Calculator's result display via accessibility, if readable.

    Prefer the SwiftUI Calculator display node when present; on macOS 14 CI the
    result can appear only in the broader app static-text dump. Values carry
    U+200E bidi marks, which the evaluator strips.
    """

    pid = _pid_for_process("Calculator")
    if pid is None:
        return None
    app_services = _require_app_services()
    app = app_services.AXUIElementCreateApplication(pid)
    input_view = _find_ax_element_by_identifier(app_services, app, "StandardInputView")
    if input_view is not None:
        display = _calculator_display_from_static_text_values(_calculator_static_text_values(app_services, input_view))
        if display is not None:
            return display

    return _calculator_display_from_static_text_values(_calculator_static_text_values(app_services, app))


def calculator_static_text_values() -> list[str]:
    """Return Calculator AX static text values for diagnostics."""

    pid = _pid_for_process("Calculator")
    if pid is None:
        return []
    app_services = _require_app_services()
    app = app_services.AXUIElementCreateApplication(pid)
    return _calculator_static_text_values(app_services, app)


def _require_app_services() -> Any:
    """Import the AX bridge, loud on failure.

    A missing dependency or TCC grant must read as "harness broken", never as
    "display empty" — an ImportError swallow here hid a never-installed pyobjc
    framework behind two days of false calculator FAILs (QA findings 8/13).
    """

    import ApplicationServices as app_services

    if not app_services.AXIsProcessTrusted():
        raise RuntimeError(
            "AX reads unavailable: this process is not trusted for Accessibility. "
            "Run the e2e from a terminal with an Accessibility grant."
        )
    return app_services


def _find_ax_element_by_identifier(app_services: Any, element: Any, identifier: str, *, depth: int = 0) -> Any | None:
    if depth > 12:
        return None
    if _ax_attribute(app_services, element, "AXIdentifier") == identifier:
        return element
    children = _ax_attribute(app_services, element, "AXChildren")
    if isinstance(children, Iterable) and not isinstance(children, str):
        for child in children:
            found = _find_ax_element_by_identifier(app_services, child, identifier, depth=depth + 1)
            if found is not None:
                return found
    return None


def _pid_for_process(name: str) -> int | None:
    proc = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    first = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else ""
    try:
        return int(first)
    except ValueError:
        return None


def _calculator_static_text_values(app_services: Any, element: Any, *, depth: int = 0) -> list[str]:
    if depth > 12:
        return []

    role = _ax_attribute(app_services, element, "AXRole")
    value = _ax_attribute(app_services, element, "AXValue")
    values: list[str] = []
    if role == "AXStaticText" and isinstance(value, str):
        values.append(value)

    children = _ax_attribute(app_services, element, "AXChildren")
    if isinstance(children, Iterable) and not isinstance(children, str):
        for child in children:
            values.extend(_calculator_static_text_values(app_services, child, depth=depth + 1))
    return values


def _calculator_display_from_static_text_values(values: list[str]) -> str | None:
    for value in reversed(values):
        if value.strip():
            return value
    return None


def _ax_attribute(app_services: Any, element: Any, attribute: str) -> Any:
    try:
        err, value = app_services.AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


def delete_test_notes() -> None:
    escaped_prefix = _applescript_string(ARTIFACT_PREFIX)
    run_osascript(
        f'tell application "Notes" to delete (every note where name contains {escaped_prefix})',
        check=False,
        timeout_s=5.0,
    )


def notes_body_for_title(title: str) -> str | None:
    proc = run_osascript(
        f'tell application "Notes" to get body of (first note where name contains {_applescript_string(title)})',
        check=False,
        timeout_s=10.0,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def create_png(path: Path, *, size: tuple[int, int]) -> None:
    from PIL import Image

    Image.new("RGB", size, color=(80, 160, 240)).save(path, "PNG")


def image_dimensions(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def cursor_position() -> tuple[int, int]:
    import pyautogui

    position = pyautogui.position()
    return int(position.x), int(position.y)


def restore_cursor(position: tuple[int, int]) -> None:
    try:
        import pyautogui

        pyautogui.moveTo(position[0], position[1])
    except Exception:
        return


def screencapture_available() -> bool:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        proc = subprocess.run(["screencapture", "-x", tmp.name], capture_output=True, text=True, check=False)
        return proc.returncode == 0 and Path(tmp.name).stat().st_size > 0


def run_osascript(script: str, *, check: bool, timeout_s: float = 10.0) -> subprocess.CompletedProcess[str]:
    command = ["osascript", "-e", script]
    try:
        return subprocess.run(command, capture_output=True, text=True, check=check, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        if check:
            raise
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr = f"{stderr}\nosascript timed out after {timeout_s}s".strip()
        return subprocess.CompletedProcess(command, 124, stdout, stderr)


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
