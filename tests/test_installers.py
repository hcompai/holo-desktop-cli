from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_DIR = ROOT / "install"


def test_manifest_matches_package_and_lock() -> None:
    manifest = json.loads((INSTALL_DIR / "manifest.json").read_text())
    assert set(manifest["supported_platforms"]) == {
        "darwin-arm64",
        "windows-x86_64",
        "windows-arm64",
        "linux-x86_64",
    }
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["holo_version"] == pyproject["project"]["version"]
    assert manifest["python_version"] == "3.12"
    for entry in manifest["supported_platforms"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["uv_sha256"])
        assert entry["uv_url"].startswith("https://")

    dependencies = manifest["supported_platforms"]["windows-arm64"]["dependency_wheels"]
    assert dependencies == [
        {
            "name": "cryptography",
            "version": "48.0.0",
            "url": "BUILD_AT_RELEASE",
            "sha256": "0" * 64,
        }
    ]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_cryptography = next(package for package in lock["package"] if package["name"] == "cryptography")
    assert dependencies[0]["version"] == locked_cryptography["version"]


def test_installers_parse() -> None:
    subprocess.run(["sh", "-n", str(INSTALL_DIR / "install.sh")], check=True)
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


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows architecture detection")
@pytest.mark.parametrize(
    "shell",
    [path for name in ("powershell", "pwsh") if (path := shutil.which(name))],
)
def test_install_ps1_detects_native_architecture_with_psreadline_loaded(shell: str) -> None:
    command = r"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path 'install/install.ps1'),
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -ne 0) {
    throw "install.ps1 parse errors: $errors"
}

foreach ($name in @('Fail', 'Get-HoloWindowsPlatform')) {
    $definition = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if ($null -eq $definition) {
        throw "install.ps1 does not define $name"
    }
    Invoke-Expression $definition.Extent.Text
}

Import-Module PSReadLine -ErrorAction Stop
$platform = Get-HoloWindowsPlatform
$architecture = [System.Runtime.InteropServices.RuntimeInformation, mscorlib]::OSArchitecture.ToString()
$expected = switch ($architecture) {
    'X64' { 'windows-x86_64' }
    'Arm64' { 'windows-arm64' }
    default { throw "test has no expectation for Windows architecture '$architecture'" }
}
if ($platform -ne $expected) {
    throw "expected $expected for $architecture, got '$platform'"
}
"""
    subprocess.run([shell, "-NoProfile", "-Command", command], cwd=ROOT, check=True)
