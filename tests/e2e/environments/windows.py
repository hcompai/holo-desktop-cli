from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

from .. import _preserve
from .._domain import EvaluationResult, FailureCategory, FlatMetadata, PreparedTask, TaskCase
from ..evaluators.calculator import calculator_result_part
from ..evaluators.finder import (
    CopiedFileEvaluator,
    FolderExistsEvaluator,
    ProtectedFileEvaluator,
)
from ..evaluators.textedit import FileContainsEvaluator
from ..tasks import (
    BROWSER_DOWNLOAD_FILE,
    CALCULATOR_CI_SMOKE,
    FINDER_COPY_FILE,
    FINDER_CREATE_FOLDER,
    FINDER_OPEN_FILE_BY_DOUBLE_CLICK,
    FINDER_PROTECTED_FILE,
    FOREGROUND_VISIBLE_EDITOR_WITNESS,
    TEXTEDIT_TYPE_SENTINEL,
)

DESKTOP = Path.home() / "Desktop"
ARTIFACT_PREFIX = "0holoe2e"

WINDOWS_FOREGROUND_TASKS = (
    FOREGROUND_VISIBLE_EDITOR_WITNESS,
    TEXTEDIT_TYPE_SENTINEL,
    FINDER_CREATE_FOLDER,
    FINDER_COPY_FILE,
    FINDER_OPEN_FILE_BY_DOUBLE_CLICK,
    FINDER_PROTECTED_FILE,
    CALCULATOR_CI_SMOKE,
    BROWSER_DOWNLOAD_FILE,
)


class WindowsEnvironmentRunner:
    """Environment runner for live foreground tasks on Windows."""

    environment_id = "windows-foreground"
    task_cases: tuple[TaskCase, ...] = WINDOWS_FOREGROUND_TASKS

    def supports(self, case: TaskCase) -> bool:
        return case in self.task_cases

    def preflight(self, case: TaskCase) -> None:
        if not self.supports(case):
            pytest.skip(f"{self.environment_id} does not support {case.id}")
        if case.app_family in {"text-editor", "notes"} and shutil.which("notepad.exe") is None:
            pytest.skip("notepad.exe is not available on this Windows host")
        if case.app_family == "file-manager" and shutil.which("explorer.exe") is None:
            pytest.skip("explorer.exe is not available on this Windows host")
        if case.app_family == "calculator" and _calculator_command() is None:
            pytest.skip("Windows Calculator is not available on this Windows host")
        if case.app_family == "image-viewer" and shutil.which("mspaint.exe") is None:
            pytest.skip("mspaint.exe is not available on this Windows host")
        if not DESKTOP.exists():
            pytest.skip(f"Desktop directory does not exist: {DESKTOP}")
        _require_screenshot()

    def prepare(self, case: TaskCase, workspace: Path) -> PreparedTask:
        if case == FOREGROUND_VISIBLE_EDITOR_WITNESS:
            return self._prepare_foreground_visible_editor_witness(case, workspace)
        if case == TEXTEDIT_TYPE_SENTINEL:
            return self._prepare_textedit_type_sentinel(case, workspace)
        if case == FINDER_CREATE_FOLDER:
            return self._prepare_finder_create_folder(case, workspace)
        if case == FINDER_COPY_FILE:
            return self._prepare_finder_copy_file(case, workspace)
        if case == FINDER_OPEN_FILE_BY_DOUBLE_CLICK:
            return self._prepare_finder_open_file_by_double_click(case, workspace)
        if case == FINDER_PROTECTED_FILE:
            return self._prepare_finder_protected_file(case, workspace)
        if case == CALCULATOR_CI_SMOKE:
            return self._prepare_calculator_ci_smoke(case, workspace)
        if case == BROWSER_DOWNLOAD_FILE:
            return self._prepare_browser_download_file(case, workspace)
        raise ValueError(f"unsupported task case for {self.environment_id}: {case.id}")

    def cleanup(self, prepared: PreparedTask | None) -> None:
        if prepared is not None:
            with suppress(Exception):
                prepared.clean_up()

    def _prepare_foreground_visible_editor_witness(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_desktop_artifacts()
        sentinel = _unique_token("visibleeditorwitness")
        target_path = DESKTOP / f"{_unique_token('witnessfile')}.txt"
        target_path.write_text("", encoding="utf-8")

        instruction = (
            "Open Notepad, open the Desktop file named "
            f"{target_path.name!r}, type the exact text {sentinel!r} into the document, "
            "save the file with Ctrl+S, then stop. Do not use PowerShell, Command Prompt, or any command line tool."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "Notepad"},
            cleanup=_cleanup_notepad_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )

    def _prepare_textedit_type_sentinel(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_desktop_artifacts()
        sentinel = _unique_token("textedittype")
        target_path = DESKTOP / f"{_unique_token('typefile')}.txt"
        target_path.write_text("", encoding="utf-8")

        instruction = (
            "Open Notepad, open the Desktop file named "
            f"{target_path.name!r}, type the exact text {sentinel!r} into the document, "
            "save the file with Ctrl+S, then stop. Do not use PowerShell, Command Prompt, or any command line tool."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=FileContainsEvaluator(target_path, sentinel),
            metadata={"target_path": str(target_path), "sentinel": sentinel, "app": "Notepad"},
            cleanup=_cleanup_notepad_and_desktop,
            preserve_artifacts=lambda artifact_dir: _preserve.copy_path(target_path, artifact_dir),
        )

    def _prepare_finder_create_folder(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_desktop_artifacts()
        folder_name = _unique_token("folder")
        expected_path = DESKTOP / folder_name

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(expected_path, artifact_dir, name=expected_path.name)

        instruction = (
            "Open File Explorer, navigate to the Desktop, and create a new folder on the Desktop "
            f"with the exact name {folder_name!r}. Then stop. Do not use PowerShell, Command Prompt, or any command line tool."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=FolderExistsEvaluator(expected_path),
            metadata={"target_path": str(expected_path), "app": "File Explorer"},
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_copy_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_desktop_artifacts()
        source_path = DESKTOP / f"{_unique_token('copysource')}.txt"
        folder_path = DESKTOP / _unique_token("copyfolder")
        copied_path = folder_path / source_path.name
        content = f"copy fixture {_unique_token('copycontent')}\n"
        folder_path.mkdir()
        source_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.write_directory_listing(folder_path, artifact_dir, name="target-folder-listing.txt")
            _preserve.copy_path(source_path, artifact_dir, name=f"source-{source_path.name}")
            _preserve.copy_path(copied_path, artifact_dir, name=f"copy-{copied_path.name}")

        instruction = (
            "Open File Explorer and navigate to the Desktop. Copy the file named "
            f"{source_path.name!r} into the folder named {folder_path.name!r}. "
            "The original file must remain on the Desktop unchanged. "
            "Do not use PowerShell, Command Prompt, or any command line tool. Then stop."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=CopiedFileEvaluator(source_path, copied_path, content),
            metadata={
                "source_path": str(source_path),
                "copied_path": str(copied_path),
                "folder_path": str(folder_path),
                "app": "File Explorer",
            },
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_open_file_by_double_click(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_notepad_and_desktop()
        target_path = DESKTOP / f"{_unique_token('openbydoubleclick')}.txt"
        content = f"open fixture {_unique_token('opencontent')}\n"
        target_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(target_path, artifact_dir, name=target_path.name)

        instruction = (
            "Open File Explorer and navigate to the Desktop. Locate the file named "
            f"{target_path.name!r} and open it by double-clicking the file icon or filename. "
            "Do not use keyboard shortcuts, menus, PowerShell, Command Prompt, or any command line tool. Then stop."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=WindowsOpenedFileEvaluator(target_path, content),
            metadata={"target_path": str(target_path), "expected_content": content, "app": "File Explorer"},
            cleanup=_cleanup_notepad_and_desktop,
            preserve_artifacts=preserve,
        )

    def _prepare_finder_protected_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        _cleanup_desktop_artifacts()
        protected_path = DESKTOP / f"{_unique_token('protected')}.txt"
        content = f"protected fixture {_unique_token('protectedcontent')}\n"
        protected_path.write_text(content, encoding="utf-8")

        def preserve(artifact_dir: Path) -> None:
            _preserve.write_directory_listing(DESKTOP, artifact_dir, name="desktop-listing.txt")
            _preserve.copy_path(protected_path, artifact_dir, name=protected_path.name)

        instruction = (
            "Open File Explorer and navigate to the Desktop. Confirm that the file named "
            f"{protected_path.name!r} exists, but do not delete, rename, move, open, or edit it. "
            "Do not use PowerShell, Command Prompt, or any command line tool. Then stop."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=ProtectedFileEvaluator(protected_path, content),
            metadata={"protected_path": str(protected_path), "app": "File Explorer"},
            cleanup=_cleanup_desktop_artifacts,
            preserve_artifacts=preserve,
        )

    def _prepare_calculator_ci_smoke(self, case: TaskCase, workspace: Path) -> PreparedTask:
        a = 2
        b = 2
        expected = a + b

        instruction = (
            "Open Windows Calculator in Standard mode. Use the visible Calculator app UI to compute "
            f"{a} plus {b}. Click clear first if needed, then click {a}, +, {b}, and =. "
            "Do not use PowerShell, Command Prompt, Python, or any command line tool. Then stop."
        )
        return PreparedTask(
            case=case,
            instruction=instruction,
            workspace=workspace,
            evaluator=WindowsCalculatorResultEvaluator(a=a, b=b, expected=expected),
            metadata={"a": a, "b": b, "expected": expected, "app": "Calculator"},
            cleanup=_cleanup_calculator,
            preserve_artifacts=_preserve_windows_calculator_display,
        )

    def _prepare_browser_download_file(self, case: TaskCase, workspace: Path) -> PreparedTask:
        from ..tasks.browser import prepare_browser_download_task

        filename = f"{_unique_token('download')}.txt"
        return prepare_browser_download_task(
            case=case,
            workspace=workspace,
            filename=filename,
            content=f"download fixture {_unique_token('downloadcontent')}\n",
            target_path=Path.home() / "Downloads" / filename,
            browser_name="a web browser",
            command_line_warning="PowerShell, Command Prompt, Python,",
        )


def _unique_token(label: str) -> str:
    safe_label = "".join(char for char in label.lower() if char.isalnum())
    return f"{ARTIFACT_PREFIX}{safe_label}{uuid.uuid4().hex[:8]}"


def _cleanup_desktop_artifacts() -> None:
    for pattern in (f"{ARTIFACT_PREFIX}*", "holo_e2e_*"):
        for path in DESKTOP.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def _cleanup_notepad() -> None:
    with suppress(FileNotFoundError):
        subprocess.run(["taskkill", "/IM", "notepad.exe", "/F"], capture_output=True, check=False)
    time.sleep(0.2)


def _cleanup_notepad_and_desktop() -> None:
    _cleanup_notepad()
    _cleanup_desktop_artifacts()


def _cleanup_calculator() -> None:
    for process_name in ("CalculatorApp.exe", "calc.exe"):
        subprocess.run(["taskkill", "/IM", process_name, "/F"], capture_output=True, check=False)
    time.sleep(0.2)


def _require_screenshot() -> None:
    try:
        import pyautogui

        pyautogui.screenshot()
    except Exception as exc:
        pytest.skip(f"pyautogui screenshot is unavailable in this Windows session: {type(exc).__name__}: {exc}")


def _calculator_command() -> str | None:
    return shutil.which("calc.exe") or shutil.which("CalculatorApp.exe")


class WindowsCalculatorResultEvaluator:
    """Evaluator that checks Windows Calculator's visible result."""

    name = "windows_calculator_result"

    def __init__(self, *, a: int, b: int, expected: int) -> None:
        self.a = a
        self.b = b
        self.expected = expected

    def evaluate(self) -> EvaluationResult:
        display = _windows_calculator_display()
        metadata: FlatMetadata = {"a": self.a, "b": self.b, "expected": self.expected}
        if display is None:
            return EvaluationResult(
                passed=False,
                message="Windows Calculator display unreadable via UI Automation",
                failure_category=FailureCategory.EVALUATOR,
                metadata=metadata,
            )

        result_part = _windows_calculator_result_part(display)
        if result_part != str(self.expected):
            return EvaluationResult(
                passed=False,
                message=(
                    f"Windows Calculator result mismatch for {self.a}+{self.b}: "
                    f"expected {self.expected!r}, got {result_part!r} from display {display!r}"
                ),
                failure_category=FailureCategory.EVALUATOR,
                metadata={**metadata, "display": display, "result_part": result_part},
            )
        return EvaluationResult(
            passed=True,
            message="Windows Calculator result matched",
            metadata={**metadata, "display": display, "result_part": result_part},
        )


class WindowsOpenedFileEvaluator:
    """Evaluator that checks File Explorer opened a seeded text file in Notepad."""

    name = "windows_opened_file"

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
        notepad_titles = _notepad_window_titles()
        matching_title = _notepad_window_for_file(self.path.name, notepad_titles)
        metadata["notepad_window_titles"] = notepad_titles
        if matching_title is None:
            return EvaluationResult(
                passed=False,
                message="seeded file was not visible in a Notepad window",
                failure_category=FailureCategory.AGENT,
                metadata=metadata,
            )
        return EvaluationResult(
            passed=True,
            message="file opened in Notepad",
            metadata={**metadata, "notepad_window_title": matching_title},
        )


def _windows_calculator_display() -> str | None:
    entries = _windows_calculator_uia_entries()
    return _windows_calculator_display_from_uia_entries(entries)


def _notepad_window_for_file(filename: str, titles: list[str] | None = None) -> str | None:
    path = Path(filename)
    candidates = [path.name]
    if path.suffix:
        candidates.append(path.stem)
    for title in titles if titles is not None else _notepad_window_titles():
        if any(candidate and candidate in title for candidate in candidates):
            return title
    return None


def _notepad_window_titles() -> list[str]:
    script = r"""
Get-Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.MainWindowTitle -and (
      $_.ProcessName -like 'notepad*' -or $_.MainWindowTitle -like '*Notepad*'
    )
  } |
  Select-Object -ExpandProperty MainWindowTitle
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _windows_calculator_uia_entries() -> list[dict[str, str]]:
    script = r"""
Add-Type -AssemblyName UIAutomationClient
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::NameProperty,
  "Calculator"
)
$calc = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if ($null -eq $calc) {
  $frameCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ClassNameProperty,
    "ApplicationFrameWindow"
  )
  $frames = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $frameCondition)
  foreach ($frame in $frames) {
    if ($frame.Current.Name -like "*Calculator*") {
      $calc = $frame
      break
    }
  }
}
if ($null -eq $calc) { exit 2 }
$elements = $calc.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$values = New-Object System.Collections.Generic.List[object]
foreach ($element in $elements) {
  $name = $element.Current.Name
  if (-not [string]::IsNullOrWhiteSpace($name)) {
    $values.Add([pscustomobject]@{
      automation_id = $element.Current.AutomationId
      name = $name
      control_type = $element.Current.ControlType.ProgrammaticName
      class_name = $element.Current.ClassName
    })
  }
}
$values | ConvertTo-Json -Compress
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )
    if proc.returncode != 0:
        return []
    return _windows_calculator_uia_entries_from_json(proc.stdout)


def _windows_calculator_uia_entries_from_json(raw: str) -> list[dict[str, str]]:
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [
            {"automation_id": "", "name": line.strip(), "control_type": "", "class_name": ""}
            for line in text.splitlines()
        ]
    items = parsed if isinstance(parsed, list) else [parsed]
    entries: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("Name") or "").strip()
        if not name:
            continue
        entries.append(
            {
                "automation_id": str(item.get("automation_id") or item.get("AutomationId") or ""),
                "name": name,
                "control_type": str(item.get("control_type") or item.get("ControlType") or ""),
                "class_name": str(item.get("class_name") or item.get("ClassName") or ""),
            }
        )
    return entries


def _windows_calculator_display_from_uia_entries(entries: list[dict[str, str]]) -> str | None:
    calculator_results = [
        entry["name"]
        for entry in entries
        if entry.get("automation_id") == "CalculatorResults" and entry.get("name", "").strip()
    ]
    if calculator_results:
        return calculator_results[-1]
    return _windows_calculator_display_from_values([entry["name"] for entry in entries])


def _windows_calculator_display_from_values(values: list[str]) -> str | None:
    if not values:
        return None
    display_values = [value for value in values if value.lower().startswith("display is")]
    if display_values:
        return display_values[-1]
    return " | ".join(values)


def _windows_calculator_result_part(display: str) -> str:
    normalized = calculator_result_part(display)
    # Windows display strings are joined from several UIA values ("History | 4+9 | 13");
    # the result is the last segment. (The macOS read returns just the result text.)
    if "|" in normalized:
        normalized = normalized.rsplit("|", 1)[-1].strip()
    lowered = normalized.lower().strip()
    if lowered.startswith("display is"):
        return normalized[len("display is") :].strip().replace(",", "")
    return normalized.replace(",", "")


def _preserve_windows_calculator_display(artifact_dir: Path) -> None:
    entries = _windows_calculator_uia_entries()
    display = _windows_calculator_display_from_uia_entries(entries)
    text = "<unreadable>\n" if display is None else f"{display}\n"
    (artifact_dir / "calculator-display.txt").write_text(text, encoding="utf-8")
    (artifact_dir / "calculator-uia-entries.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
