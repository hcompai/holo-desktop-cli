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
# A full bump must cover every published platform in the manifest.
ALL_SHAS = {"darwin-arm64": NEW_DARWIN, "windows-x86_64": NEW_WINDOWS, "linux-x86_64": NEW_LINUX}


def test_apply_bump_rewrites_version_and_digests() -> None:
    bump = RuntimeBump(version="0.2.0", shas=dict(ALL_SHAS))
    result = apply_bump(REAL_SOURCE, bump)

    assert 'PINNED_RUNTIME_VERSION = "0.2.0"' in result
    assert NEW_DARWIN in result and NEW_WINDOWS in result and NEW_LINUX in result
    # The version literal must not appear duplicated in any artifact URL (URLs are derived).
    assert result.count('PINNED_RUNTIME_VERSION = "') == 1
    # Untouched platform digests of the original must be gone (both were replaced).
    assert "f4085285a9722730408fd5e5dfc36672809ba60250552cf701a5e1198bdc2427" not in result


def test_apply_bump_keeps_each_digest_with_its_platform() -> None:
    bump = RuntimeBump(version="0.2.0", shas=dict(ALL_SHAS))
    result = apply_bump(REAL_SOURCE, bump)

    darwin_idx = result.index("hai-agent-runtime-darwin-arm64.zip")
    windows_idx = result.index("hai-agent-runtime-windows-x86_64.zip")
    assert result.index(NEW_DARWIN, darwin_idx) < result.index(NEW_WINDOWS, windows_idx)
    # The darwin digest must sit between the darwin filename and the windows entry.
    assert darwin_idx < result.index(NEW_DARWIN) < windows_idx


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
    # darwin alone bumps the shared version but leaves windows pinned to a stale
    # digest at the new version's URL — a guaranteed download verification failure.
    bump = RuntimeBump(version="0.2.0", shas={"darwin-arm64": NEW_DARWIN})
    with pytest.raises(ValueError, match="windows-x86_64"):
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
