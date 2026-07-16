from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

from ._domain import EvaluationResult, FailureCategory, FlatMetadata
from .evaluators.calculator import calculator_result_part

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
    display = _run(["xdpyinfo"], timeout=5.0)
    if display.returncode != 0:
        _unavailable(f"X11 display is unavailable: {display.stderr.strip()}")
    screenshot = _run(["scrot", "-o", "/tmp/holo-e2e-preflight.png"], timeout=10.0)
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
    search = _run(["xdotool", "search", "--onlyvisible", "--name", ".*"], timeout=5.0)
    if search.returncode != 0:
        return []
    windows: list[tuple[str, str]] = []
    for window_id in search.stdout.splitlines():
        window_id = window_id.strip()
        if not window_id:
            continue
        title = _run(["xdotool", "getwindowname", window_id], timeout=2.0)
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
        running = _run(["pgrep", "-x", name], timeout=2.0)
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


def opened_file_window(filename: str, titles: list[str] | None = None) -> str | None:
    path = Path(filename)
    candidates = (path.name, path.stem)
    for title in titles if titles is not None else [title for _, title in visible_windows()]:
        folded = title.casefold()
        if "mousepad" in folded and any(candidate.casefold() in folded for candidate in candidates if candidate):
            return title
    return None


class LinuxOpenedFileEvaluator:
    """Proves a seeded file is open in a visible Mousepad window."""

    name = "linux_opened_file"

    def __init__(self, path: Path, expected_content: str) -> None:
        self.path = path
        self.expected_content = expected_content

    def evaluate(self) -> EvaluationResult:
        metadata: FlatMetadata = {"path": str(self.path)}
        if not self.path.exists():
            return EvaluationResult(
                passed=False,
                message=f"file disappeared before open check: {self.path}",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        if self.path.read_text(encoding="utf-8", errors="replace") != self.expected_content:
            return EvaluationResult(
                passed=False,
                message="seeded file content changed before open check",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        titles = [title for _, title in visible_windows()]
        matching_title = opened_file_window(self.path.name, titles)
        metadata["visible_window_titles"] = titles
        if matching_title is None:
            return EvaluationResult(
                passed=False,
                message="seeded file was not visible in a Mousepad window",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        return EvaluationResult(
            passed=True,
            message="file opened in Mousepad",
            metadata={**metadata, "mousepad_window_title": matching_title},
        )


class LinuxCalculatorResultEvaluator:
    """Checks KCalc's visible result through the independent AT-SPI tree."""

    name = "linux_calculator_result"

    def __init__(self, *, a: int, b: int, expected: int) -> None:
        self.a = a
        self.b = b
        self.expected = expected

    def evaluate(self) -> EvaluationResult:
        entries = kcalc_accessible_entries()
        display = kcalc_display_from_entries(entries)
        metadata: FlatMetadata = {
            "a": self.a,
            "b": self.b,
            "expected": self.expected,
            "accessible_entries": [json.dumps(entry, sort_keys=True) for entry in entries],
        }
        if display is None:
            return EvaluationResult(
                passed=False,
                message="KCalc display unreadable via AT-SPI",
                failure_category=FailureCategory.EVALUATOR,
                metadata=metadata,
            )
        result_part = kcalc_result_part(display)
        if result_part != str(self.expected):
            return EvaluationResult(
                passed=False,
                message=f"KCalc result mismatch: expected {self.expected!r}, got {result_part!r}",
                failure_category=FailureCategory.AGENT,
                metadata={**metadata, "display": display, "result_part": result_part},
            )
        return EvaluationResult(
            passed=True,
            message="KCalc result matched",
            metadata={**metadata, "display": display, "result_part": result_part},
        )


def kcalc_accessible_entries() -> list[dict[str, str]]:
    script = r"""
import json
import pyatspi

rows = []

def visit(node, depth=0):
    if depth > 20:
        return
    try:
        name = node.name or ""
        role = node.getRoleName() or ""
    except Exception:
        return
    text = ""
    try:
        text_iface = node.queryText()
        text = text_iface.getText(0, text_iface.characterCount)
    except Exception:
        pass
    if name or text:
        rows.append({"name": name, "role": role, "text": text})
    try:
        for child in node:
            visit(child, depth + 1)
    except Exception:
        pass

desktop = pyatspi.Registry.getDesktop(0)
for app in desktop:
    try:
        if "kcalc" in (app.name or "").lower():
            visit(app)
    except Exception:
        pass
print(json.dumps(rows))
"""
    proc = _run(["/usr/bin/python3", "-c", script], timeout=10.0)
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [
        {key: str(value) for key, value in item.items() if key in {"name", "role", "text"}}
        for item in payload
        if isinstance(item, dict)
    ]


def kcalc_display_from_entries(entries: list[dict[str, str]]) -> str | None:
    display_candidates: list[str] = []
    text_candidates: list[str] = []
    numeric_candidates: list[str] = []
    for entry in entries:
        role = entry.get("role", "").casefold()
        values = [entry.get("text", "").strip(), entry.get("name", "").strip()]
        for value in values:
            if not value:
                continue
            if "display" in entry.get("name", "").casefold() or "display" in role:
                display_candidates.append(value)
            if any(kind in role for kind in ("text", "entry", "edit")) and "button" not in role:
                text_candidates.append(value)
            if "button" not in role and re.fullmatch(r"[\s\u200e\u200f\d.,+\-*/=]+", value):
                numeric_candidates.append(value)
    for candidates in (display_candidates, text_candidates, numeric_candidates):
        for candidate in reversed(candidates):
            if re.search(r"\d", candidate):
                return candidate
    return None


def kcalc_result_part(display: str) -> str:
    result = calculator_result_part(display)
    if "=" in result:
        result = result.rsplit("=", 1)[-1]
    return result.strip()


def preserve_kcalc_display(artifact_dir: Path) -> None:
    entries = kcalc_accessible_entries()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "kcalc-atspi.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    display = kcalc_display_from_entries(entries)
    (artifact_dir / "kcalc-display.txt").write_text(f"{display or ''}\n", encoding="utf-8")


def preserve_window_titles(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    titles = [title for _, title in visible_windows()]
    (artifact_dir / "visible-window-titles.txt").write_text("\n".join(titles) + "\n", encoding="utf-8")


def _activate_window(window_id: str) -> None:
    _run(["xdotool", "windowactivate", "--sync", window_id], timeout=5.0)
    _run(["xdotool", "windowfocus", "--sync", window_id], timeout=5.0)


def _run(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", f"{type(exc).__name__}: {exc}")


def _unavailable(message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)
