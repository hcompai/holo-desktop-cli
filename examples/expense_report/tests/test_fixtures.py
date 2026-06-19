"""Behavioural tests for the OSWorld fixture downloader.

Uses `httpx.MockTransport` so we exercise the real client, real streaming,
real sha256 hashing, real cache hardlink/copy, real `tomli`/`tomli_w` round-trip.
No mocks of our own code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from expense_report_demo import fixtures

# Cache the real Client constructor so our stub factory can still build one even
# after fixtures.httpx.Client is monkeypatched to point at our stub.
_REAL_HTTPX_CLIENT = httpx.Client


def _client(payload_for: dict[str, bytes]) -> httpx.Client:
    """A real httpx.Client whose transport serves canned bytes per URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = payload_for.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="missing")
        return httpx.Response(200, content=body)

    return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler), follow_redirects=True)


def _write_manifest(path: Path, pulls: list[tuple[str, str, str]]) -> None:
    """Write a minimal TOML manifest from a list of (url, dest, sha256) tuples."""
    body = ""
    for url, dest, sha in pulls:
        body += "[[pull]]\n"
        body += f'url = "{url}"\n'
        body += f'dest = "{dest}"\n'
        body += f'sha256 = "{sha}"\n\n'
    path.write_text(body)


def test_ensure_downloads_validates_and_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: empty cache, manifest entry with right sha256, file lands at dest."""
    payload = b"hello world"
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://example.com/file.bin"

    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [(url, "subdir/file.bin", sha)])

    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({url: payload}))

    dest_root = tmp_path / "out"
    fixtures.ensure(manifest_path, dest_root, cache_dir=tmp_path / "cache")

    dest = dest_root / "subdir" / "file.bin"
    assert dest.is_file()
    assert dest.read_bytes() == payload


def test_ensure_hash_mismatch_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the server returns content whose sha256 doesn't match the manifest, raise."""
    url = "https://example.com/file.bin"
    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [(url, "f.bin", "deadbeef" * 8)])

    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({url: b"actual payload"}))

    with pytest.raises(ValueError, match="sha256 mismatch"):
        fixtures.ensure(manifest_path, tmp_path / "out", cache_dir=tmp_path / "cache")


def test_ensure_uses_cache_on_second_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After the first ensure(), the cache holds the file; a second ensure with the
    same sha must not re-fetch (we serve a 404 to prove it)."""
    payload = b"cached!"
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://example.com/file.bin"

    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [(url, "f.bin", sha)])

    cache_dir = tmp_path / "cache"
    dest_root = tmp_path / "out"

    # First call: server has the payload.
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({url: payload}))
    fixtures.ensure(manifest_path, dest_root, cache_dir=cache_dir)

    dest = dest_root / "f.bin"
    dest.unlink()  # remove dest, keep cache

    # Second call: server returns 404; cache should satisfy.
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({}))
    fixtures.ensure(manifest_path, dest_root, cache_dir=cache_dir)
    assert dest.is_file()
    assert dest.read_bytes() == payload


def test_ensure_missing_sha_raises(tmp_path: Path) -> None:
    """A manifest entry without a sha256 is a hard error in ensure (user must `pin` first)."""
    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [("https://example.com/x", "x", "")])

    with pytest.raises(ValueError, match="missing sha256"):
        fixtures.ensure(manifest_path, tmp_path / "out", cache_dir=tmp_path / "cache")


def test_pin_writes_sha256_back_to_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pin() downloads, computes sha256, rewrites the TOML with the hash filled in."""
    payload = b"pin me"
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://example.com/y"

    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [(url, "y.bin", "")])

    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({url: payload}))

    dest_root = tmp_path / "out"
    fixtures.pin(manifest_path, dest_root, cache_dir=tmp_path / "cache")
    after = fixtures.load(manifest_path)
    assert len(after.pull) == 1
    assert after.pull[0].sha256 == sha
    # pin must materialize the file under dest, not only rewrite the TOML.
    dest = dest_root / "y.bin"
    assert dest.is_file()
    assert dest.read_bytes() == payload


def test_pin_already_pinned_still_materializes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fully-pinned manifest still ends with files linked under dest_root, not just
    an identical TOML rewrite."""
    payload = b"already pinned"
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://example.com/p"

    manifest_path = tmp_path / "m.toml"
    _write_manifest(manifest_path, [(url, "sub/p.bin", sha)])

    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_kw: _client({url: payload}))

    dest_root = tmp_path / "out"
    fixtures.pin(manifest_path, dest_root, cache_dir=tmp_path / "cache")

    dest = dest_root / "sub" / "p.bin"
    assert dest.is_file()
    assert dest.read_bytes() == payload
