from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ._domain import Metadata, PreparedTask


class E2EResult(BaseModel):
    """Machine-readable summary of one live e2e task attempt."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    environment_id: str
    execution: str
    driver: str
    command: list[str] = Field(default_factory=list)
    exit_code: int | None
    duration_s: float | None
    event_log_path: Path | None
    copied_event_log_path: Path | None
    assertion_passed: bool
    failure_category: str | None
    artifact_dir: Path
    message: str
    metadata: Metadata = Field(default_factory=dict)


@dataclass(frozen=True)
class E2EArtifacts:
    """Filesystem locations for one live e2e test's artifacts."""

    root: Path
    runs_dir: Path
    stdout_path: Path
    stderr_path: Path
    result_path: Path
    platform_path: Path
    before_screenshot_path: Path
    after_screenshot_path: Path
    events_path: Path
    final_dir: Path

    @classmethod
    def create(cls, root: Path) -> E2EArtifacts:
        root.mkdir(parents=True, exist_ok=True)
        runs_dir = root / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        artifacts = cls(
            root=root,
            runs_dir=runs_dir,
            stdout_path=root / "stdout.txt",
            stderr_path=root / "stderr.txt",
            result_path=root / "result.json",
            platform_path=root / "platform.json",
            before_screenshot_path=root / "screen-before.png",
            after_screenshot_path=root / "screen-after.png",
            events_path=root / "events.jsonl",
            final_dir=root / "final",
        )
        artifacts.write_platform_metadata()
        return artifacts

    def write_platform_metadata(self) -> None:
        self.platform_path.write_text(
            json.dumps(
                {
                    "platform": platform.platform(),
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "python": platform.python_version(),
                    "git": _git_metadata(),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def capture_screenshot(self, *, before: bool) -> None:
        path = self.before_screenshot_path if before else self.after_screenshot_path
        try:
            import pyautogui

            image = pyautogui.screenshot()
            image.save(path)
        except Exception as exc:
            path.with_suffix(".error.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")

    def write_streams(self, *, stdout: str, stderr: str) -> None:
        self.stdout_path.write_text(stdout, encoding="utf-8")
        self.stderr_path.write_text(stderr, encoding="utf-8")

    def copy_event_log(self, event_log_path: Path | None) -> Path | None:
        if event_log_path is None or not event_log_path.exists():
            return None
        shutil.copy2(event_log_path, self.events_path)
        return self.events_path

    def preserve_final_artifacts(self, prepared_task: PreparedTask) -> None:
        self.final_dir.mkdir(parents=True, exist_ok=True)
        try:
            prepared_task.preserve_final_artifacts(self.final_dir)
        except Exception as exc:
            error_path = self.final_dir / "preserve-error.txt"
            error_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")

    def write_result(self, result: E2EResult) -> None:
        self.result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")


def _git_metadata() -> dict[str, str | None]:
    return {
        "branch": _git(["branch", "--show-current"]),
        "commit": _git(["rev-parse", "HEAD"]),
    }


def _git(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(["git", *args], check=False, capture_output=True, text=True)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None
