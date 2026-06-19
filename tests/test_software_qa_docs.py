"""Repository hygiene checks for the Claude Code QA example docs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE_QA = ROOT / "examples/software_qa"


def test_nimbus_docs_route_qa_through_root_holo_mcp() -> None:
    docs = "\n".join(
        [
            (SOFTWARE_QA / "CLAUDE.md").read_text(encoding="utf-8"),
            (SOFTWARE_QA / "AGENTS.md").read_text(encoding="utf-8"),
            (SOFTWARE_QA / "README.md").read_text(encoding="utf-8"),
        ]
    )

    assert "holo_desktop" in docs
    assert "holo-qa" in docs
    assert "holo install claude-code" in docs
    assert ".mcp.json" not in docs
    assert "qa_launch" not in docs
    assert "holo-qa MCP" not in docs


def test_nimbus_ships_a_local_qa_skill_for_root_mcp() -> None:
    skill = (SOFTWARE_QA / ".claude/skills/holo-qa/SKILL.md").read_text(encoding="utf-8")

    assert "holo_desktop(task)" in skill
    assert "qa/*.md" in skill
    assert "VERDICT: PASSED" in skill
    assert "VERDICT: FAILED" in skill
    assert ".mcp.json" not in skill
    assert "qa_launch" not in skill
    assert "npm run qa:holo" not in skill


def test_nimbus_project_does_not_ship_workspace_mcp_config() -> None:
    assert not (SOFTWARE_QA / ".mcp.json").exists()


def test_software_qa_does_not_ship_a_private_runner() -> None:
    stale_paths = [
        SOFTWARE_QA / "mcp.py",
        SOFTWARE_QA / "cli.py",
        SOFTWARE_QA / "runner.py",
        SOFTWARE_QA / "prompt.py",
        SOFTWARE_QA / "spec.py",
        SOFTWARE_QA / "pyproject.toml",
        SOFTWARE_QA / "__init__.py",
        SOFTWARE_QA / "scripts/install-claude-desktop-mcp.py",
        SOFTWARE_QA / "scripts/launch-holo-qa-mcp.sh",
    ]

    assert [path for path in stale_paths if path.exists()] == []


def test_nimbus_package_scripts_do_not_bypass_root_mcp() -> None:
    package_json = (SOFTWARE_QA / "package.json").read_text(encoding="utf-8")

    assert "qa:holo" not in package_json
    assert "qa:list" not in package_json
    assert "examples.software_qa" not in package_json
