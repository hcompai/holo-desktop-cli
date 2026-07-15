import json
from pathlib import Path

from PIL import Image

from tests.e2e import _smoke_report
from tests.e2e._smoke_report import render_artifact_root

PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _write_task_artifacts(root: Path) -> Path:
    task_dir = root / "tests__e2e__test_live_foreground.py__test_foreground_task_calculator_ci_smoke_"
    task_dir.mkdir(parents=True)
    (task_dir / "stdout.txt").write_text("answer\n", encoding="utf-8")
    (task_dir / "stderr.txt").write_text("profile table\n", encoding="utf-8")
    Image.new("RGB", (1, 1), color=(80, 160, 240)).save(task_dir / "screen-before.png")
    Image.new("RGB", (1, 1), color=(80, 160, 240)).save(task_dir / "screen-after.png")
    (task_dir / "result.json").write_text(
        json.dumps(
            {
                "task_id": "calculator_ci_smoke",
                "environment_id": "macos-foreground",
                "execution": "foreground",
                "driver": "pyautogui",
                "command": ["uv", "run", "holo", "run", "task", "--profile"],
                "exit_code": 0,
                "duration_s": 12.5,
                "event_log_path": None,
                "copied_event_log_path": str(task_dir / "events.jsonl"),
                "assertion_passed": True,
                "failure_category": None,
                "artifact_dir": str(task_dir),
                "message": "Calculator result matched",
                "metadata": {
                    "a": 2,
                    "b": 2,
                    "expected": 4,
                    "evaluation": {"display": "4", "result_part": "4"},
                    "timing": {
                        "steps_timed": 2,
                        "avg_observe_s": 0.2,
                        "avg_llm_s": 1.5,
                        "avg_tool_s": 0.3,
                        "avg_step_s": 2.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        task_dir / "events.jsonl",
        [
            {
                "ts": "2026-06-16T10:00:00Z",
                "event": {
                    "kind": "observation_event",
                    "observation": {
                        "image": {"type": "base64", "media_type": "image/png", "source": PNG_1X1},
                        "cursor_position": [1, 2],
                        "viewport_size": [100, 100],
                    },
                },
            },
            {
                "ts": "2026-06-16T10:00:01Z",
                "event": {
                    "kind": "policy_event",
                    "message": {"content": '{"note": "Click 2", "thought": "Need first operand"}'},
                    "tool_reqs": [{"id": "tool-1", "tool_name": "click_desktop", "args": {"x": 10, "y": 20}}],
                },
            },
            {
                "ts": "2026-06-16T10:00:02Z",
                "event": {
                    "kind": "tool_result_event",
                    "tool_req": {"id": "tool-1", "tool_name": "click_desktop"},
                    "result": "ok",
                },
            },
            {
                "ts": "2026-06-16T10:00:03Z",
                "event": {"kind": "answer_event", "answer": "2+2 is 4"},
            },
        ],
    )
    return task_dir


def test_render_artifact_root_writes_summary_actions_images_and_gif(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    _write_task_artifacts(root)

    summary_path = render_artifact_root(root)

    assert summary_path == root / "smoke-summary.md"
    text = summary_path.read_text(encoding="utf-8")
    assert "calculator_ci_smoke" in text
    assert "Calculator result matched" in text
    assert "avg_step_s" in text

    task_dir = next(path for path in root.iterdir() if path.is_dir())
    assert (task_dir / "summary.md").exists()
    assert (task_dir / "actions.json").exists()
    assert (task_dir / "observation-screenshots" / "step-0001.png").exists()
    assert (task_dir / "observation.gif").exists()

    with Image.open(task_dir / "observation.gif") as image:
        assert image.n_frames == 1

    actions = json.loads((task_dir / "actions.json").read_text(encoding="utf-8"))
    assert actions[0]["tool_name"] == "click_desktop"
    assert actions[0]["result"] == "ok"
    assert actions[0]["note"] == "Click 2"


def test_render_artifact_root_records_missing_observation_images(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    task_dir = _write_task_artifacts(root)
    _write_jsonl(
        task_dir / "events.jsonl",
        [{"ts": "2026-06-16T10:00:00Z", "event": {"kind": "answer_event", "answer": "done"}}],
    )

    render_artifact_root(root)

    error_path = task_dir / "observation-gif-error.txt"
    assert error_path.exists()
    assert "No observation screenshots" in error_path.read_text(encoding="utf-8")
    assert (task_dir / "summary.md").exists()


def test_render_artifact_root_appends_to_github_step_summary(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    github_summary = tmp_path / "github-summary.md"
    _write_task_artifacts(root)

    render_artifact_root(root, github_step_summary=github_summary)

    text = github_summary.read_text(encoding="utf-8")
    assert "# Holo Live Smoke" in text
    assert "calculator_ci_smoke" in text


def test_github_step_summary_embeds_reviewable_actions_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    github_summary = tmp_path / "github-summary.md"
    task_dir = _write_task_artifacts(root)

    render_artifact_root(root, github_step_summary=github_summary)

    text = github_summary.read_text(encoding="utf-8")
    assert "<summary><code>actions.jsonl</code></summary>" in text
    assert '"tool_name":"click_desktop"' in text
    assert '"note":"Click 2"' in text
    assert (task_dir / "actions.jsonl").exists()
    assert '"tool_name":"click_desktop"' in (task_dir / "actions.jsonl").read_text(encoding="utf-8")


def test_github_step_summary_names_visual_artifacts_without_claiming_inline_images(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    github_summary = tmp_path / "github-summary.md"
    _write_task_artifacts(root)

    render_artifact_root(root, github_step_summary=github_summary)

    text = github_summary.read_text(encoding="utf-8")
    assert "Visual review files" in text
    assert "`screen-before.png`" in text
    assert "`screen-after.png`" in text
    assert "`observation.gif`" in text
    assert "GitHub job summaries do not render generated artifact images inline" in text


def test_render_artifact_root_writes_flat_review_bundle(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    review_bundle = tmp_path / "review-bundle"
    task_dir = _write_task_artifacts(root)
    (task_dir / "runtime.log").write_text("first attempt\n", encoding="utf-8")
    (task_dir / "runtime-attempt-2.log").write_text("second attempt\n", encoding="utf-8")

    render_artifact_root(root, review_bundle=review_bundle)

    names = {path.name for path in review_bundle.iterdir() if path.is_file()}
    assert {
        "smoke-summary.md",
        "smoke-summary.json",
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
        "runtime.log",
        "runtime-attempt-2.log",
    } <= names


def test_main_empty_review_bundle_flag_disables_bundle_output(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "run-20260616-100000"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_task_artifacts(root)
    monkeypatch.chdir(cwd)

    exit_code = _smoke_report.main(["--root", str(root), "--review-bundle", ""])

    assert exit_code == 0
    assert not (cwd / "smoke-summary.md").exists()
    assert not (cwd / "summary.md").exists()


def test_review_bundle_redacts_secret_shaped_text(tmp_path: Path) -> None:
    root = tmp_path / "run-20260616-100000"
    review_bundle = tmp_path / "review-bundle"
    task_dir = _write_task_artifacts(root)
    secret = "hk-0123456789abcdef0123456789abcdef"
    (task_dir / "stdout.txt").write_text(f"Authorization: Bearer {secret}\n", encoding="utf-8")
    (task_dir / "stderr.txt").write_text(f"HAI_API_KEY={secret}\n", encoding="utf-8")
    result = json.loads((task_dir / "result.json").read_text(encoding="utf-8"))
    result["message"] = f"leaked {secret}"
    (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    _write_jsonl(
        task_dir / "events.jsonl",
        [
            {
                "ts": "2026-06-16T10:00:00Z",
                "event": {
                    "kind": "policy_event",
                    "message": {"content": '{"note": "use Bearer hk-0123456789abcdef0123456789abcdef"}'},
                    "tool_reqs": [{"id": "tool-1", "tool_name": "click_desktop", "args": {"token": secret}}],
                },
            },
            {"ts": "2026-06-16T10:00:01Z", "event": {"kind": "answer_event", "answer": f"done {secret}"}},
        ],
    )

    render_artifact_root(root, review_bundle=review_bundle)

    for path in review_bundle.iterdir():
        if path.suffix not in {".json", ".jsonl", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert secret not in text
        assert "Authorization: Bearer hk-" not in text
    assert "[REDACTED]" in (review_bundle / "stdout.txt").read_text(encoding="utf-8")
    assert "[REDACTED]" in (review_bundle / "summary.md").read_text(encoding="utf-8")


def test_short_text_truncates_to_limit() -> None:
    text = _smoke_report._short_text("a" * 20, limit=10)

    assert text == "aaaaaaa..."
    assert len(text) == 10


def test_main_reports_missing_artifact_root_without_error(tmp_path: Path, monkeypatch) -> None:
    github_summary = tmp_path / "github-summary.md"
    monkeypatch.setattr(_smoke_report, "DEFAULT_ARTIFACT_BASE", tmp_path / "missing")

    exit_code = _smoke_report.main(["--github-step-summary", str(github_summary)])

    assert exit_code == 0
    text = github_summary.read_text(encoding="utf-8")
    assert "No e2e artifact root was created" in text


def test_main_clears_stale_review_bundle_when_artifact_root_missing(tmp_path: Path, monkeypatch) -> None:
    github_summary = tmp_path / "github-summary.md"
    review_bundle = tmp_path / "review-bundle"
    review_bundle.mkdir()
    (review_bundle / "stale.txt").write_text("old run", encoding="utf-8")
    monkeypatch.setattr(_smoke_report, "DEFAULT_ARTIFACT_BASE", tmp_path / "missing")

    exit_code = _smoke_report.main(
        [
            "--github-step-summary",
            str(github_summary),
            "--review-bundle",
            str(review_bundle),
        ]
    )

    assert exit_code == 0
    assert not review_bundle.exists()
