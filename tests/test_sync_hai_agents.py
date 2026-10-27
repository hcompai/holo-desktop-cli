from __future__ import annotations

import importlib.util
import json
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sync_hai_agents", ROOT / "scripts" / "sync_hai_agents.py")
assert _spec is not None and _spec.loader is not None
sync_hai_agents = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_hai_agents)


def _release_files(tmp_path: Path) -> Path:
    for name in ("pyproject.toml", "CHANGELOG.md", "install/manifest.json"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def test_a_newer_sdk_stages_a_consistent_patch_release(tmp_path: Path) -> None:
    root = _release_files(tmp_path)
    before = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    major, minor, patch = before.split(".")

    new = sync_hai_agents.sync(root, "99.0.0", "9.9.9", "2026-10-16")

    assert new == f"{major}.{minor}.{int(patch) + 1}"
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    assert project["version"] == new
    assert "hai-agents[cli,workstation]>=99.0.0" in project["dependencies"]
    assert json.loads((root / "install" / "manifest.json").read_text())["holo_version"] == new
    notes = (root / "CHANGELOG.md").read_text()
    assert f"## [{new}] - 2026-10-16\n\n- Requires `hai-agents` 99.0.0+ (`hai-agent-runtime` 9.9.9).\n" in notes
    assert notes.index(f"## [{new}]") < notes.index(f"## [{before}]")


def test_an_already_synced_sdk_changes_nothing(tmp_path: Path) -> None:
    root = _release_files(tmp_path)
    floor = sync_hai_agents.FLOOR.search((root / "pyproject.toml").read_text()).group(1)
    snapshot = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    assert sync_hai_agents.sync(root, floor, None, "2026-10-16") is None
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == snapshot
