"""Behavioural tests for download-on-first-run of the hai-agent-runtime binary.

A real loopback HTTP server plays the release host. The installer must
download, verify the sha256, and atomically install under the managed runtime
dir; `resolve_command` must prefer PATH > managed install, only then download,
and raise when nothing is found. There is no env override: pointing Holo at a
different runtime requires a deliberate `hai-agent-runtime` wrapper on PATH.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest

from holo_desktop.agent_client import launcher, runtime_install
from holo_desktop.agent_client.runtime_install import (
    DOWNLOAD_SHA256_ENV,
    DOWNLOAD_URL_ENV,
    PINNED_RUNTIME_VERSION,
    RuntimeArtifact,
    install_runtime,
    installed_binary,
    pinned_artifact,
)
from holo_desktop.settings import RuntimeInstallSettings, load_holo_settings

FAKE_BINARY = b"#!/bin/sh\necho fake-runtime\n"


@contextmanager
def _release_server(payload: bytes, *, path: str = "/hai-agent-runtime") -> Iterator[str]:
    """Serve `payload` at `path`; yields the full URL."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != path:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{path}"
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def _point_at(monkeypatch: pytest.MonkeyPatch, url: str, payload: bytes) -> None:
    monkeypatch.setenv(DOWNLOAD_URL_ENV, url)
    monkeypatch.setenv(DOWNLOAD_SHA256_ENV, hashlib.sha256(payload).hexdigest())


def _artifact() -> runtime_install.RuntimeArtifact:
    return pinned_artifact(settings=load_holo_settings().install)


def _command() -> list[str]:
    return launcher.resolve_command(settings=load_holo_settings())


@pytest.fixture()
def runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "runtime"
    monkeypatch.setattr(runtime_install, "RUNTIME_DIR", target)
    return target


def test_install_downloads_verifies_and_installs(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _release_server(FAKE_BINARY) as url:
        _point_at(monkeypatch, url, FAKE_BINARY)
        binary = install_runtime(_artifact())

    assert binary.read_bytes() == FAKE_BINARY
    assert binary.is_relative_to(runtime_dir / PINNED_RUNTIME_VERSION)
    if os.name != "nt":
        assert os.access(binary, os.X_OK), "installed binary must be executable"
    # A second resolve must find the managed install without re-downloading.
    assert installed_binary(PINNED_RUNTIME_VERSION) == binary


def test_checksum_mismatch_raises_and_installs_nothing(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _release_server(FAKE_BINARY) as url:
        monkeypatch.setenv(DOWNLOAD_URL_ENV, url)
        monkeypatch.setenv(DOWNLOAD_SHA256_ENV, hashlib.sha256(b"something else").hexdigest())
        with pytest.raises(RuntimeError, match="sha256"):
            install_runtime(_artifact())

    assert installed_binary(PINNED_RUNTIME_VERSION) is None, "a failed verify must not leave a binary behind"


def test_url_override_without_sha_is_refused(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DOWNLOAD_URL_ENV, "http://127.0.0.1:1/hai-agent-runtime")
    monkeypatch.delenv(DOWNLOAD_SHA256_ENV, raising=False)
    with pytest.raises(RuntimeError, match=DOWNLOAD_SHA256_ENV):
        _artifact()


def test_http_error_raises(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _release_server(FAKE_BINARY, path="/elsewhere") as url:
        wrong_url = url.replace("/elsewhere", "/missing")
        _point_at(monkeypatch, wrong_url, FAKE_BINARY)
        with pytest.raises(RuntimeError, match="404"):
            install_runtime(_artifact())
    assert installed_binary(PINNED_RUNTIME_VERSION) is None


def test_app_zip_artifact_is_extracted(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # macOS releases ship a zipped .app bundle; the executable lives inside it.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        info = zipfile.ZipInfo("hai_agent_runtime.app/Contents/MacOS/hai-agent-runtime")
        info.external_attr = 0o755 << 16
        zf.writestr(info, FAKE_BINARY)
    payload = buffer.getvalue()

    with _release_server(payload, path="/hai-agent-runtime.zip") as url:
        _point_at(monkeypatch, url, payload)
        binary = install_runtime(_artifact())

    assert binary.name == "hai-agent-runtime"
    assert "hai_agent_runtime.app" in binary.as_posix()
    assert binary.read_bytes() == FAKE_BINARY
    if os.name != "nt":
        assert os.access(binary, os.X_OK)
    assert installed_binary(PINNED_RUNTIME_VERSION) == binary


def _clear_resolution_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(DOWNLOAD_URL_ENV, raising=False)
    monkeypatch.delenv(DOWNLOAD_SHA256_ENV, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))


def _managed_install(runtime_dir: Path) -> Path:
    version_dir = runtime_dir / PINNED_RUNTIME_VERSION
    version_dir.mkdir(parents=True)
    binary = version_dir / ("hai-agent-runtime.exe" if os.name == "nt" else "hai-agent-runtime")
    binary.write_bytes(FAKE_BINARY)
    binary.chmod(0o755)
    return binary


def test_resolve_ignores_binary_env_var(runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The old HAI_AGENT_RUNTIME_BINARY escape hatch silently swapped the runtime; it must be dead.
    _clear_resolution_env(monkeypatch, tmp_path)
    binary = _managed_install(runtime_dir)
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BINARY", "python -m hai_agent_runtime")
    assert _command() == [str(binary)]


def test_resolve_raises_when_nothing_found_and_download_declined(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_resolution_env(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_install, "confirm_download", lambda: False)
    with pytest.raises(RuntimeError, match="PATH"):
        _command()


def test_resolve_prefers_path_over_managed(runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_resolution_env(monkeypatch, tmp_path)
    _managed_install(runtime_dir)
    path_dir = tmp_path / "bin"
    path_dir.mkdir()
    # Windows shutil.which only matches PATHEXT names; an extensionless file is
    # invisible there and resolution would fall through to the managed install.
    exe_name = "hai-agent-runtime.exe" if os.name == "nt" else "hai-agent-runtime"
    on_path = path_dir / exe_name
    on_path.write_bytes(FAKE_BINARY)
    on_path.chmod(0o755)
    monkeypatch.setenv("PATH", str(path_dir))
    assert [os.path.normcase(p) for p in _command()] == [os.path.normcase(str(on_path))]


def test_resolve_uses_managed_install_without_downloading(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_resolution_env(monkeypatch, tmp_path)
    binary = _managed_install(runtime_dir)
    # Any download attempt would hit a dead URL and raise; reaching it means the managed install was ignored.
    monkeypatch.setenv(DOWNLOAD_URL_ENV, "http://127.0.0.1:1/dead")
    monkeypatch.setenv(DOWNLOAD_SHA256_ENV, "0" * 64)
    assert _command() == [str(binary)]


def test_resolve_downloads_when_nothing_is_installed(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_resolution_env(monkeypatch, tmp_path)
    with _release_server(FAKE_BINARY) as url:
        _point_at(monkeypatch, url, FAKE_BINARY)
        command = _command()
    assert command == [str(installed_binary(PINNED_RUNTIME_VERSION))]
    expected = runtime_dir / PINNED_RUNTIME_VERSION
    assert Path(command[0]).is_relative_to(expected)


def test_ensure_managed_runtime_uses_existing_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    existing = tmp_path / "hai-agent-runtime"
    existing.write_text("")
    monkeypatch.setattr(runtime_install, "installed_binary", lambda version: existing)

    called = False

    def fake_install(_artifact: RuntimeArtifact) -> Path:
        nonlocal called
        called = True
        return tmp_path / "unexpected"

    monkeypatch.setattr(runtime_install, "install_runtime", fake_install)

    assert runtime_install.ensure_managed_runtime(settings=RuntimeInstallSettings(), assume_yes=True) == existing
    assert called is False


def test_ensure_managed_runtime_downloads_when_assume_yes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = RuntimeArtifact(url="https://example.test/runtime.zip", sha256="1" * 64)
    installed = tmp_path / "managed" / "hai-agent-runtime"
    monkeypatch.setattr(runtime_install, "installed_binary", lambda version: None)
    monkeypatch.setattr(runtime_install, "pinned_artifact", lambda *, settings: artifact)

    def fail_prompt() -> bool:
        raise AssertionError("assume_yes must bypass confirm_download")

    monkeypatch.setattr(runtime_install, "confirm_download", fail_prompt)
    monkeypatch.setattr(runtime_install, "install_runtime", lambda actual: installed if actual == artifact else None)

    assert runtime_install.ensure_managed_runtime(settings=RuntimeInstallSettings(), assume_yes=True) == installed


def test_ensure_managed_runtime_rejects_unimplemented_platform(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_resolution_env(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_install, "platform_key", lambda: "linux-x86_64")
    with pytest.raises(runtime_install.RuntimeArtifactUnavailable, match="not published"):
        runtime_install.ensure_managed_runtime(settings=RuntimeInstallSettings(), assume_yes=True)


@pytest.mark.parametrize(
    "platform_key, suffix",
    [
        ("darwin-arm64", ".zip"),
        ("windows-x86_64", ".zip"),
    ],
)
def test_published_manifest_entry_is_real(platform_key: str, suffix: str) -> None:
    # Published platforms must not ship placeholder values.
    artifact = runtime_install.MANIFEST[platform_key]
    assert len(artifact.sha256) == 64 and set(artifact.sha256) <= set("0123456789abcdef")
    assert artifact.sha256 != runtime_install.PLACEHOLDER_SHA256, (
        "placeholder sha256 would make every download fail verification"
    )
    assert artifact.url.startswith("https://")
    assert artifact.url.endswith(suffix)


_NETWORK_TEST_ENV = "HOLO_RUNTIME_NETWORK_TEST"


@pytest.mark.skipif(
    os.environ.get(_NETWORK_TEST_ENV, "").strip().lower() not in ("1", "true", "yes"),
    reason=f"network test against the live CDN; set {_NETWORK_TEST_ENV}=1 to run",
)
@pytest.mark.parametrize("platform_key", sorted(runtime_install.MANIFEST))
def test_pinned_artifact_is_published_and_matches_sha(platform_key: str) -> None:
    # The unit suite only checks the pin's *shape*; this proves the pinned URL is
    # actually live and its bytes hash to the pinned digest (the real end-to-end
    # guarantee a download relies on). Opt-in: it hits the network and is large.
    artifact = runtime_install.MANIFEST[platform_key]
    digest = hashlib.sha256()
    with (
        httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=600.0)) as client,
        client.stream("GET", artifact.url) as response,
    ):
        assert response.status_code == 200, f"{artifact.url} -> HTTP {response.status_code}"
        for chunk in response.iter_bytes():
            digest.update(chunk)
    assert digest.hexdigest() == artifact.sha256.lower(), f"published bytes do not match pinned sha for {platform_key}"


@pytest.mark.parametrize("platform_key", ["darwin-x86_64", "linux-x86_64"])
def test_unimplemented_platform_refuses_install(
    platform_key: str, runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unpublished platforms must be explicit product gaps, not placeholder
    # release URLs that look real until download/verification time.
    _clear_resolution_env(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_install, "platform_key", lambda: platform_key)
    with pytest.raises(runtime_install.RuntimeArtifactUnavailable, match="not published"):
        _artifact()
    assert installed_binary(PINNED_RUNTIME_VERSION) is None


@pytest.mark.parametrize("platform_key", ["darwin-x86_64", "linux-x86_64"])
def test_resolve_fails_before_prompting_on_unimplemented_platform(
    platform_key: str, runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The TTY confirm must never ask the user to approve a download that cannot happen.
    _clear_resolution_env(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_install, "platform_key", lambda: platform_key)

    def _no_prompt() -> bool:
        raise AssertionError("confirm_download must not be reached for an unimplemented platform")

    monkeypatch.setattr(runtime_install, "confirm_download", _no_prompt)
    with pytest.raises(runtime_install.RuntimeArtifactUnavailable, match="not published"):
        _command()
