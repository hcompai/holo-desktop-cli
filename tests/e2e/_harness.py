from __future__ import annotations

from holo_desktop.agent_client.event_timings import StepTimingsSummary, extract_step_timings

from ._artifacts import E2EArtifacts, E2EResult
from ._domain import FailureCategory, FlatMetadata, PreparedTask
from ._runner import HoloRunResult, find_latest_event_log, run_holo_foreground
from .conftest import HoloLiveConfig


def _flatten_timing(timing: StepTimingsSummary | dict[str, object]) -> dict[str, object]:
    """Keep only the scalar timing summary for the flat result metadata.

    ``extract_step_timings`` includes a per-step ``steps`` list of dicts, which
    is not a valid :data:`~._domain.FlatMetadata` leaf and fails ``E2EResult``
    validation. The scalar summary (``steps_timed``, ``avg_*``) is retained here;
    per-step detail already lives in ``events.jsonl`` and the rendered table.
    """
    payload = timing.model_dump(mode="json") if isinstance(timing, StepTimingsSummary) else timing
    return {key: value for key, value in payload.items() if key != "steps"}


def run_and_evaluate(
    *,
    prepared: PreparedTask,
    artifacts: E2EArtifacts,
    config: HoloLiveConfig,
    environment_id: str,
) -> None:
    artifacts.capture_screenshot(before=True)
    run_result: HoloRunResult | None = None
    passed = False
    failure_category: FailureCategory | None = None
    message = ""
    evaluation_metadata: FlatMetadata = {}
    try:
        run_result = run_holo_foreground(
            task=prepared.instruction,
            runs_dir=artifacts.runs_dir,
            config=config,
            max_steps=16,
            max_time_s=config.timeout_s,
        )
        artifacts.write_streams(stdout=run_result.stdout, stderr=run_result.stderr)
        if run_result.exit_code != 0:
            failure_category = FailureCategory.HOLO_COMMAND
            message = f"`holo run` exited with {run_result.exit_code}"
            raise AssertionError(message)
        run_event_log = run_result.event_log_path or find_latest_event_log(artifacts.runs_dir)
        run_timing = extract_step_timings(run_event_log)
        # extract_step_timings returns None when the log holds no timed steps; only a missing log is inconclusive.
        if run_event_log is not None and (run_timing is None or _flatten_timing(run_timing).get("steps_timed") == 0):
            failure_category = FailureCategory.HOLO_COMMAND
            message = "`holo run` produced zero timed agent steps"
            raise AssertionError(message)

        evaluation = prepared.evaluate()
        passed = evaluation.passed
        failure_category = evaluation.failure_category
        message = evaluation.message
        evaluation_metadata = evaluation.metadata
        assert evaluation.passed, evaluation.message
    finally:
        artifacts.capture_screenshot(before=False)
        artifacts.preserve_final_artifacts(prepared)
        event_log_path = run_result.event_log_path if run_result else None
        copied_event_log = artifacts.copy_event_log(event_log_path)
        if copied_event_log is None:
            copied_event_log = artifacts.copy_event_log(find_latest_event_log(artifacts.runs_dir))
        copied_runtime_log = artifacts.copy_runtime_log(run_result.runtime_log_path if run_result else None)
        timing = extract_step_timings(copied_event_log)
        artifacts.write_result(
            E2EResult(
                task_id=prepared.case.id,
                environment_id=environment_id,
                execution="foreground",
                driver="pyautogui",
                command=run_result.command if run_result else [],
                exit_code=run_result.exit_code if run_result else None,
                duration_s=run_result.duration_s if run_result else None,
                event_log_path=run_result.event_log_path if run_result else None,
                copied_event_log_path=copied_event_log,
                runtime_log_path=run_result.runtime_log_path if run_result else None,
                copied_runtime_log_path=copied_runtime_log,
                assertion_passed=passed,
                failure_category=failure_category.value if failure_category else None,
                artifact_dir=artifacts.root,
                message=message,
                metadata={
                    **prepared.metadata,
                    "case_intent": prepared.case.intent,
                    "app_family": prepared.case.app_family,
                    "evaluator": prepared.evaluator.name,
                    "evaluation": evaluation_metadata,
                    **({"timing": _flatten_timing(timing)} if timing else {}),
                },
            )
        )
