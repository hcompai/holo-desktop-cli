from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._environment import runner_for_platform


class RawE2EResult(BaseModel):
    """Subset of the harness result JSON consumed by report rendering."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    environment_id: str = "unknown"
    command: list[str] = Field(default_factory=list)
    duration_s: float | None = None
    assertion_passed: bool = False
    skipped: bool = False
    failure_category: str | None = None
    artifact_dir: Path
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Normalized report row for one task attempt."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    environment_id: str
    passed: bool
    skipped: bool
    failure_category: str | None
    message: str
    duration_s: float | None
    avg_step_s: float | None
    artifact_dir: Path
    command: list[str]


class PlatformSummary(BaseModel):
    """Summary for one OS job or shard."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    platform: str
    results: list[TaskResult]
    passed: int
    failed: int
    skipped: int
    total: int
    pass_rate: float
    failure_categories: dict[str, int]
    avg_step_s: float | None


class AggregateSummary(BaseModel):
    """Summary across all OS jobs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    platforms: list[PlatformSummary]
    passed: int
    failed: int
    skipped: int
    total: int
    pass_rate: float
    avg_step_s: float | None


def task_ids_for_platform(platform: str) -> list[str]:
    runner = runner_for_platform(platform)
    return sorted(task.id for task in runner.task_cases)


def task_ids_for_shard(platform: str, *, shard_index: int, shard_total: int) -> list[str]:
    if shard_total <= 0:
        raise ValueError("shard_total must be positive")
    if shard_index < 0 or shard_index >= shard_total:
        raise ValueError("shard_index must be between 0 and shard_total - 1")
    return [
        task_id for index, task_id in enumerate(task_ids_for_platform(platform)) if index % shard_total == shard_index
    ]


def load_task_results(root: Path) -> list[TaskResult]:
    return [_task_result_from_json(path) for path in sorted(root.glob("**/result.json"))]


def load_task_result(root: Path, task_id: str) -> TaskResult | None:
    for path in sorted(root.glob("**/result.json")):
        result = _task_result_from_json(path)
        if result.task_id == task_id:
            return result
    return None


def _task_result_from_json(path: Path) -> TaskResult:
    raw = RawE2EResult.model_validate_json(path.read_text(encoding="utf-8"))
    timing = raw.metadata.get("timing") if isinstance(raw.metadata.get("timing"), dict) else {}
    return TaskResult(
        task_id=raw.task_id or path.parent.name,
        environment_id=raw.environment_id,
        passed=raw.assertion_passed,
        skipped=raw.skipped,
        failure_category=raw.failure_category,
        message=raw.message,
        duration_s=raw.duration_s,
        avg_step_s=_optional_float(timing.get("avg_step_s")),
        artifact_dir=raw.artifact_dir or path.parent,
        command=raw.command,
    )


def build_platform_summary(platform: str, results: list[TaskResult]) -> PlatformSummary:
    passed = sum(1 for result in results if result.passed and not result.skipped)
    skipped = sum(1 for result in results if result.skipped)
    failed = sum(1 for result in results if not result.passed and not result.skipped)
    denominator = passed + failed
    pass_rate = round((passed / denominator) * 100.0, 1) if denominator else 0.0
    failure_categories: dict[str, int] = {}
    for result in results:
        if result.failure_category:
            failure_categories[result.failure_category] = failure_categories.get(result.failure_category, 0) + 1
    step_values = [result.avg_step_s for result in results if result.avg_step_s is not None]
    avg_step_s = round(sum(step_values) / len(step_values), 2) if step_values else None
    return PlatformSummary(
        platform=platform,
        results=results,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=len(results),
        pass_rate=pass_rate,
        failure_categories=dict(sorted(failure_categories.items())),
        avg_step_s=avg_step_s,
    )


def build_aggregate_summary(platforms: list[PlatformSummary]) -> AggregateSummary:
    merged_platforms = _merge_platform_summaries(platforms)
    passed = sum(platform.passed for platform in merged_platforms)
    failed = sum(platform.failed for platform in merged_platforms)
    skipped = sum(platform.skipped for platform in merged_platforms)
    total = sum(platform.total for platform in merged_platforms)
    denominator = passed + failed
    pass_rate = round((passed / denominator) * 100.0, 1) if denominator else 0.0
    step_values = [platform.avg_step_s for platform in merged_platforms if platform.avg_step_s is not None]
    avg_step_s = round(sum(step_values) / len(step_values), 2) if step_values else None
    return AggregateSummary(
        platforms=merged_platforms,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total,
        pass_rate=pass_rate,
        avg_step_s=avg_step_s,
    )


def _merge_platform_summaries(platforms: list[PlatformSummary]) -> list[PlatformSummary]:
    grouped: dict[str, list[TaskResult]] = {}
    for platform in platforms:
        grouped.setdefault(platform.platform, []).extend(platform.results)
    return [build_platform_summary(platform, grouped[platform]) for platform in sorted(grouped, key=_platform_sort_key)]


def _platform_sort_key(platform: str) -> tuple[int, str]:
    preferred = {"macOS": 0, "Windows": 1}
    return (preferred.get(platform, 99), platform)


def render_task_markdown(result: TaskResult) -> str:
    status = "PASS" if result.passed else "SKIP" if result.skipped else "FAIL"
    command = " ".join(result.command)
    lines = [
        f"## {status}: `{result.task_id}`",
        "",
        f"- Environment: `{result.environment_id}`",
        f"- Duration: `{_format_seconds(result.duration_s)}`",
        f"- Failure category: `{result.failure_category or 'n/a'}`",
        f"- avg_step_s: `{_format_seconds(result.avg_step_s)}`",
        f"- Message: {_escape_markdown_line(result.message)}",
    ]
    if command:
        lines.append(f"- Command: `{command}`")
    lines.append("")
    return "\n".join(lines)


def render_platform_markdown(summary: PlatformSummary) -> str:
    lines = [
        f"# Holo Full E2E: {summary.platform}",
        "",
        "| Platform | Passed | Failed | Skipped | Total | Pass rate | Avg step |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {summary.platform} | {summary.passed} | {summary.failed} | {summary.skipped} | "
            f"{summary.total} | {summary.pass_rate}% | {_format_duration_cell(summary.avg_step_s)} |"
        ),
        "",
    ]
    if summary.failure_categories:
        lines.extend(["## Failure Categories", ""])
        for category, count in summary.failure_categories.items():
            lines.append(f"- `{category}`: {count}")
        lines.append("")
    return "\n".join(lines)


def render_aggregate_markdown(summary: AggregateSummary) -> str:
    lines = [
        "# Holo Full E2E Summary",
        "",
        "| Platform | Passed | Failed | Skipped | Total | Pass rate | Avg step |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for platform in summary.platforms:
        lines.append(
            f"| {platform.platform} | {platform.passed} | {platform.failed} | {platform.skipped} | "
            f"{platform.total} | {platform.pass_rate}% | {_format_duration_cell(platform.avg_step_s)} |"
        )
    lines.append(
        f"| Overall | {summary.passed} | {summary.failed} | {summary.skipped} | "
        f"{summary.total} | {summary.pass_rate}% | {_format_duration_cell(summary.avg_step_s)} |"
    )
    lines.append("")
    return "\n".join(lines)


def write_platform_report(report_dir: Path, summary: PlatformSummary) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (report_dir / "summary.md").write_text(render_platform_markdown(summary), encoding="utf-8")
    with (report_dir / "task-results.jsonl").open("w", encoding="utf-8") as handle:
        for result in summary.results:
            handle.write(json.dumps(result.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")


def load_platform_summary(path: Path) -> PlatformSummary:
    return PlatformSummary.model_validate_json(path.read_text(encoding="utf-8"))


def write_aggregate_report(report_dir: Path, summary_paths: list[Path]) -> AggregateSummary:
    aggregate = build_aggregate_summary([load_platform_summary(path) for path in summary_paths])
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "aggregate-summary.json").write_text(
        json.dumps(aggregate.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown = render_aggregate_markdown(aggregate)
    (report_dir / "aggregate-summary.md").write_text(markdown, encoding="utf-8")
    append_to_step_summary(markdown)
    return aggregate


def append_task_summary(artifact_root: Path, task_id: str, *, platform: str | None = None) -> TaskResult:
    task_id = task_id.strip()
    result = load_task_result(artifact_root, task_id)
    if result is None:
        result = write_missing_task_result(artifact_root, task_id, platform=platform)
    append_to_step_summary(render_task_markdown(result))
    return result


def ensure_expected_task_results(
    artifact_root: Path,
    expected_task_ids: list[str],
    *,
    platform: str | None = None,
) -> list[TaskResult]:
    results = load_task_results(artifact_root)
    seen = {result.task_id for result in results}
    missing = [task_id for task_id in expected_task_ids if task_id not in seen]
    for task_id in missing:
        results.append(write_missing_task_result(artifact_root, task_id, platform=platform))
    return sorted(results, key=lambda result: result.task_id)


def write_missing_task_result(artifact_root: Path, task_id: str, *, platform: str | None = None) -> TaskResult:
    artifact_dir = artifact_root / f"missing__{task_id}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    environment_id = _environment_id_for_platform(platform)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "environment_id": environment_id,
        "execution": "foreground",
        "driver": "pyautogui",
        "command": [],
        "exit_code": None,
        "duration_s": None,
        "event_log_path": None,
        "copied_event_log_path": None,
        "assertion_passed": False,
        "skipped": False,
        "failure_category": "harness",
        "artifact_dir": str(artifact_dir),
        "message": f"pytest completed without writing result.json for task {task_id!r}",
        "metadata": {"synthetic": True},
    }
    path = artifact_dir / "result.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return _task_result_from_json(path)


def _environment_id_for_platform(platform: str | None) -> str:
    if platform == "macOS":
        return "macos-foreground"
    if platform == "Windows":
        return "windows-foreground"
    if platform == "Linux":
        return "linux-foreground"
    return "unknown"


def _read_expected_task_ids(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_to_step_summary(markdown: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(markdown.rstrip())
        handle.write("\n")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return str(round(value, 2))


def _format_duration_cell(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value, 2)}s"


def _escape_markdown_line(value: str) -> str:
    return value.replace("\n", " ").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path, nargs="?")
    parser.add_argument("--platform")
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--append-step-summary", action="store_true")
    parser.add_argument("--list-task-ids-for-platform", choices=["darwin", "win32", "linux"])
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-total", type=int)
    parser.add_argument("--append-task-summary", action="store_true")
    parser.add_argument("--task-id")
    parser.add_argument("--expected-task-ids-file", type=Path)
    parser.add_argument("--aggregate-summary-json", type=Path, action="append", default=[])
    parser.add_argument("--aggregate-report-dir", type=Path)
    args = parser.parse_args(argv)

    if args.list_task_ids_for_platform:
        if args.shard_index is None and args.shard_total is None:
            task_ids = task_ids_for_platform(args.list_task_ids_for_platform)
        elif args.shard_index is not None and args.shard_total is not None:
            task_ids = task_ids_for_shard(
                args.list_task_ids_for_platform,
                shard_index=args.shard_index,
                shard_total=args.shard_total,
            )
        else:
            parser.error("--shard-index and --shard-total must be supplied together")
        for task_id in task_ids:
            print(task_id)
        return 0

    if args.append_task_summary:
        if args.artifact_root is None:
            parser.error("artifact_root is required with --append-task-summary")
        if not args.task_id:
            parser.error("--task-id is required with --append-task-summary")
        result = append_task_summary(args.artifact_root, args.task_id, platform=args.platform)
        return 0 if result.passed else 1

    if args.aggregate_summary_json:
        if args.aggregate_report_dir is None:
            parser.error("--aggregate-report-dir is required with --aggregate-summary-json")
        aggregate = write_aggregate_report(args.aggregate_report_dir, args.aggregate_summary_json)
        return 1 if aggregate.failed else 0

    if args.artifact_root is None or not args.platform or args.report_dir is None:
        parser.error("artifact_root, --platform, and --report-dir are required unless using a helper mode")

    expected_task_ids = _read_expected_task_ids(args.expected_task_ids_file)
    results = (
        ensure_expected_task_results(args.artifact_root, expected_task_ids, platform=args.platform)
        if expected_task_ids is not None
        else load_task_results(args.artifact_root)
    )
    summary = build_platform_summary(args.platform, results)
    write_platform_report(args.report_dir, summary)
    if args.append_step_summary:
        append_to_step_summary(render_platform_markdown(summary))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
