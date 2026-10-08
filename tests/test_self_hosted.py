"""Self-hosted target: read after the env files load, and a server without a model fails fast."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from holo_desktop.cli import bootstrap
from holo_desktop.task import Outcome

run_mod = importlib.import_module("holo_desktop.cli.run")
mcp_mod = importlib.import_module("holo_desktop.cli.mcp")


@pytest.fixture(autouse=True)
def _offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bootstrap, "seed_bundled_skills", lambda: None)
    monkeypatch.setattr(mcp_mod.mcp_app, "run", lambda: None)


def test_self_hosted_server_in_holo_env_needs_no_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap.LEGACY_ENV_PATH.parent.mkdir(parents=True)
    bootstrap.LEGACY_ENV_PATH.write_text(
        "HAI_AGENT_RUNTIME_BASE_URL=http://localhost:8000/v1\nHAI_AGENT_RUNTIME_MODEL=holo3\n"
    )
    seen: dict[str, Any] = {}

    async def drive(task: str, **kwargs: Any) -> Outcome:
        seen.update(kwargs)
        return Outcome(status="completed", answer="ok", error=None)

    monkeypatch.setattr(run_mod, "_drive", drive)

    run_mod.run("task", no_kill_switch=True)

    assert (seen["base_url"], seen["model"]) == ("http://localhost:8000/v1", "holo3")


@pytest.mark.parametrize("command", ["run", "mcp"])
def test_self_hosted_server_without_model_points_at_model(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://localhost:8000/v1")

    with pytest.raises(SystemExit) as exc:
        if command == "run":
            run_mod.run("task", no_kill_switch=True)
        else:
            mcp_mod.mcp()

    assert exc.value.code == 1
    assert "--model" in capsys.readouterr().err
