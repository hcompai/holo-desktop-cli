from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

DEFAULT_ARTIFACT_BASE = Path("~/.holo/e2e-artifacts").expanduser()
DEFAULT_REVIEW_BUNDLE = Path("~/.holo/e2e-review").expanduser()
MAX_GIF_WIDTH = 960
GIF_FRAME_MS = 700
MAX_INLINE_ACTIONS_JSONL_CHARS = 12_000
SECRET_PATTERNS = (
    re.compile(r"(Authorization:\s*Bearer\s+)[^\s\"']+", re.IGNORECASE),
    re.compile(r"(\bBearer\s+)(hk-[A-Za-z0-9._~+/-]{20,})", re.IGNORECASE),
    re.compile(r"\bhk-[A-Za-z0-9._~+/-]{20,}\b"),
    re.compile(r"(HAI_API_KEY\s*[=:]\s*)[^\s\"']+", re.IGNORECASE),
)


@dataclass
class ActionRow:
    step: int
    tool_id: str | None
    tool_name: str
    args: dict[str, object]
    note: str | None = None
    thought: str | None = None
    result: str | None = None


@dataclass
class EventSmokeSummary:
    actions: list[ActionRow] = field(default_factory=list)
    final_answer: str | None = None
    screenshot_paths: list[Path] = field(default_factory=list)
    gif_path: Path | None = None
    gif_error: str | None = None


@dataclass
class TaskSmokeSummary:
    task_dir: Path
    task_id: str
    environment_id: str | None
    passed: bool
    message: str
    duration_s: float | None
    timing: dict[str, object]
    actions: list[ActionRow]
    final_answer: str | None
    gif_path: Path | None
    summary_path: Path


def find_latest_artifact_root(base: Path | None = None) -> Path:
    root = DEFAULT_ARTIFACT_BASE if base is None else base.expanduser()
    candidates = [path for path in root.glob("run-*") if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No e2e artifact roots found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def render_artifact_root(
    root: Path,
    *,
    github_step_summary: Path | None = None,
    review_bundle: Path | None = None,
) -> Path:
    summaries = [
        render_task_dir(path) for path in sorted(root.iterdir()) if path.is_dir() and (path / "result.json").exists()
    ]
    summary_path = root / "smoke-summary.md"
    summary_text = _render_root_markdown(summaries)
    summary_path.write_text(summary_text, encoding="utf-8")
    (root / "smoke-summary.json").write_text(
        json.dumps(_sanitize_json_value([_summary_json(summary) for summary in summaries]), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if review_bundle is not None:
        _write_review_bundle(summaries, root=root, output_dir=review_bundle.expanduser())
    if github_step_summary is not None:
        with github_step_summary.open("a", encoding="utf-8") as handle:
            handle.write(summary_text)
            handle.write("\n")
    return summary_path


def render_task_dir(task_dir: Path) -> TaskSmokeSummary:
    result = json.loads((task_dir / "result.json").read_text(encoding="utf-8"))
    event_summary = extract_event_summary(task_dir / "events.jsonl", output_dir=task_dir)
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    timing = metadata.get("timing") if isinstance(metadata.get("timing"), dict) else {}
    task_summary = TaskSmokeSummary(
        task_dir=task_dir,
        task_id=str(result.get("task_id") or task_dir.name),
        environment_id=result.get("environment_id") if isinstance(result.get("environment_id"), str) else None,
        passed=bool(result.get("assertion_passed")),
        message=str(result.get("message") or ""),
        duration_s=result.get("duration_s") if isinstance(result.get("duration_s"), (int, float)) else None,
        timing=timing,
        actions=event_summary.actions,
        final_answer=event_summary.final_answer,
        gif_path=event_summary.gif_path,
        summary_path=task_dir / "summary.md",
    )
    (task_dir / "actions.json").write_text(
        json.dumps(_sanitize_json_value([asdict(action) for action in task_summary.actions]), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (task_dir / "actions.jsonl").write_text(_actions_jsonl(task_summary.actions), encoding="utf-8")
    task_summary.summary_path.write_text(_render_task_markdown(task_summary), encoding="utf-8")
    return task_summary


def extract_event_summary(event_log: Path, *, output_dir: Path) -> EventSmokeSummary:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = output_dir / "observation-screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    summary = EventSmokeSummary()
    pending: dict[str, ActionRow] = {}
    observation_index = 0

    for record in _load_jsonl(event_log):
        event = record.get("event")
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        if kind == "observation_event":
            image_bytes = _extract_observation_image_bytes(event)
            if image_bytes is None:
                continue
            observation_index += 1
            path = screenshots_dir / f"step-{observation_index:04d}.png"
            path.write_bytes(image_bytes)
            summary.screenshot_paths.append(path)
        elif kind == "policy_event":
            note, thought = _policy_note_and_thought(event)
            reqs = event.get("tool_reqs")
            if not isinstance(reqs, list):
                continue
            for req in reqs:
                if not isinstance(req, dict):
                    continue
                args = req.get("args")
                row = ActionRow(
                    step=len(summary.actions) + 1,
                    tool_id=req.get("id") if isinstance(req.get("id"), str) else None,
                    tool_name=str(req.get("tool_name") or "tool"),
                    args=args if isinstance(args, dict) else {},
                    note=note,
                    thought=thought,
                )
                summary.actions.append(row)
                if row.tool_id:
                    pending[row.tool_id] = row
        elif kind == "tool_result_event":
            result_text = _short_text(event.get("result"))
            tool_req = event.get("tool_req")
            tool_id = tool_req.get("id") if isinstance(tool_req, dict) else None
            if isinstance(tool_id, str) and tool_id in pending:
                pending[tool_id].result = result_text
        elif kind == "answer_event":
            summary.final_answer = _short_text(event.get("answer"), limit=2000)

    summary.gif_path, summary.gif_error = _write_observation_gif(summary.screenshot_paths, output_dir)
    if summary.gif_error is not None:
        (output_dir / "observation-gif-error.txt").write_text(summary.gif_error + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="E2E artifact root. Defaults to newest ~/.holo/e2e-artifacts/run-*.",
    )
    parser.add_argument("--github-step-summary", type=Path, default=None)
    parser.add_argument(
        "--review-bundle",
        default=str(DEFAULT_REVIEW_BUNDLE),
        help="Flat directory to upload as the GitHub artifact. Pass an empty string to disable.",
    )
    args = parser.parse_args(argv)
    review_bundle = _review_bundle_path(args.review_bundle)

    try:
        root = args.root or find_latest_artifact_root()
    except FileNotFoundError as exc:
        if review_bundle is not None:
            _clear_review_bundle(review_bundle)
        message = f"# Holo Live Smoke\n\nNo e2e artifact root was created: {exc}\n"
        if args.github_step_summary is not None:
            with args.github_step_summary.open("a", encoding="utf-8") as handle:
                handle.write(message)
        else:
            print(message)
        return 0
    summary = render_artifact_root(root, github_step_summary=args.github_step_summary, review_bundle=review_bundle)
    print(summary)
    return 0


def _review_bundle_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    return Path(text).expanduser() if text else None


def _clear_review_bundle(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _extract_observation_image_bytes(event: dict[str, object]) -> bytes | None:
    observation = event.get("observation")
    if not isinstance(observation, dict):
        return None
    image = observation.get("image")
    if not isinstance(image, dict):
        return None
    candidates: list[object] = [image.get("source"), image.get("data"), image.get("base64")]
    source = image.get("source")
    if isinstance(source, dict):
        candidates.extend([source.get("data"), source.get("base64")])

    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        raw = candidate.split(",", 1)[1] if candidate.startswith("data:image/") and "," in candidate else candidate
        try:
            decoded = base64.b64decode(raw, validate=False)
        except ValueError:
            continue
        if decoded.startswith(b"\x89PNG") or decoded.startswith(b"\xff\xd8"):
            return decoded
    return None


def _policy_note_and_thought(event: dict[str, object]) -> tuple[str | None, str | None]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return None, None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content.strip(), None
    if not isinstance(parsed, dict):
        return content.strip(), None
    note = parsed.get("note")
    thought = parsed.get("thought")
    return (
        note.strip() if isinstance(note, str) and note.strip() else None,
        thought.strip() if isinstance(thought, str) and thought.strip() else None,
    )


def _write_observation_gif(screenshot_paths: list[Path], output_dir: Path) -> tuple[Path | None, str | None]:
    if not screenshot_paths:
        return None, "No observation screenshots were extractable from events.jsonl"
    frames: list[Image.Image] = []
    try:
        for path in screenshot_paths:
            image = Image.open(path).convert("RGB")
            if image.width > MAX_GIF_WIDTH:
                height = int(image.height * (MAX_GIF_WIDTH / image.width))
                image = image.resize((MAX_GIF_WIDTH, height))
            frames.append(image)
        gif_path = output_dir / "observation.gif"
        frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=GIF_FRAME_MS, loop=0)
        return gif_path, None
    except Exception as exc:
        return None, f"Failed to render observation.gif: {type(exc).__name__}: {exc}"


def _render_root_markdown(summaries: list[TaskSmokeSummary]) -> str:
    lines = ["# Holo Live Smoke", ""]
    if not summaries:
        lines.append("No task result directories found.")
        return _redact_text("\n".join(lines) + "\n")
    for summary in summaries:
        status = "PASS" if summary.passed else "FAIL"
        lines.extend(
            [
                f"## {status}: `{summary.task_id}`",
                "",
                f"- Environment: `{summary.environment_id or 'unknown'}`",
                f"- Duration: `{summary.duration_s}` seconds",
                f"- Message: {summary.message}",
                f"- Timed steps: `{summary.timing.get('steps_timed', 'n/a')}`",
                f"- avg_observe_s: `{summary.timing.get('avg_observe_s', 'n/a')}`",
                f"- avg_llm_s: `{summary.timing.get('avg_llm_s', 'n/a')}`",
                f"- avg_tool_s: `{summary.timing.get('avg_tool_s', 'n/a')}`",
                f"- avg_step_s: `{summary.timing.get('avg_step_s', 'n/a')}`",
                "",
                "### Visual review files",
                "",
                (
                    "GitHub job summaries do not render generated artifact images inline. "
                    "These files are attached to this job's artifact for visual review:"
                ),
                "",
                "- Before screenshot: `screen-before.png`",
                "- After screenshot: `screen-after.png`",
                f"- Observation GIF: `{summary.gif_path.name if summary.gif_path else 'not available'}`",
                "",
                "### Actions",
                "",
                _render_inline_actions_jsonl(summary.actions),
                "",
            ]
        )
        if summary.final_answer:
            lines.extend(["### Final answer", "", summary.final_answer, ""])
    return _redact_text("\n".join(lines) + "\n")


def _render_task_markdown(summary: TaskSmokeSummary) -> str:
    lines = [
        f"# {summary.task_id}",
        "",
        f"Result: {'PASS' if summary.passed else 'FAIL'}",
        "",
        f"Message: {summary.message}",
        "",
        "## Timing",
        "",
    ]
    for key in ("steps_timed", "avg_observe_s", "avg_llm_s", "avg_tool_s", "avg_step_s"):
        lines.append(f"- {key}: `{summary.timing.get(key, 'n/a')}`")
    lines.extend(["", "## Actions", ""])
    if not summary.actions:
        lines.append("No policy tool actions found.")
    for action in summary.actions:
        args = json.dumps(action.args, sort_keys=True)
        lines.append(f"- {action.step}. `{action.tool_name}` args=`{args}` result=`{action.result}`")
        if action.note:
            lines.append(f"  - note: {action.note}")
        if action.thought:
            lines.append(f"  - thought: {action.thought}")
    lines.extend(["", "## Final Answer", "", summary.final_answer or "No final answer event found.", ""])
    return _redact_text("\n".join(lines))


def _summary_json(summary: TaskSmokeSummary) -> dict[str, object]:
    return {
        "task_id": summary.task_id,
        "environment_id": summary.environment_id,
        "passed": summary.passed,
        "message": summary.message,
        "duration_s": summary.duration_s,
        "timing": summary.timing,
        "action_count": len(summary.actions),
        "gif_path": str(summary.gif_path) if summary.gif_path else None,
    }


def _write_review_bundle(summaries: list[TaskSmokeSummary], *, root: Path, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    _copy_if_exists(root / "smoke-summary.md", output_dir / "smoke-summary.md")
    _copy_if_exists(root / "smoke-summary.json", output_dir / "smoke-summary.json")

    single_task = len(summaries) == 1
    for summary in summaries:
        prefix = "" if single_task else f"{summary.task_id}--"
        for name in (
            "summary.md",
            "actions.jsonl",
            "actions.json",
            "events.jsonl",
            "observation.gif",
            "screen-before.png",
            "screen-after.png",
            "result.json",
            "stdout.txt",
            "stderr.txt",
            "platform.json",
        ):
            _copy_review_file(summary.task_dir / name, output_dir / f"{prefix}{name}")
        for runtime_log in sorted(summary.task_dir.glob("runtime*.log")):
            _copy_review_file(runtime_log, output_dir / f"{prefix}{runtime_log.name}")


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _copy_review_file(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
        destination.write_text(_redact_text(source.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        return
    shutil.copy2(source, destination)


def _render_inline_actions_jsonl(actions: list[ActionRow]) -> str:
    if not actions:
        return "No policy tool actions found."
    text = _actions_jsonl(actions)
    suffix = ""
    if len(text) > MAX_INLINE_ACTIONS_JSONL_CHARS:
        text = text[:MAX_INLINE_ACTIONS_JSONL_CHARS].rstrip()
        suffix = "\n... truncated; full `actions.jsonl` is attached in the job artifact."
    return "\n".join(
        [
            "<details>",
            "<summary><code>actions.jsonl</code></summary>",
            "",
            "```json",
            text + suffix,
            "```",
            "",
            "</details>",
        ]
    )


def _actions_jsonl(actions: list[ActionRow]) -> str:
    return "".join(
        json.dumps(_sanitize_json_value(asdict(action)), separators=(",", ":"), sort_keys=True) + "\n"
        for action in actions
    )


def _short_text(value: object, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    redacted = _redact_text(text)
    return redacted if len(redacted) <= limit else f"{redacted[: limit - 3]}..."


def _sanitize_json_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    return value


def _redact_text(text: str) -> str:
    redacted = text
    redacted = SECRET_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    for pattern in SECRET_PATTERNS[2:]:
        redacted = pattern.sub(r"\1[REDACTED]" if pattern.groups else "[REDACTED]", redacted)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
