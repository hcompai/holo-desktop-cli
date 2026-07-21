from __future__ import annotations

import json
from pathlib import Path

from ._report import (
    TaskResult,
    append_task_summary,
    build_aggregate_summary,
    build_platform_summary,
    ensure_expected_task_results,
    load_task_result,
    load_task_results,
    render_aggregate_markdown,
    render_task_markdown,
    task_ids_for_platform,
    task_ids_for_shard,
    write_platform_report,
)

STABLE_CI_TASK_IDS = [
    "browser_download_file",
    "calculator_ci_smoke",
    "finder_copy_file",
    "finder_create_folder",
    "finder_open_file_by_double_click",
    "finder_protected_file",
    "foreground_visible_editor_witness",
    "textedit_type_sentinel",
]


def _task_result(
    *,
    task_id: str = "task",
    environment_id: str = "windows-foreground",
    passed: bool = True,
    skipped: bool = False,
    failure_category: str | None = None,
    message: str = "ok",
    duration_s: float | None = 10.0,
    avg_step_s: float | None = 4.0,
    artifact_dir: Path,
    command: list[str] | None = None,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        environment_id=environment_id,
        passed=passed,
        skipped=skipped,
        failure_category=failure_category,
        message=message,
        duration_s=duration_s,
        avg_step_s=avg_step_s,
        artifact_dir=artifact_dir,
        command=command if command is not None else ["uv", "run", "holo", "run", task_id, "--profile"],
    )


def _write_result_json(
    root: Path,
    *,
    task_id: str,
    environment_id: str = "windows-foreground",
    passed: bool,
    failure_category: str | None = None,
    duration_s: float = 10.0,
    avg_step_s: float | None = 4.0,
) -> Path:
    task_dir = root / task_id
    task_dir.mkdir(parents=True)
    timing = {"steps_timed": 3, "avg_step_s": avg_step_s} if avg_step_s is not None else {}
    payload = {
        "task_id": task_id,
        "environment_id": environment_id,
        "execution": "foreground",
        "driver": "pyautogui",
        "command": ["uv", "run", "holo", "run", "do it", "--profile"],
        "exit_code": 0 if passed else 1,
        "duration_s": duration_s,
        "event_log_path": None,
        "copied_event_log_path": str(task_dir / "events.jsonl"),
        "assertion_passed": passed,
        "failure_category": failure_category,
        "artifact_dir": str(task_dir),
        "message": "ok" if passed else "failed",
        "metadata": {"timing": timing} if timing else {},
    }
    path = task_dir / "result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_task_results_reads_nested_result_files(tmp_path: Path) -> None:
    _write_result_json(tmp_path, task_id="calculator_ci_smoke", passed=True)
    _write_result_json(tmp_path, task_id="failed_task", passed=False, failure_category="agent")

    results = load_task_results(tmp_path)

    assert [result.task_id for result in results] == ["calculator_ci_smoke", "failed_task"]
    assert results[0].passed is True
    assert results[1].failure_category == "agent"


def test_load_task_result_uses_requested_task_not_latest_mtime(tmp_path: Path) -> None:
    older = _write_result_json(tmp_path, task_id="wanted", passed=True)
    newer = _write_result_json(tmp_path, task_id="other", passed=False, failure_category="agent")
    older.touch()
    newer.touch()

    result = load_task_result(tmp_path, "wanted")

    assert result is not None
    assert result.task_id == "wanted"
    assert result.passed is True


def test_append_task_summary_synthesizes_missing_result(tmp_path: Path) -> None:
    result = append_task_summary(tmp_path, "missing_task", platform="Windows")

    assert result.task_id == "missing_task"
    assert result.passed is False
    assert result.skipped is False
    assert result.failure_category == "harness"
    assert result.environment_id == "windows-foreground"
    assert "without writing result.json" in result.message
    assert (tmp_path / "missing__missing_task" / "result.json").exists()


def test_append_task_summary_strips_task_id_line_endings(tmp_path: Path) -> None:
    result = append_task_summary(tmp_path, "missing_task\r", platform="Windows")

    assert result.task_id == "missing_task"
    assert (tmp_path / "missing__missing_task" / "result.json").exists()


def test_ensure_expected_task_results_backfills_missing_tasks(tmp_path: Path) -> None:
    _write_result_json(tmp_path, task_id="present", passed=True)

    results = ensure_expected_task_results(tmp_path, ["missing", "present"], platform="macOS")
    summary = build_platform_summary("macOS", results)

    assert [result.task_id for result in results] == ["missing", "present"]
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.total == 2
    assert summary.pass_rate == 50.0
    assert summary.failure_categories == {"harness": 1}


def test_build_platform_summary_counts_pass_fail_skip_and_average_step(tmp_path: Path) -> None:
    results = [
        _task_result(
            task_id="a",
            passed=True,
            duration_s=10.0,
            avg_step_s=4.0,
            artifact_dir=tmp_path / "a",
        ),
        _task_result(
            task_id="b",
            passed=False,
            failure_category="agent",
            message="missed",
            duration_s=20.0,
            avg_step_s=8.0,
            artifact_dir=tmp_path / "b",
        ),
        _task_result(
            task_id="c",
            passed=False,
            skipped=True,
            failure_category="environment",
            message="preflight skipped",
            duration_s=None,
            avg_step_s=None,
            artifact_dir=tmp_path / "c",
        ),
    ]

    summary = build_platform_summary("Windows", results)

    assert summary.platform == "Windows"
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.skipped == 1
    assert summary.total == 3
    assert summary.pass_rate == 50.0
    assert summary.failure_categories == {"agent": 1, "environment": 1}
    assert summary.avg_step_s == 6.0


def test_render_task_markdown_contains_profile_and_message(tmp_path: Path) -> None:
    result = _task_result(
        task_id="calculator_ci_smoke",
        environment_id="macos-foreground",
        message="calculator display matched 4",
        duration_s=56.3,
        avg_step_s=4.73,
        artifact_dir=tmp_path,
        command=["uv", "run", "holo", "run", "2+2", "--profile"],
    )

    markdown = render_task_markdown(result)

    assert "## PASS: `calculator_ci_smoke`" in markdown
    assert "Environment: `macos-foreground`" in markdown
    assert "avg_step_s: `4.73`" in markdown
    assert "calculator display matched 4" in markdown


def test_write_platform_report_writes_summary_json_markdown_and_jsonl(tmp_path: Path) -> None:
    result = _task_result(
        task_id="calculator_ci_smoke",
        duration_s=12.0,
        avg_step_s=3.0,
        artifact_dir=tmp_path / "task",
        command=["uv", "run", "holo", "run", "2+2", "--profile"],
    )
    summary = build_platform_summary("Windows", [result])

    write_platform_report(tmp_path / "report", summary)

    assert json.loads((tmp_path / "report" / "summary.json").read_text(encoding="utf-8"))["passed"] == 1
    assert "| Windows | 1 | 0 | 0 | 1 | 100.0% | 3.0s |" in (tmp_path / "report" / "summary.md").read_text(
        encoding="utf-8"
    )
    assert json.loads((tmp_path / "report" / "task-results.jsonl").read_text(encoding="utf-8"))["task_id"] == (
        "calculator_ci_smoke"
    )


def test_task_ids_for_platform_returns_registered_runner_tasks() -> None:
    macos_ids = task_ids_for_platform("darwin")
    windows_ids = task_ids_for_platform("win32")
    linux_ids = task_ids_for_platform("linux")

    assert macos_ids == STABLE_CI_TASK_IDS
    assert windows_ids == STABLE_CI_TASK_IDS
    assert linux_ids == STABLE_CI_TASK_IDS
    assert macos_ids == sorted(macos_ids)
    assert windows_ids == sorted(windows_ids)
    assert linux_ids == sorted(linux_ids)


def test_missing_linux_task_uses_linux_environment_identity(tmp_path: Path) -> None:
    [result] = ensure_expected_task_results(tmp_path, ["missing"], platform="Linux")

    assert result.environment_id == "linux-foreground"


def test_task_ids_for_shard_partition_without_overlap() -> None:
    all_ids = task_ids_for_platform("darwin")
    shards = [task_ids_for_shard("darwin", shard_index=index, shard_total=4) for index in range(4)]
    flattened = [task_id for shard in shards for task_id in shard]

    assert sorted(flattened) == all_ids
    assert len(flattened) == len(set(flattened))
    assert max(len(shard) for shard in shards) - min(len(shard) for shard in shards) <= 1


def test_build_aggregate_summary_merges_platform_shards(tmp_path: Path) -> None:
    windows_shard_1 = build_platform_summary(
        "Windows",
        [
            _task_result(
                task_id="a",
                duration_s=1.0,
                avg_step_s=4.0,
                artifact_dir=tmp_path / "a",
                command=[],
            ),
            _task_result(
                task_id="b",
                passed=False,
                failure_category="agent",
                message="fail",
                duration_s=2.0,
                avg_step_s=6.0,
                artifact_dir=tmp_path / "b",
                command=[],
            ),
        ],
    )
    windows_shard_2 = build_platform_summary(
        "Windows",
        [
            _task_result(
                task_id="d",
                duration_s=4.0,
                avg_step_s=10.0,
                artifact_dir=tmp_path / "d",
                command=[],
            )
        ],
    )
    macos = build_platform_summary(
        "macOS",
        [
            _task_result(
                task_id="c",
                environment_id="macos-foreground",
                duration_s=3.0,
                avg_step_s=8.0,
                artifact_dir=tmp_path / "c",
                command=[],
            )
        ],
    )

    aggregate = build_aggregate_summary([macos, windows_shard_1, windows_shard_2])

    assert aggregate.passed == 3
    assert aggregate.failed == 1
    assert aggregate.total == 4
    assert aggregate.pass_rate == 75.0
    assert len(aggregate.platforms) == 2
    assert aggregate.platforms[0].platform == "macOS"
    assert aggregate.platforms[1].platform == "Windows"
    assert aggregate.platforms[1].passed == 2
    assert aggregate.platforms[1].failed == 1


def test_render_aggregate_markdown_contains_platform_rows(tmp_path: Path) -> None:
    summary = build_platform_summary(
        "Windows",
        [
            _task_result(
                task_id="a",
                duration_s=1.0,
                avg_step_s=4.0,
                artifact_dir=tmp_path / "a",
                command=[],
            )
        ],
    )

    markdown = render_aggregate_markdown(build_aggregate_summary([summary]))

    assert "# Holo Full E2E Summary" in markdown
    assert "| Windows | 1 | 0 | 0 | 1 | 100.0% | 4.0s |" in markdown
    assert "| Overall | 1 | 0 | 0 | 1 | 100.0% | 4.0s |" in markdown
