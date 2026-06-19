"""Rewrite the pinned hai-agent-runtime version + per-platform sha256 in runtime_install.py."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Stdlib only on purpose: this runs as `python scripts/bump_runtime.py` in a
# checkout with no dependencies installed, so a third-party import would break
# the bump step.
RUNTIME_INSTALL = Path(__file__).parents[1] / "src" / "holo_desktop" / "agent_client" / "runtime_install.py"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FILENAME_RE = re.compile(r'"hai-agent-runtime-([^".]+)\.zip"')


@dataclass(frozen=True)
class RuntimeBump:
    version: str
    shas: dict[str, str]  # platform key (e.g. darwin-arm64) -> sha256 hex

    def __post_init__(self) -> None:
        for platform, sha in self.shas.items():
            if not _SHA256_RE.fullmatch(sha):
                raise ValueError(f"{platform}: {sha!r} is not a lowercase 64-char sha256")


def _filename_for(platform: str) -> str:
    return f"hai-agent-runtime-{platform}.zip"


def _manifest_platforms(source: str) -> set[str]:
    """Platform keys that have a published artifact literal in `source`."""
    return set(_MANIFEST_FILENAME_RE.findall(source))


def apply_bump(source: str, bump: RuntimeBump) -> str:
    """Return `source` with PINNED_RUNTIME_VERSION and the manifest digests replaced; raises if any anchor is missing."""
    published = _manifest_platforms(source)
    extra = bump.shas.keys() - published
    if extra:
        raise ValueError(f"no manifest entry for platform(s): {sorted(extra)}")
    # The version is a single literal feeding every derived URL, so any published
    # platform left without a fresh sha would keep a stale digest at the new
    # version's URL and fail verification on download. Refuse the partial bump.
    missing = published - bump.shas.keys()
    if missing:
        raise ValueError(f"missing sha for published platform(s): {sorted(missing)}")

    updated, count = re.subn(
        r'PINNED_RUNTIME_VERSION = "[^"]*"',
        f'PINNED_RUNTIME_VERSION = "{bump.version}"',
        source,
    )
    if count != 1:
        raise ValueError(f"expected exactly one PINNED_RUNTIME_VERSION assignment, found {count}")

    for platform, sha in bump.shas.items():
        filename = _filename_for(platform)
        pattern = re.compile(rf'("{re.escape(filename)}",\s*")[0-9a-fA-F]{{64}}(")')
        updated, count = pattern.subn(rf"\g<1>{sha}\g<2>", updated)
        if count != 1:
            raise ValueError(f"expected exactly one sha256 literal for {filename}, found {count}")
    return updated


def _parse_args(argv: list[str]) -> RuntimeBump:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--sha",
        action="append",
        required=True,
        metavar="PLATFORM=SHA256",
        help="per-platform digest, e.g. darwin-arm64=<hex> (repeatable)",
    )
    args = parser.parse_args(argv)
    shas: dict[str, str] = {}
    for entry in args.sha:
        platform, _, sha = entry.partition("=")
        if not platform or not sha:
            parser.error(f"--sha must be PLATFORM=SHA256, got {entry!r}")
        shas[platform] = sha.lower()
    return RuntimeBump(version=args.version, shas=shas)


def main(argv: list[str]) -> int:
    bump = _parse_args(argv)
    source = RUNTIME_INSTALL.read_text()
    RUNTIME_INSTALL.write_text(apply_bump(source, bump))
    print(f"bumped runtime to {bump.version} ({', '.join(sorted(bump.shas))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
