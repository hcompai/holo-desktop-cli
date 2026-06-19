from __future__ import annotations

from pathlib import Path

import pytest

from ._artifacts import E2EArtifacts
from ._domain import EnvironmentRunner, PreparedTask, TaskCase
from ._harness import run_and_evaluate
from .conftest import HoloLiveConfig
from .environments.macos import MACOS_FOREGROUND_TASKS


@pytest.mark.holo_live_foreground
@pytest.mark.parametrize("task_case", MACOS_FOREGROUND_TASKS, ids=lambda task_case: task_case.id)
def test_foreground_task(
    task_case: TaskCase,
    holo_live_preflight: None,
    holo_live_config: HoloLiveConfig,
    holo_e2e_artifacts: E2EArtifacts,
    environment_runner: EnvironmentRunner,
    tmp_path: Path,
) -> None:
    if not environment_runner.supports(task_case):
        pytest.skip(f"{environment_runner.environment_id} does not support {task_case.id}")

    prepared: PreparedTask | None = None
    try:
        environment_runner.preflight(task_case)
        prepared = environment_runner.prepare(task_case, tmp_path)
        run_and_evaluate(
            prepared=prepared,
            artifacts=holo_e2e_artifacts,
            config=holo_live_config,
            environment_id=environment_runner.environment_id,
        )
    finally:
        environment_runner.cleanup(prepared)
