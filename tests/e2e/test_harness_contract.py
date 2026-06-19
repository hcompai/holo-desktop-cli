import json
import subprocess
from pathlib import Path

import pytest

from holo_desktop.settings import load_holo_settings

from . import _harness, _macos
from ._artifacts import E2EArtifacts, E2EResult
from ._domain import EvaluationResult, FailureCategory, PreparedTask
from ._environment import UnsupportedEnvironmentError, runner_for_platform
from ._runner import HoloRunResult, find_event_log_path, find_latest_event_log, run_holo_foreground
from .conftest import HoloLiveConfig, _selected_task_ids
from .environments import windows as _windows
from .environments.macos import MACOS_FOREGROUND_TASKS
from .environments.windows import WINDOWS_FOREGROUND_TASKS, WindowsEnvironmentRunner
from .evaluators.browser import DownloadedFileEvaluator
from .evaluators.calculator import CalculatorResultEvaluator, calculator_result_part
from .evaluators.finder import CopiedFileEvaluator, OpenedFileEvaluator, ProtectedFileEvaluator
from .evaluators.textedit import TextEditContainsEvaluator
from .tasks import CALCULATOR_CI_SMOKE, FINDER_OPEN_FILE_BY_DOUBLE_CLICK


class _PassingEvaluator:
    name = "passing"

    def evaluate(self):
        raise AssertionError("not used")


class _SuccessfulEvaluator:
    name = "successful"

    def evaluate(self) -> EvaluationResult:
        return EvaluationResult(passed=True, message="ok")


def _holo_live_config(*, timeout_s: float = 30.0) -> HoloLiveConfig:
    return HoloLiveConfig(
        enabled=True,
        timeout_s=timeout_s,
        model=None,
        base_url=None,
        task_ids=[],
    )


def test_find_event_log_path_from_holo_stderr() -> None:
    stderr = "some line\n\x1b[2mevents streamed to\x1b[0m \x1b[36m/tmp/holo/events.jsonl\x1b[0m\n"

    assert find_event_log_path(stderr) == Path("/tmp/holo/events.jsonl")


def test_find_event_log_path_from_wrapped_holo_stderr() -> None:
    stderr = "events streamed to \n/tmp/holo/wrapped/events.jsonl\n"

    assert find_event_log_path(stderr) == Path("/tmp/holo/wrapped/events.jsonl")


def test_find_latest_event_log_returns_newest_run_log(tmp_path: Path) -> None:
    older = tmp_path / "older" / "events.jsonl"
    newer = tmp_path / "newer" / "events.jsonl"
    older.parent.mkdir()
    newer.parent.mkdir()
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    newer.touch()

    assert find_latest_event_log(tmp_path) == newer


def test_timeout_result_falls_back_to_latest_event_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event_log = tmp_path / "run-id" / "events.jsonl"
    event_log.parent.mkdir()
    event_log.write_text("partial trace", encoding="utf-8")

    def timeout_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["uv", "run", "holo"], timeout=0.01, output="", stderr="")

    monkeypatch.setattr(subprocess, "run", timeout_run)

    result = run_holo_foreground(
        task="do something",
        runs_dir=tmp_path,
        config=_holo_live_config(timeout_s=0.01),
        stream_output=False,
    )

    assert result.exit_code == 124
    assert result.event_log_path == event_log


def test_holo_max_time_is_inside_subprocess_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_holo_foreground(
        task="do something",
        runs_dir=tmp_path,
        config=_holo_live_config(timeout_s=30.0),
        max_time_s=120.0,
        stream_output=False,
    )

    max_time_index = captured_command.index("--max-time-s") + 1
    assert captured_command[max_time_index] == "25.0"


def test_run_and_evaluate_uses_live_timeout_for_holo_max_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_max_time_s: float | None = None

    def fake_run_holo_foreground(**kwargs: object) -> HoloRunResult:
        nonlocal captured_max_time_s
        max_time_s = kwargs["max_time_s"]
        assert isinstance(max_time_s, float)
        captured_max_time_s = max_time_s
        return HoloRunResult(
            command=["uv", "run", "holo"],
            exit_code=0,
            stdout="",
            stderr="",
            duration_s=1.0,
            event_log_path=None,
        )

    monkeypatch.setattr(_harness, "run_holo_foreground", fake_run_holo_foreground)
    monkeypatch.setattr(E2EArtifacts, "capture_screenshot", lambda self, *, before: None)
    artifacts = E2EArtifacts.create(tmp_path / "artifacts")
    prepared = PreparedTask(
        case=MACOS_FOREGROUND_TASKS[0],
        instruction="do it",
        workspace=tmp_path,
        evaluator=_SuccessfulEvaluator(),
    )

    _harness.run_and_evaluate(
        prepared=prepared,
        artifacts=artifacts,
        config=_holo_live_config(timeout_s=240.0),
        environment_id="macos-foreground",
    )

    assert captured_max_time_s == 240.0


def test_run_and_evaluate_rejects_zero_step_holo_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event_log_path = tmp_path / "runs" / "events.jsonl"
    event_log_path.parent.mkdir()
    event_log_path.write_text(
        json.dumps(
            {
                "event": {
                    "kind": "step_timings",
                    "steps": [],
                    "avg_observe_s": None,
                    "avg_llm_s": None,
                    "avg_tool_s": None,
                    "avg_step_s": None,
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_run_holo_foreground(**kwargs: object) -> HoloRunResult:
        return HoloRunResult(
            command=["uv", "run", "holo"],
            exit_code=0,
            stdout="",
            stderr="",
            duration_s=1.0,
            event_log_path=event_log_path,
        )

    monkeypatch.setattr(_harness, "run_holo_foreground", fake_run_holo_foreground)
    monkeypatch.setattr(E2EArtifacts, "capture_screenshot", lambda self, *, before: None)
    artifacts = E2EArtifacts.create(tmp_path / "artifacts")
    prepared = PreparedTask(
        case=MACOS_FOREGROUND_TASKS[0],
        instruction="do it",
        workspace=tmp_path,
        evaluator=_SuccessfulEvaluator(),
    )

    with pytest.raises(AssertionError, match="zero timed agent steps"):
        _harness.run_and_evaluate(
            prepared=prepared,
            artifacts=artifacts,
            config=_holo_live_config(timeout_s=30.0),
            environment_id="macos-foreground",
        )

    result = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
    assert result["failure_category"] == FailureCategory.HOLO_COMMAND.value
    # extract_step_timings yields no summary for a step-less log, so the result records no timing at all.
    assert "timing" not in result["metadata"]


def test_holo_run_command_uses_agent_api_runtime_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_holo_foreground(
        task="do something",
        runs_dir=tmp_path,
        config=_holo_live_config(),
        stream_output=False,
    )

    assert "--runs-dir" in captured_command
    assert "--max-steps" in captured_command
    assert "--max-time-s" in captured_command
    assert "--fast" not in captured_command


def test_holo_run_command_passes_fast_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_holo_foreground(
        task="do something",
        runs_dir=tmp_path,
        config=HoloLiveConfig(enabled=True, timeout_s=30.0, model=None, base_url=None, task_ids=[], fast=True),
        stream_output=False,
    )

    assert "--fast" in captured_command


def test_textedit_evaluator_reports_applescript_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _macos,
        "textedit_documents_text",
        lambda: _macos.TextEditDocumentsError("TextEdit AppleScript failed with code 124: timed out"),
    )

    result = TextEditContainsEvaluator("HOLO_E2E_SENTINEL").evaluate()

    assert not result.passed
    assert result.failure_category == FailureCategory.EVALUATOR
    assert result.message == "TextEdit AppleScript failed with code 124: timed out"


def test_textedit_document_read_retries_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []

    def fake_run_osascript(script: str, *, check: bool, timeout_s: float) -> subprocess.CompletedProcess[str]:
        calls.append(timeout_s)
        if len(calls) == 1:
            return subprocess.CompletedProcess(["osascript"], 124, "", "osascript timed out after 20.0s")
        return subprocess.CompletedProcess(["osascript"], 0, "open fixture token\n", "")

    monkeypatch.setattr(_macos, "run_osascript", fake_run_osascript)
    monkeypatch.setattr(_macos.time, "sleep", lambda seconds: None)

    result = _macos.textedit_documents_text()

    assert result == _macos.TextEditDocuments(["open fixture token"])
    assert calls == [20.0, 30.0]


def test_opened_file_evaluator_accepts_textedit_trimmed_trailing_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_path = tmp_path / "fixture.txt"
    target_path.write_text("open fixture token\n", encoding="utf-8")
    monkeypatch.setattr(_macos, "textedit_documents_text", lambda: _macos.TextEditDocuments(["open fixture token"]))

    result = OpenedFileEvaluator(target_path, "open fixture token\n").evaluate()

    assert result.passed


def test_artifact_result_schema_serializes_paths(tmp_path: Path) -> None:
    artifacts = E2EArtifacts.create(tmp_path / "artifacts")

    artifacts.write_result(
        E2EResult(
            task_id="task",
            environment_id="macos-foreground",
            execution="foreground",
            driver="pyautogui",
            command=["uv", "run", "holo"],
            exit_code=0,
            duration_s=1.5,
            event_log_path=tmp_path / "runs" / "events.jsonl",
            copied_event_log_path=artifacts.events_path,
            assertion_passed=True,
            failure_category=None,
            artifact_dir=artifacts.root,
            message="passed",
            metadata={"target_path": str(tmp_path / "target.txt")},
        )
    )

    payload = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
    assert payload["event_log_path"] == str(tmp_path / "runs" / "events.jsonl")
    assert payload["copied_event_log_path"] == str(artifacts.events_path)
    assert payload["artifact_dir"] == str(artifacts.root)
    assert payload["environment_id"] == "macos-foreground"


def test_flatten_timing_drops_per_step_list_keeps_scalars() -> None:
    flattened = _harness._flatten_timing(
        {
            "steps": [{"step_idx": 0, "tool_name": "click_desktop", "failed": False}],
            "avg_step_s": 4.2,
            "steps_timed": 1,
        }
    )
    assert "steps" not in flattened
    assert flattened == {"avg_step_s": 4.2, "steps_timed": 1}


def test_artifact_result_schema_serializes_per_step_timing(tmp_path: Path) -> None:
    # A timing summary carries a per-step list of dicts; the flat result metadata must
    # still validate and serialize (regression for the live-run E2EResult ValidationError).
    artifacts = E2EArtifacts.create(tmp_path / "artifacts")
    timing = {
        "steps": [{"step_idx": 0, "tool_name": "write_desktop", "failed": False}],
        "avg_step_s": 5.0,
        "steps_timed": 1,
    }

    artifacts.write_result(
        E2EResult(
            task_id="task",
            environment_id="macos-foreground",
            execution="foreground",
            driver="pyautogui",
            command=["uv", "run", "holo"],
            exit_code=0,
            duration_s=1.5,
            event_log_path=tmp_path / "runs" / "events.jsonl",
            copied_event_log_path=artifacts.events_path,
            assertion_passed=True,
            failure_category=None,
            artifact_dir=artifacts.root,
            message="passed",
            metadata={"timing": _harness._flatten_timing(timing)},
        )
    )

    payload = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["timing"]["steps_timed"] == 1
    assert "steps" not in payload["metadata"]["timing"]


def test_prepared_task_preserves_final_artifacts(tmp_path: Path) -> None:
    target = tmp_path / "final"
    target.mkdir()

    def preserve(artifact_dir: Path) -> None:
        (artifact_dir / "snapshot.txt").write_text("saved", encoding="utf-8")

    prepared = PreparedTask(
        case=MACOS_FOREGROUND_TASKS[0],
        instruction="do it",
        workspace=tmp_path,
        evaluator=_PassingEvaluator(),
        preserve_artifacts=preserve,
    )

    prepared.preserve_final_artifacts(target)

    assert (target / "snapshot.txt").read_text(encoding="utf-8") == "saved"


def test_artifact_preserve_errors_are_recorded(tmp_path: Path) -> None:
    artifacts = E2EArtifacts.create(tmp_path / "artifacts")
    prepared = PreparedTask(
        case=MACOS_FOREGROUND_TASKS[0],
        instruction="do it",
        workspace=tmp_path,
        evaluator=_PassingEvaluator(),
        preserve_artifacts=lambda artifact_dir: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    artifacts.preserve_final_artifacts(prepared)

    assert "RuntimeError: boom" in (artifacts.final_dir / "preserve-error.txt").read_text(encoding="utf-8")


def test_selected_task_ids_accepts_comma_separated_values(pytestconfig: pytest.Config) -> None:
    pytestconfig.option.holo_live_task_ids = (
        "textedit_type_sentinel,finder_create_folder, foreground_visible_editor_witness "
    )

    assert _selected_task_ids(pytestconfig) == [
        "textedit_type_sentinel",
        "finder_create_folder",
        "foreground_visible_editor_witness",
    ]


def test_artifact_root_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "full-e2e-artifacts"
    monkeypatch.setenv("HOLO_E2E_ARTIFACT_ROOT", str(override))

    assert load_holo_settings().test.artifact_root == override


STABLE_CI_TASK_IDS = {
    "browser_download_file",
    "calculator_ci_smoke",
    "finder_copy_file",
    "finder_create_folder",
    "finder_open_file_by_double_click",
    "finder_protected_file",
    "foreground_visible_editor_witness",
    "textedit_type_sentinel",
}


def test_macos_task_catalog_contains_stable_ci_task_ids() -> None:
    assert {task.id for task in MACOS_FOREGROUND_TASKS} == STABLE_CI_TASK_IDS


def test_windows_runner_supports_stable_ci_task_catalog() -> None:
    assert {task.id for task in WINDOWS_FOREGROUND_TASKS} == STABLE_CI_TASK_IDS


def test_double_click_repro_task_is_registered_on_macos_and_windows() -> None:
    assert FINDER_OPEN_FILE_BY_DOUBLE_CLICK.id == "finder_open_file_by_double_click"
    assert FINDER_OPEN_FILE_BY_DOUBLE_CLICK in MACOS_FOREGROUND_TASKS
    assert FINDER_OPEN_FILE_BY_DOUBLE_CLICK in WINDOWS_FOREGROUND_TASKS


def test_removed_unstable_task_ids_are_not_registered() -> None:
    registered_ids = {task.id for task in (*MACOS_FOREGROUND_TASKS, *WINDOWS_FOREGROUND_TASKS)}

    assert registered_ids.isdisjoint(
        {
            "browser_local_form_fill",
            "browser_to_file_transfer",
            "browser_upload_file",
            "calculator_addition",
            "calculator_foreground_takeover",
            "finder_move_file",
            "finder_rename_file",
            "notes_create_note",
            "preview_rotate_image",
            "textedit_save_to_desktop",
        }
    )


def test_removed_unstable_task_ids_are_not_exported() -> None:
    from . import tasks

    exported_ids = {getattr(tasks, name).id for name in tasks.__all__}

    assert exported_ids == {
        "browser_download_file",
        "calculator_ci_smoke",
        "finder_copy_file",
        "finder_create_folder",
        "finder_open_file_by_double_click",
        "finder_protected_file",
        "foreground_visible_editor_witness",
        "textedit_type_sentinel",
    }


def test_macos_task_preparation_does_not_launch_target_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_desktop = tmp_path / "desktop"
    fake_desktop.mkdir()
    monkeypatch.setattr(_macos, "DESKTOP", fake_desktop)

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("cold-start e2e task preparation must not launch target apps")

    for helper_name in (
        "open_file_in_textedit",
        "new_textedit_document",
        "open_finder_desktop",
        "open_calculator_basic",
        "open_notes",
        "open_preview_image",
        "ensure_frontmost_app",
    ):
        monkeypatch.setattr(_macos, helper_name, fail_if_called)

    monkeypatch.setattr(_macos, "delete_test_notes", lambda: None)
    # clean_up() legitimately quits and refocuses apps, but those paths shell out to osascript;
    # keep it off real desktops and non-macOS CI. Stub the wrappers (each sleeps 0.4s) and the
    # osascript chokepoint itself so no cleanup path can reach a real process.
    monkeypatch.setattr(_macos, "quit_app", lambda *args, **kwargs: None)
    monkeypatch.setattr(_macos, "activate_app", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        _macos,
        "run_osascript",
        lambda script, **kwargs: subprocess.CompletedProcess(["osascript"], returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(_macos, "cursor_position", lambda: (0, 0))
    monkeypatch.setattr(_macos, "frontmost_app_name", lambda: "Chrome")
    monkeypatch.setattr(_macos, "create_png", lambda path, *, size: path.write_bytes(b"png fixture"))

    for task in MACOS_FOREGROUND_TASKS:
        workspace = tmp_path / task.id
        workspace.mkdir()
        prepared = task.prepare(workspace)
        try:
            assert "Open " in prepared.instruction
            for key in ("target_path", "old_path", "new_path", "image_path"):
                path = prepared.metadata.get(key)
                if isinstance(path, str):
                    assert Path(path).is_relative_to(fake_desktop)
        finally:
            prepared.clean_up()


def test_environment_runner_selection() -> None:
    macos_runner = runner_for_platform("darwin")
    windows_runner = runner_for_platform("win32")

    assert macos_runner.environment_id == "macos-foreground"
    assert windows_runner.environment_id == "windows-foreground"
    with pytest.raises(UnsupportedEnvironmentError):
        runner_for_platform("linux")


def test_calculator_ci_smoke_is_available_on_macos_and_windows() -> None:
    assert CALCULATOR_CI_SMOKE.id == "calculator_ci_smoke"
    assert CALCULATOR_CI_SMOKE in MACOS_FOREGROUND_TASKS
    assert CALCULATOR_CI_SMOKE in WINDOWS_FOREGROUND_TASKS


def test_calculator_ci_smoke_macos_prepares_two_plus_two(tmp_path: Path) -> None:
    prepared = CALCULATOR_CI_SMOKE.prepare(tmp_path)

    assert "2 plus 2" in prepared.instruction
    assert "Do not use Terminal" in prepared.instruction
    assert prepared.metadata["a"] == 2
    assert prepared.metadata["b"] == 2
    assert prepared.metadata["expected"] == 4
    assert isinstance(prepared.evaluator, CalculatorResultEvaluator)


def test_calculator_ci_smoke_windows_prepares_two_plus_two(tmp_path: Path) -> None:
    runner = WindowsEnvironmentRunner()
    prepared = runner.prepare(CALCULATOR_CI_SMOKE, tmp_path)

    assert "2 plus 2" in prepared.instruction
    assert "PowerShell" in prepared.instruction
    assert "Command Prompt" in prepared.instruction
    assert prepared.metadata["a"] == 2
    assert prepared.metadata["b"] == 2
    assert prepared.metadata["expected"] == 4
    assert prepared.evaluator.name == "windows_calculator_result"


def test_finder_open_file_by_double_click_prepares_desktop_text_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_desktop = tmp_path / "desktop"
    fake_desktop.mkdir()
    monkeypatch.setattr(_macos, "DESKTOP", fake_desktop)

    prepared = FINDER_OPEN_FILE_BY_DOUBLE_CLICK.prepare(tmp_path)
    target_path = Path(str(prepared.metadata["target_path"]))

    assert target_path.parent == fake_desktop
    assert target_path.name.endswith(".txt")
    assert target_path.exists()
    assert target_path.read_text(encoding="utf-8") == prepared.metadata["expected_content"]
    assert "double-click" in prepared.instruction
    assert target_path.name in prepared.instruction
    assert "Do not use Terminal" in prepared.instruction
    assert isinstance(prepared.evaluator, OpenedFileEvaluator)


def test_windows_open_file_by_double_click_prepares_desktop_text_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_desktop = tmp_path / "desktop"
    fake_desktop.mkdir()
    monkeypatch.setattr(_windows, "DESKTOP", fake_desktop)
    runner = WindowsEnvironmentRunner()

    prepared = runner.prepare(FINDER_OPEN_FILE_BY_DOUBLE_CLICK, tmp_path)
    target_path = Path(str(prepared.metadata["target_path"]))

    assert target_path.parent == fake_desktop
    assert target_path.name.endswith(".txt")
    assert target_path.exists()
    assert target_path.read_text(encoding="utf-8") == prepared.metadata["expected_content"]
    assert "double-click" in prepared.instruction
    assert "File Explorer" in prepared.instruction
    assert target_path.name in prepared.instruction
    assert "PowerShell" in prepared.instruction
    assert prepared.evaluator.name == "windows_opened_file"


def test_seeded_text_file_tasks_use_desktop_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    macos_desktop = tmp_path / "macos-desktop"
    windows_desktop = tmp_path / "windows-desktop"
    macos_workspace = tmp_path / "macos-workspace"
    windows_workspace = tmp_path / "windows-workspace"
    for path in (macos_desktop, windows_desktop, macos_workspace, windows_workspace):
        path.mkdir()

    monkeypatch.setattr(_macos, "DESKTOP", macos_desktop)
    monkeypatch.setattr(_windows, "DESKTOP", windows_desktop)

    seeded_task_ids = {"foreground_visible_editor_witness", "textedit_type_sentinel"}
    macos_tasks_by_id = {task.id: task for task in MACOS_FOREGROUND_TASKS}
    windows_tasks_by_id = {task.id: task for task in WINDOWS_FOREGROUND_TASKS}
    windows_runner = WindowsEnvironmentRunner()

    assert seeded_task_ids <= macos_tasks_by_id.keys()
    assert seeded_task_ids <= windows_tasks_by_id.keys()

    for task_id in seeded_task_ids:
        task = macos_tasks_by_id[task_id]
        prepared = task.prepare(macos_workspace)
        target_path = Path(str(prepared.metadata["target_path"]))
        assert target_path.parent == macos_desktop
        assert target_path.exists()
        assert macos_workspace not in target_path.parents

    for task_id in seeded_task_ids:
        task = windows_tasks_by_id[task_id]
        prepared = windows_runner.prepare(task, windows_workspace)
        target_path = Path(str(prepared.metadata["target_path"]))
        assert target_path.parent == windows_desktop
        assert target_path.exists()
        assert windows_workspace not in target_path.parents


def test_calculator_result_part_strips_bidi_marks() -> None:
    # Real shape from the StandardInputView AX read on the SwiftUI Calculator.
    assert calculator_result_part("\u200e1\u200e3") == "13"


def test_macos_calculator_display_falls_back_to_app_static_text_values() -> None:
    # Real shape from macos-14 CI where StandardInputView was absent but the app
    # static-text dump still contained the visible result.
    assert _macos._calculator_display_from_static_text_values(["4"]) == "4"


def test_windows_calculator_display_prefers_display_text() -> None:
    display = _windows._windows_calculator_display_from_values(["History", "Display is 13", "Memory is clear"])

    assert display == "Display is 13"
    assert _windows._windows_calculator_result_part(display) == "13"


def test_windows_calculator_display_fallback_keeps_later_result_values() -> None:
    display = _windows._windows_calculator_display_from_values(["History", "4+9", "13"])

    assert display == "History | 4+9 | 13"
    assert _windows._windows_calculator_result_part(display) == "13"


def test_windows_calculator_display_from_uia_entries_prefers_calculator_results() -> None:
    display = _windows._windows_calculator_display_from_uia_entries(
        [
            {"automation_id": "History", "name": "History", "control_type": "Text"},
            {"automation_id": "CalculatorResults", "name": "Display is \u200e13", "control_type": "Text"},
            {"automation_id": "Memory", "name": "Memory is clear", "control_type": "Text"},
        ]
    )

    assert display == "Display is \u200e13"
    assert _windows._windows_calculator_result_part(display) == "13"


def test_windows_notepad_window_match_accepts_hidden_txt_extension() -> None:
    title = "0holoe2eopenbydoubleclick38516669 - Notepad"

    assert _windows._notepad_window_for_file("0holoe2eopenbydoubleclick38516669.txt", [title]) == title


def test_windows_cleanup_calculator_does_not_kill_shared_uwp_host(monkeypatch: pytest.MonkeyPatch) -> None:
    killed_processes: list[str] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        killed_processes.append(args[args.index("/IM") + 1])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(_windows.subprocess, "run", fake_run)
    monkeypatch.setattr(_windows.time, "sleep", lambda _: None)

    _windows._cleanup_calculator()

    assert killed_processes == ["CalculatorApp.exe", "calc.exe"]
    assert "ApplicationFrameHost.exe" not in killed_processes


def test_windows_calculator_result_part_strips_bidi_marks_from_display_prefix() -> None:
    assert _windows._windows_calculator_result_part("Display is \u200e1,234") == "1234"


def test_windows_calculator_result_part_falls_back_to_pipe_split() -> None:
    assert _windows._windows_calculator_result_part("4+9 | 13") == "13"


def test_calculator_evaluator_exact_matches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_macos, "calculator_display", lambda: "‎1‎3")

    result = CalculatorResultEvaluator(a=4, b=9, expected=13).evaluate()

    assert result.passed


def test_calculator_evaluator_rejects_substring_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_macos, "calculator_display", lambda: "‎1‎1‎3")

    result = CalculatorResultEvaluator(a=4, b=9, expected=13).evaluate()

    assert not result.passed
    # A readable display with the wrong value is a determined agent failure,
    # not an inconclusive evaluator read.
    assert result.failure_category == FailureCategory.AGENT


def test_copied_file_evaluator_requires_both_files_with_content(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    copied_path = tmp_path / "target" / "source.txt"
    copied_path.parent.mkdir()
    source_path.write_text("expected", encoding="utf-8")
    copied_path.write_text("expected", encoding="utf-8")

    result = CopiedFileEvaluator(source_path, copied_path, "expected").evaluate()

    assert result.passed


def test_protected_file_evaluator_rejects_changed_content(tmp_path: Path) -> None:
    protected_path = tmp_path / "protected.txt"
    protected_path.write_text("changed", encoding="utf-8")

    result = ProtectedFileEvaluator(protected_path, "expected").evaluate()

    assert not result.passed
    assert result.failure_category == FailureCategory.AGENT
    assert "content changed" in result.message


def test_downloaded_file_evaluator_matches_exact_content(tmp_path: Path) -> None:
    path = tmp_path / "download.txt"
    path.write_text("expected", encoding="utf-8")

    result = DownloadedFileEvaluator(path, "expected").evaluate()

    assert result.passed


def test_downloaded_file_evaluator_rejects_wrong_content(tmp_path: Path) -> None:
    path = tmp_path / "download.txt"
    path.write_text("wrong", encoding="utf-8")

    result = DownloadedFileEvaluator(path, "expected").evaluate()

    assert not result.passed
    assert result.failure_category == FailureCategory.AGENT
    assert "content did not match" in result.message
