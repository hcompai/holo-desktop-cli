"""Raise the `hai-agents` floor to the latest SDK release and stage the matching Holo patch release."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = re.compile(r'"hai-agents\[cli,workstation\]>=(\d+\.\d+\.\d+)"')
VERSION = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)
PIN_URL = "https://raw.githubusercontent.com/hcompai/hai-agents-python/v{}/src/hai_agents_local/runtime/pin.json"


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def sync(root: Path, sdk: str, runtime: str | None, today: str) -> str | None:
    """Rewrite the release files for `sdk`; returns the new Holo version, or None when already synced."""
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text()
    floor = FLOOR.search(text)
    version = VERSION.search(text)
    if floor is None or version is None:
        raise SystemExit("pyproject.toml has no hai-agents[cli,workstation] floor or project version")
    if _parse(sdk) <= _parse(floor.group(1)):
        return None
    major, minor, patch = version.groups()
    new = f"{major}.{minor}.{int(patch) + 1}"
    text = FLOOR.sub(f'"hai-agents[cli,workstation]>={sdk}"', text, count=1)
    pyproject.write_text(VERSION.sub(f'version = "{new}"', text, count=1))

    manifest = root / "install" / "manifest.json"
    data = json.loads(manifest.read_text())
    data["holo_version"] = new
    manifest.write_text(json.dumps(data, indent=2) + "\n")

    requires = f"- Requires `hai-agents` {sdk}+" + (f" (`hai-agent-runtime` {runtime})." if runtime else ".")
    changelog = root / "CHANGELOG.md"
    notes = changelog.read_text()
    heading = f"## [{new}] - {today}"
    if "## [Unreleased]\n\n" in notes:
        notes = notes.replace("## [Unreleased]\n\n", f"{heading}\n\n{requires}\n", 1)
    else:
        first = notes.index("\n## [") + 1
        notes = f"{notes[:first]}{heading}\n\n{requires}\n\n{notes[first:]}"
    changelog.write_text(notes)
    return new


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="hai-agents version to sync to (default: latest on PyPI)")
    args = parser.parse_args()
    sdk = args.sdk or _fetch_json("https://pypi.org/pypi/hai-agents/json")["info"]["version"]
    try:
        runtime = _fetch_json(PIN_URL.format(sdk)).get("version")
    except OSError:
        runtime = None
    new = sync(ROOT, sdk, runtime, datetime.datetime.now(datetime.UTC).date().isoformat())
    print(f"hai-agents {sdk}: " + (f"staged Holo {new}" if new else "already synced"))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as handle:
            handle.write(f"sdk={sdk}\nversion={new or ''}\nchanged={'true' if new else 'false'}\n")


if __name__ == "__main__":
    main()
