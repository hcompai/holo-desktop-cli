from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from holo_desktop.settings import load_holo_settings

from ._artifacts import E2EArtifacts
from ._domain import EnvironmentRunner
from ._environment import UnsupportedEnvironmentError, current_environment_runner


@dataclass(frozen=True)
class HoloLiveConfig:
    """Pytest options used by live foreground Holo runs."""

    enabled: bool
    timeout_s: float
    model: str | None
    base_url: str | None
    task_ids: list[str]
    quiet: bool = False
    fast: bool = False


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-holo-live-foreground",
        action="store_true",
        default=False,
        help="Run foreground HoloDesktop CLI live tests. These move cursor/focus and require a real desktop.",
    )
    parser.addoption(
        "--holo-live-timeout",
        type=float,
        default=180.0,
        help="Timeout in seconds for each live `holo run` subprocess.",
    )
    parser.addoption(
        "--holo-model",
        action="store",
        default=None,
        help="Optional model override passed to `holo run --model`.",
    )
    parser.addoption(
        "--holo-base-url",
        action="store",
        default=None,
        help="Optional OpenAI-compatible base URL passed to `holo run --base-url`.",
    )
    parser.addoption(
        "--holo-live-task-ids",
        action="store",
        default="",
        metavar="TASK_ID",
        help=(
            "Comma-separated live e2e task id slugs to run, "
            "for example `--holo-live-task-ids textedit_type_sentinel,finder_create_folder`."
        ),
    )
    parser.addoption(
        "--holo-live-quiet",
        action="store_true",
        default=False,
        help=(
            "Pass --quiet to `holo run`, suppressing the agent's live step narration. "
            "Narration is on by default; combine with pytest --capture=tee-sys to watch it stream."
        ),
    )
    parser.addoption(
        "--holo-fast",
        action="store_true",
        default=False,
        help="Pass --fast to `holo run`: opt-in fast mode (one screenshot, no thinking, smaller uploads).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "holo_live_foreground: opt-in live foreground desktop test")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    selected_task_ids = _selected_task_ids(config)
    if config.getoption("--run-holo-live-foreground"):
        if selected_task_ids:
            selected: list[pytest.Item] = []
            deselected: list[pytest.Item] = []
            for item in items:
                if "holo_live_foreground" in item.keywords and _live_task_id(item) not in selected_task_ids:
                    deselected.append(item)
                else:
                    selected.append(item)
            if deselected:
                config.hook.pytest_deselected(items=deselected)
                items[:] = selected
        return
    skip = pytest.mark.skip(reason="requires --run-holo-live-foreground; moves cursor/focus on the real desktop")
    for item in items:
        if "holo_live_foreground" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def holo_live_config(pytestconfig: pytest.Config) -> HoloLiveConfig:
    return HoloLiveConfig(
        enabled=bool(pytestconfig.getoption("--run-holo-live-foreground")),
        timeout_s=float(pytestconfig.getoption("--holo-live-timeout")),
        model=pytestconfig.getoption("--holo-model"),
        base_url=pytestconfig.getoption("--holo-base-url"),
        task_ids=_selected_task_ids(pytestconfig),
        quiet=bool(pytestconfig.getoption("--holo-live-quiet")),
        fast=bool(pytestconfig.getoption("--holo-fast")),
    )


@pytest.fixture(scope="session")
def holo_live_preflight(holo_live_config: HoloLiveConfig) -> None:
    if not holo_live_config.enabled:
        pytest.skip("requires --run-holo-live-foreground")
    if not (holo_live_config.base_url or _holo_api_key_present()):
        pytest.skip("HAI_API_KEY missing from shell env and ~/.holo/.env; run `uv run holo login` first")


@pytest.fixture(scope="session")
def environment_runner() -> EnvironmentRunner:
    try:
        return current_environment_runner()
    except UnsupportedEnvironmentError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def holo_e2e_artifact_root() -> Path:
    override = load_holo_settings().test.artifact_root
    if override is not None:
        override.mkdir(parents=True, exist_ok=True)
        return override
    stamp = datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
    root = Path.home() / ".holo" / "e2e-artifacts" / stamp
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def holo_e2e_artifacts(request: pytest.FixtureRequest, holo_e2e_artifact_root: Path) -> E2EArtifacts:
    test_id = request.node.nodeid.replace("/", "__").replace("::", "__").replace("[", "_").replace("]", "_")
    return E2EArtifacts.create(holo_e2e_artifact_root / test_id)


def _holo_api_key_present() -> bool:
    if os.environ.get("HAI_API_KEY"):
        return True
    env_path = Path.home() / ".holo" / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("HAI_API_KEY=") and stripped.split("=", 1)[1].strip():
            return True
    return False


def _selected_task_ids(config: pytest.Config) -> list[str]:
    raw_value = config.getoption("--holo-live-task-ids") or ""
    return [task_id.strip() for task_id in str(raw_value).split(",") if task_id.strip()]


def _live_task_id(item: pytest.Item) -> str | None:
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return None
    task_case = callspec.params.get("task_case")
    return getattr(task_case, "id", None)
