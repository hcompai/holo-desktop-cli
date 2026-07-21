from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_DIR = ROOT / "install"


def test_manifest_supports_only_v1_platforms_with_real_hashes() -> None:
    manifest = json.loads((INSTALL_DIR / "manifest.json").read_text())
    assert set(manifest["supported_platforms"]) == {"darwin-arm64", "windows-x86_64", "linux-x86_64"}
    assert manifest["holo_version"] == "0.0.2"
    assert manifest["python_version"] == "3.12"
    for entry in manifest["supported_platforms"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["uv_sha256"])
        assert entry["uv_url"].startswith("https://")


def test_install_sh_has_supported_and_unsupported_platform_paths() -> None:
    script = INSTALL_DIR / "install.sh"
    subprocess.run(["sh", "-n", str(script)], check=True)
    text = script.read_text()
    assert "Darwin" in text
    assert "arm64" in text
    assert "linux-x86_64" in text
    assert "darwin-x86_64" in text
    assert "HOLO_INSTALL_SKIP_PATH" in text
    assert "HOLO_INSTALL_SKIP_RUN_SETUP" in text
    assert "HOLO_INSTALL_MANIFEST_URL" in text
    assert "https://install.hcompany.ai/install/manifest.json" in text
    assert 'path_line="export PATH=\\"$HOLO_HOME/bin:\\$PATH\\""' in text
    assert "--no-bin" in text
    assert "--reinstall-package holo-desktop-cli" in text
    assert "python -m holo_desktop.installer_bootstrap --yes" in text
    assert 'holo" setup' not in text


def test_install_ps1_targets_windows_x86_64_and_user_path() -> None:
    text = (INSTALL_DIR / "install.ps1").read_text()
    assert "IsWindows" in text
    assert "X64" in text
    assert "[Environment]::SetEnvironmentVariable" in text
    assert "windows-x86_64" in text
    assert "https://install.hcompany.ai/install/manifest.json" in text
    assert "HOLO_INSTALL_SKIP_RUN_SETUP" in text
    assert "--no-bin" in text
    assert "--no-registry" in text
    assert "--reinstall-package holo-desktop-cli" in text
    assert "python -m holo_desktop.installer_bootstrap --yes" in text
    assert 'holo.exe") setup' not in text


def test_install_ps1_parses_when_powershell_is_available() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        return
    subprocess.run(
        [
            shell,
            "-NoProfile",
            "-Command",
            "$null = [scriptblock]::Create((Get-Content -Raw install/install.ps1)); 'ok'",
        ],
        cwd=ROOT,
        check=True,
    )


def test_holo_help_does_not_expose_installer_bootstrap() -> None:
    result = subprocess.run(["holo", "--help"], check=True, capture_output=True, text=True)
    assert "{run,stop,guard,serve,agent-api,mcp,acp,install,login,whoami,doctor}" in result.stdout
    assert "installer_bootstrap" not in result.stdout
