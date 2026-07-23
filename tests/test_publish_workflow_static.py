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
    assert "windows-arm64-dependency" in rendered
    assert "put-object" in rendered
    assert "Metadata.sha256" in rendered
    assert "https://install.hcompany.ai" in rendered
    assert "--cache-control" in rendered
    assert "--content-type text/x-shellscript" in rendered
    assert "--content-type application/json" in rendered
    upload_step = next(step for step in job["steps"] if step.get("name") == "Upload installer assets")
    assert "--if-none-match '*'" in upload_step["run"]
    assert "max-age=31536000, immutable" in upload_step["run"]
    smoke_step = next(step for step in job["steps"] if step.get("name") == "Smoke Linux installer from CDN")
    assert 'curl -fsSL "${INSTALLER_BASE_URL}/install.sh" | bash' in smoke_step["run"]
    assert '"$HOLO_HOME/bin/holo" --help' in smoke_step["run"]


def test_release_job_checks_out_installer_assets_before_github_release() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["release"]["steps"]

    assert steps[0]["uses"] == "actions/checkout@v4"
    release_step = steps[-1]
    assert release_step["uses"] == "softprops/action-gh-release@v2"
    assert "release-assets/wheels/*.whl" in release_step["with"]["files"]
    assert "install/install.sh" in release_step["with"]["files"]
    assert "install/install.ps1" in release_step["with"]["files"]
    assert "release-assets/install/manifest.json" in release_step["with"]["files"]


def test_release_builds_and_materializes_the_windows_arm64_dependency() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    wheel = workflow["jobs"]["windows-arm64-dependency"]
    release = workflow["jobs"]["release"]

    assert wheel["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert wheel["runs-on"] == "windows-11-arm"
    rendered = yaml.safe_dump(wheel, sort_keys=True)
    assert "build_windows_arm64_dependency_wheel.ps1" in rendered
    assert "manifest_path" in rendered
    assert "wheel_path" in rendered
    assert "BUILD_AT_RELEASE" in rendered
    assert "windows-arm64-dependency" in rendered
    assert workflow["jobs"]["publish-pypi"]["needs"] == ["build", "windows-arm64-dependency"]
    assert release["needs"] == ["publish-pypi", "windows-arm64-dependency"]

    build_script = (ROOT / "scripts/build_windows_arm64_dependency_wheel.ps1").read_text(encoding="utf-8")
    assert '"cpython-$PythonVersion-windows-aarch64-none"' in build_script
    assert '-Filter "$DependencyName-*-win_arm64.whl"' in build_script


def test_client_release_refuses_placeholder_runtime_and_smokes_windows_arm64() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    build_steps = workflow["jobs"]["build"]["steps"]
    gate = next(
        step for step in build_steps if step.get("name") == "assert every managed runtime artifact is published"
    )
    assert gate["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert "'=0{64}$' shas/*.txt" in gate["run"]

    smoke = workflow["jobs"]["smoke-windows-arm64-installer-cdn"]
    assert smoke["needs"] == "publish-installer-cdn"
    assert smoke["runs-on"] == "windows-11-arm"
    rendered = yaml.safe_dump(smoke, sort_keys=True)
    assert "https://install.hcompany.ai" in rendered
    assert "install.ps1" in rendered
    assert "holo.exe" in rendered
    smoke_step = next(step for step in smoke["steps"] if step.get("name") == "Smoke Windows ARM64 installer from CDN")
    assert smoke_step["env"]["UV_NO_BUILD"] == "1"


def test_windows_arm64_installer_and_full_e2e_scaffolding() -> None:
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    installer = ci["jobs"]["windows-arm64-installer"]
    assert installer["runs-on"] == "windows-11-arm"
    rendered_installer = yaml.safe_dump(installer, sort_keys=True)
    assert "install.ps1" in rendered_installer
    assert "windows-arm64.txt" in rendered_installer
    assert "HOLO_INSTALL_SKIP_RUN_SETUP" in rendered_installer
    assert "build_windows_arm64_dependency_wheel.ps1" in rendered_installer
    assert "UV_NO_BUILD" in rendered_installer
    assert "steps.dependency.outputs.manifest_path" in rendered_installer
    assert "steps.client.outputs.wheel_path" in rendered_installer
    assert "windows-11-arm" in ci["jobs"]["python"]["strategy"]["matrix"]["os"]

    full_e2e = (ROOT / ".github/workflows/holo-full-e2e.yml").read_text(encoding="utf-8")
    assert "selector: 'windows-arm64'" in full_e2e
    assert "os: 'windows-11-arm'" in full_e2e
    assert "artifact_platform: 'windows-arm64'" in full_e2e
    assert "release_default: false" in full_e2e
    assert "matrix.artifact_platform" in full_e2e


def test_windows_arm64_candidate_is_verified_and_consumed_before_merge() -> None:
    action = yaml.safe_load(
        (ROOT / ".github/actions/setup-hai-runtime-candidate/action.yml").read_text(encoding="utf-8")
    )
    assert set(action["inputs"]) == {"github-token", "run-id", "expected-head-sha"}
    downloads = [step for step in action["runs"]["steps"] if step.get("uses") == "actions/download-artifact@v4"]
    assert {step["with"]["name"] for step in downloads} == {
        "runtime-zip-windows-arm64",
        "runtime-sha-windows-arm64",
    }
    for step in downloads:
        assert step["with"]["repository"] == "hcompai/hai"
        assert step["with"]["github-token"] == "${{ inputs.github-token }}"
        assert step["with"]["run-id"] == "${{ inputs.run-id }}"

    rendered_action = yaml.safe_dump(action, sort_keys=True)
    assert "run.status -ne" in rendered_action
    assert "run.conclusion -ne" in rendered_action
    assert "run.head_sha -ne" in rendered_action
    assert "Windows ARM64 runtime artifact SHA mismatch" in rendered_action
    assert "hai-agent-runtime.exe" in rendered_action
    assert "GITHUB_PATH" in rendered_action

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    installer = ci["jobs"]["windows-arm64-installer"]
    candidate = next(step for step in installer["steps"] if step.get("id") == "runtime_candidate")
    assert candidate["if"] == "vars.HAI_WINDOWS_ARM64_CANDIDATE_RUN_ID != ''"
    assert candidate["uses"] == "./.github/actions/setup-hai-runtime-candidate"
    assert candidate["with"] == {
        "github-token": "${{ secrets.HAI_ACTIONS_READ_TOKEN }}",
        "run-id": "${{ vars.HAI_WINDOWS_ARM64_CANDIDATE_RUN_ID }}",
        "expected-head-sha": "${{ vars.HAI_WINDOWS_ARM64_CANDIDATE_HEAD_SHA }}",
    }
    installer_run = next(
        step for step in installer["steps"] if step.get("name") == "Install from the pull request checkout"
    )
    assert "HAI_AGENT_RUNTIME_DOWNLOAD_URL" in installer_run["run"]
    assert "HAI_AGENT_RUNTIME_DOWNLOAD_SHA256" in installer_run["run"]
    assert "http.server" in installer_run["run"]
    assert "$runtimeSha -notmatch" in installer_run["run"] and "$hasCandidate" in installer_run["run"]

    full_e2e = yaml.safe_load((ROOT / ".github/workflows/holo-full-e2e.yml").read_text(encoding="utf-8"))
    e2e_candidate = next(
        step
        for step in full_e2e["jobs"]["full-e2e"]["steps"]
        if step.get("name") == "Set up the pre-merge HAI runtime candidate"
    )
    assert e2e_candidate["if"] == (
        "matrix.artifact_platform == 'windows-arm64' && vars.HAI_WINDOWS_ARM64_CANDIDATE_RUN_ID != ''"
    )
    assert e2e_candidate["uses"] == "./.github/actions/setup-hai-runtime-candidate"


def test_linux_live_workflows_install_the_pull_request_candidate() -> None:
    for relative_path in (
        ".github/workflows/holo-live-smoke.yml",
        ".github/workflows/holo-full-e2e.yml",
    ):
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Install Linux candidate through shell installer" in workflow
        assert "HOLO_INSTALL_MANIFEST_URL" in workflow
        assert "HOLO_INSTALL_PACKAGE" in workflow
        assert (
            'curl -fsSL "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/${GITHUB_SHA}/install/install.sh" | bash'
            in workflow
        )
        assert '"$HOLO_HOME/bin/holo" --help' in workflow
