"""OSWorld fixture downloader with sha256-keyed cache.

Reads a TOML manifest of `[[pull]]` entries (url, dest, sha256) and ensures
each file lives at `<dest_root>/<dest>` with the right hash. Files are first
downloaded into `<cache_dir>/<sha>.bin` (caller-provided so it can be shared
across demos), then hard-linked into the per-demo dest. Hash mismatch raises
and deletes the cached file so the next run retries cleanly.

Run `expense-report-demo pin-fixtures <manifest>` to compute missing hashes, write them
back into the TOML, and materialize every file under its dest (one-shot,
opt-in — never silent in CI).
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tomllib
from pathlib import Path

import httpx
import tomli_w
from pydantic import BaseModel, ConfigDict, Field

_DOWNLOAD_CHUNK = 64 * 1024
_HTTP_TIMEOUT_S = 60.0


class FixturePull(BaseModel):
    """One file to download. sha256 may be empty during initial authoring; pin via --pin."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    url: str = Field(min_length=1)
    dest: str = Field(min_length=1, description="Relative path under <dest_root>")
    sha256: str = Field(description="Hex sha256; empty allowed only when --pin is in flight")


class FixtureManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pull: list[FixturePull] = Field(min_length=1)


def load(manifest_path: Path) -> FixtureManifest:
    """Parse a TOML manifest into a validated FixtureManifest."""
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return FixtureManifest.model_validate(data)


def ensure(manifest_path: Path, dest_root: Path, cache_dir: Path) -> None:
    """Download (if missing) and link every pull in the manifest. Raises on
    hash mismatch with the cache wiped so the next run retries cleanly."""
    manifest = load(manifest_path)
    dest_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True)
    try:
        for pull in manifest.pull:
            _ensure_one(client, pull, dest_root, cache_dir)
    finally:
        client.close()


def pin(manifest_path: Path, dest_root: Path, cache_dir: Path) -> None:
    """One-shot: compute any missing sha256s, write them back into the TOML, then
    materialize every entry under `dest_root` (downloading/verifying via `ensure`)."""
    manifest = load(manifest_path)
    dest_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True)
    pinned: list[FixturePull] = []
    try:
        for pull in manifest.pull:
            if pull.sha256:
                pinned.append(pull)
                continue
            print(f"  [pin] {pull.url}", file=sys.stderr)
            data = _download(client, pull.url)
            sha = hashlib.sha256(data).hexdigest()
            cache_path = cache_dir / f"{sha}.bin"
            cache_path.write_bytes(data)
            pinned.append(FixturePull(url=pull.url, dest=pull.dest, sha256=sha))
    finally:
        client.close()
    out = {"pull": [p.model_dump() for p in pinned]}
    manifest_path.write_text(tomli_w.dumps(out), encoding="utf-8")
    print(f"  [pin] wrote {manifest_path}", file=sys.stderr)

    # Now that every entry has a hash, link them all into dest_root so a pin run
    # leaves fixtures ready to use, not just a rewritten manifest.
    ensure(manifest_path, dest_root, cache_dir)


def _ensure_one(client: httpx.Client, pull: FixturePull, dest_root: Path, cache_dir: Path) -> None:
    if not pull.sha256:
        raise ValueError(
            f"manifest entry for {pull.dest!r} is missing sha256; run `expense-report-demo pin-fixtures <manifest>` to populate"
        )
    fetch_to(client, pull.url, pull.sha256, dest_root / pull.dest, cache_dir)


def fetch_to(client: httpx.Client, url: str, sha256: str, dest: Path, cache_dir: Path) -> None:
    """Sha256-cached download into an arbitrary absolute `dest`. Shared by the
    manifest-driven path (`ensure`) and ad-hoc per-task DownloadFile setups."""
    if not sha256:
        raise ValueError(f"fetch_to({url!r}): sha256 is required to enable caching")
    cache_path = cache_dir / f"{sha256}.bin"

    if dest.exists() and _sha256(dest) == sha256:
        return

    if not (cache_path.exists() and _sha256(cache_path) == sha256):
        cache_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [fetch] {url}", file=sys.stderr)
        data = _download(client, url)
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha256:
            raise ValueError(f"sha256 mismatch for {url}: manifest={sha256} actual={actual}")
        cache_path.write_bytes(data)

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        dest.hardlink_to(cache_path)
    except OSError:
        shutil.copy2(cache_path, dest)


def _download(client: httpx.Client, url: str) -> bytes:
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        buf = bytearray()
        for chunk in resp.iter_bytes(_DOWNLOAD_CHUNK):
            buf.extend(chunk)
        return bytes(buf)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
