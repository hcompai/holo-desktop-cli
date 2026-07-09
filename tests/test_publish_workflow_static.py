from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_publish_workflow_uploads_installer_assets_after_release() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["publish-installer-cdn"]

    assert job["needs"] == "release"
    assert job["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert job["permissions"]["id-token"] == "write"
    assert job["permissions"]["contents"] == "read"

    rendered = yaml.safe_dump(job, sort_keys=True)
    assert "arn:aws:iam::676206947389:role/HoloDesktopCliInstallerReleaseRole" in rendered
    assert "hcompany-holo-desktop-installer-assets" in rendered
    assert "s3://${INSTALLER_ASSETS_BUCKET}/install.sh" in rendered
    assert "s3://${INSTALLER_ASSETS_BUCKET}/install.ps1" in rendered
    assert "s3://${INSTALLER_ASSETS_BUCKET}/install/manifest.json" in rendered
    assert "https://install.hcompany.ai" in rendered
    assert "--cache-control" in rendered
    assert "--content-type text/x-shellscript" in rendered
    assert "--content-type application/json" in rendered


def test_release_job_checks_out_installer_assets_before_github_release() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["release"]["steps"]

    assert steps[0]["uses"] == "actions/checkout@v4"
    release_step = steps[-1]
    assert release_step["uses"] == "softprops/action-gh-release@v2"
    assert "install/install.sh" in release_step["with"]["files"]
    assert "install/install.ps1" in release_step["with"]["files"]
    assert "install/manifest.json" in release_step["with"]["files"]
