"""Behavioural tests for the runtime pin-bump rewriter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import bump_runtime
import pytest
from bump_runtime import RuntimeBump, apply_bump

from holo_desktop.agent_client import runtime_install

REAL_SOURCE = Path(runtime_install.__file__).read_text()
NEW_DARWIN = "a" * 64
NEW_WINDOWS = "b" * 64
NEW_LINUX = "c" * 64
NEW_WINDOWS_ARM = "d" * 64
ALL_PLATFORM_SHAS = {
    "darwin-arm64": NEW_DARWIN,
    "windows-x86_64": NEW_WINDOWS,
    "linux-x86_64": NEW_LINUX,
    "windows-arm64": NEW_WINDOWS_ARM,
}


def test_apply_bump_rewrites_version_and_digests() -> None:
    bump = RuntimeBump(version="0.2.0", shas=ALL_PLATFORM_SHAS)
    result = apply_bump(REAL_SOURCE, bump)

    assert 'PINNED_RUNTIME_VERSION = "0.2.0"' in result
    assert all(sha in result for sha in ALL_PLATFORM_SHAS.values())
    # The version literal must not appear duplicated in any artifact URL (URLs are derived).
    assert result.count('PINNED_RUNTIME_VERSION = "') == 1
    # A placeholder digest must be replaceable like any other (windows-arm64 pre-release).
    assert runtime_install.PLACEHOLDER_SHA256 not in result


def test_apply_bump_keeps_each_digest_with_its_platform() -> None:
    bump = RuntimeBump(version="0.2.0", shas=dict(ALL_PLATFORM_SHAS))
    result = apply_bump(REAL_SOURCE, bump)

    darwin_idx = result.index("hai-agent-runtime-darwin-arm64.zip")
    windows_idx = result.index("hai-agent-runtime-windows-x86_64.zip")
    linux_idx = result.index("hai-agent-runtime-linux-x86_64.zip")
    windows_arm_idx = result.index("hai-agent-runtime-windows-arm64.zip")
    # Each digest must sit directly after its own filename literal.
    assert darwin_idx < result.index(NEW_DARWIN) < windows_idx
    assert windows_idx < result.index(NEW_WINDOWS) < linux_idx
    assert linux_idx < result.index(NEW_LINUX) < windows_arm_idx
    assert windows_arm_idx < result.index(NEW_WINDOWS_ARM)


def test_apply_bump_rejects_non_hex_sha() -> None:
    with pytest.raises(ValueError, match="sha256"):
        RuntimeBump(version="0.2.0", shas={"darwin-arm64": "not-a-sha"})


def test_apply_bump_raises_when_platform_filename_absent() -> None:
    # darwin-x86_64 (macOS Intel) has no published manifest entry, so a bump
    # targeting it has nowhere to write and must be refused.
    bump = RuntimeBump(version="0.2.0", shas={"darwin-x86_64": "c" * 64})
    with pytest.raises(ValueError, match="darwin-x86_64"):
        apply_bump(REAL_SOURCE, bump)


def test_apply_bump_requires_a_sha_for_every_published_platform() -> None:
    # A partial bump leaves the omitted platforms pinned to a stale digest at
    # the new version's URL — a guaranteed download verification failure.
    bump = RuntimeBump(
        version="0.2.0",
        shas={"darwin-arm64": NEW_DARWIN, "windows-x86_64": NEW_WINDOWS, "linux-x86_64": NEW_LINUX},
    )
    with pytest.raises(ValueError, match="windows-arm64"):
        apply_bump(REAL_SOURCE, bump)


def test_script_imports_with_stdlib_only() -> None:
    # `python scripts/bump_runtime.py` runs in a checkout with no deps installed.
    # `-S` disables site-packages, so any third-party import would fail here
    # exactly as it would in CI.
    script_dir = Path(bump_runtime.__file__).parent
    result = subprocess.run(
        [sys.executable, "-S", "-c", "import bump_runtime"],
        cwd=script_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
