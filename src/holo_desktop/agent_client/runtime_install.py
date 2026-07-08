"""Download-on-first-run install of the hai-agent-runtime binary."""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TransferSpeedColumn
from rich.prompt import Confirm

from holo_desktop.settings import DOWNLOAD_SHA256_ENV, DOWNLOAD_URL_ENV, RuntimeInstallSettings

logger = logging.getLogger(__name__)

PINNED_RUNTIME_VERSION = "0.1.8"
RUNTIME_DIR = Path.home() / ".holo" / "runtime"
# Artifacts live under an immutable, version-scoped prefix, so a CDN edge can never serve stale bytes.
RUNTIME_CDN_BASE = "https://assets.hcompanyprod.fr/hai-agent-runtime"
BINARY_NAME = "hai-agent-runtime.exe" if os.name == "nt" else "hai-agent-runtime"
# Guard value: published manifest entries must never use it, since every download would fail verification.
PLACEHOLDER_SHA256 = "0" * 64
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=600.0)
# Generous ceiling (the runtime is hundreds of MB); guards against a lying/absent Content-Length filling the disk.
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _require_secure_url(url: str) -> None:
    """Allow https anywhere, plain http only against loopback (test/ops overrides); reject the rest."""
    parsed = urlsplit(url)
    if parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS):
        return
    raise RuntimeError(f"refusing insecure hai-agent-runtime download URL (need https): {url}")


class RuntimeArtifactUnavailable(NotImplementedError):
    """Raised when the current platform has no published managed runtime artifact."""


class RuntimeArtifact(BaseModel):
    url: str
    sha256: str


def _artifact(filename: str, sha256: str) -> RuntimeArtifact:
    """A published release file resolved to its pinned, version-scoped CDN URL."""
    return RuntimeArtifact(url=f"{RUNTIME_CDN_BASE}/{PINNED_RUNTIME_VERSION}/{filename}", sha256=sha256)


MANIFEST: dict[str, RuntimeArtifact] = {
    "darwin-arm64": _artifact(
        "hai-agent-runtime-darwin-arm64.zip",
        "1aed0055898116732aee031dc4a1235782b2909ee51e0367e2d50bb3be6671c9",
    ),
    "windows-x86_64": _artifact(
        "hai-agent-runtime-windows-x86_64.zip",
        "4e6b2bcd42af2bb6b22197fcde947327497f5c62fd60d48bc9037730d80dc691",
    ),
}

UNIMPLEMENTED_PLATFORMS: dict[str, str] = {
    "darwin-x86_64": "hai-agent-runtime is not published for macOS Intel yet",
    "linux-x86_64": "hai-agent-runtime is not published for Linux yet",
}


def platform_key() -> str:
    if sys.platform == "darwin":
        system = "darwin"
    elif sys.platform.startswith("linux"):
        system = "linux"
    elif sys.platform == "win32":
        system = "windows"
    else:
        raise RuntimeError(f"unsupported platform for hai-agent-runtime: {sys.platform}")
    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}.get(machine)
    if arch is None:
        raise RuntimeError(f"unsupported architecture for hai-agent-runtime: {machine}")
    return f"{system}-{arch}"


def pinned_artifact(*, settings: RuntimeInstallSettings) -> RuntimeArtifact:
    """Artifact to install: env override (tests/ops) or the pinned per-platform manifest entry."""
    if settings.download_url:
        if not settings.download_sha256:
            raise RuntimeError(
                f"{DOWNLOAD_URL_ENV} is set but {DOWNLOAD_SHA256_ENV} is not; refusing an unverified download"
            )
        return RuntimeArtifact(url=settings.download_url, sha256=settings.download_sha256)
    key = platform_key()
    if key in UNIMPLEMENTED_PLATFORMS:
        raise RuntimeArtifactUnavailable(
            f"{UNIMPLEMENTED_PLATFORMS[key]}; put hai-agent-runtime on PATH, "
            f"or set {DOWNLOAD_URL_ENV} + {DOWNLOAD_SHA256_ENV} to a trusted build"
        )
    artifact = MANIFEST.get(key)
    if artifact is None:
        raise RuntimeError(f"no hai-agent-runtime release artifact for platform {key}")
    if artifact.sha256 == PLACEHOLDER_SHA256:
        raise RuntimeError(
            f"hai-agent-runtime v{PINNED_RUNTIME_VERSION} has no published artifact for {key} yet; "
            f"put hai-agent-runtime on PATH, or set {DOWNLOAD_URL_ENV} + {DOWNLOAD_SHA256_ENV} to a trusted build"
        )
    return artifact


def _find_binary(root: Path) -> Path | None:
    direct = root / BINARY_NAME
    if direct.is_file():
        return direct
    # macOS app-bundle shape: <version>/<name>.app/Contents/MacOS/hai-agent-runtime
    for candidate in sorted(root.glob("*.app/Contents/MacOS/hai-agent-runtime")):
        if candidate.is_file():
            return candidate
    return None


def installed_binary(version: str) -> Path | None:
    """The managed install's executable for `version`, or None if absent/incomplete."""
    return _find_binary(RUNTIME_DIR / version)


FIRST_RUN_MARKER = ".first-run-complete"


def first_run_pending(version: str) -> bool:
    """True until a task completes against the managed install (including before it is downloaded)."""
    return not (RUNTIME_DIR / version / FIRST_RUN_MARKER).exists()


def mark_first_run_complete(version: str) -> None:
    version_dir = RUNTIME_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / FIRST_RUN_MARKER).touch()


def confirm_download() -> bool:
    """One-line TTY confirmation (default yes); non-TTY contexts (mcp/acp hosts) download without asking."""
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        logger.info("hai-agent-runtime %s not found; downloading to %s", PINNED_RUNTIME_VERSION, RUNTIME_DIR)
        return True
    console = Console(stderr=True)
    console.print(f"[bold]hai-agent-runtime[/bold] v{PINNED_RUNTIME_VERSION} is not installed.")
    return Confirm.ask(f"Download it to [cyan]{RUNTIME_DIR}[/cyan]?", default=True, console=console)


def install_runtime(artifact: RuntimeArtifact) -> Path:
    """Download, sha256-verify, and atomically install `artifact` as the pinned runtime; returns the executable path."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    version_dir = RUNTIME_DIR / PINNED_RUNTIME_VERSION

    # Stage on the same filesystem as the final location so os.replace stays atomic.
    with tempfile.TemporaryDirectory(dir=RUNTIME_DIR, prefix=".staging-") as staging_str:
        staging = Path(staging_str)
        download_path = staging / "artifact"
        actual_sha256 = _download_to(artifact.url, download_path)
        if actual_sha256 != artifact.sha256.lower():
            raise RuntimeError(
                f"hai-agent-runtime download failed sha256 verification: expected {artifact.sha256}, "
                f"got {actual_sha256} (url: {artifact.url})"
            )

        staged_version = staging / "version"
        staged_version.mkdir()
        if artifact.url.endswith(".zip"):
            # Contents are sha256-verified above, so extraction is trusted.
            with zipfile.ZipFile(download_path) as archive:
                archive.extractall(staged_version)
        else:
            shutil.move(download_path, staged_version / BINARY_NAME)

        binary = _find_binary(staged_version)
        if binary is None:
            raise RuntimeError(f"downloaded artifact contains no hai-agent-runtime executable (url: {artifact.url})")
        binary.chmod(0o755)  # zipfile does not preserve the exec bit

        try:
            os.replace(staged_version, version_dir)
        except OSError:
            # Target occupied: a concurrent installer won the race, or a half-finished dir is in the way.
            existing = installed_binary(PINNED_RUNTIME_VERSION)
            if existing is not None:
                logger.info("hai-agent-runtime %s already installed by a concurrent run", PINNED_RUNTIME_VERSION)
                return existing
            shutil.rmtree(version_dir, ignore_errors=True)
            os.replace(staged_version, version_dir)

    installed = installed_binary(PINNED_RUNTIME_VERSION)
    assert installed is not None, "atomic rename just published the staged install"
    logger.info("installed hai-agent-runtime %s at %s", PINNED_RUNTIME_VERSION, installed)
    return installed


def ensure_managed_runtime(*, settings: RuntimeInstallSettings, assume_yes: bool = False) -> Path:
    """Return the pinned managed runtime, downloading it when absent and approved."""
    existing = installed_binary(PINNED_RUNTIME_VERSION)
    if existing is not None:
        return existing
    artifact = pinned_artifact(settings=settings)
    if not assume_yes and not confirm_download():
        raise RuntimeError("hai-agent-runtime download declined")
    return install_runtime(artifact)


def _download_to(url: str, dest: Path) -> str:
    """Stream `url` into `dest`; returns the sha256 hex digest of the bytes written."""
    _require_secure_url(url)
    digest = hashlib.sha256()
    written = 0
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as client,
            client.stream("GET", url) as response,
        ):
            _require_secure_url(str(response.url))  # a redirect must not downgrade to plain http
            if response.status_code != 200:
                raise RuntimeError(f"hai-agent-runtime download failed: HTTP {response.status_code} from {url}")
            total = int(response.headers.get("Content-Length", "0")) or None
            if total is not None and total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"hai-agent-runtime download too large: {total} bytes exceeds {MAX_DOWNLOAD_BYTES}")
            with dest.open("wb") as fh, _progress(url, total) as advance:
                for chunk in response.iter_bytes():
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(f"hai-agent-runtime download exceeded {MAX_DOWNLOAD_BYTES} bytes; aborting")
                    digest.update(chunk)
                    fh.write(chunk)
                    advance(len(chunk))
    except httpx.HTTPError as exc:
        raise RuntimeError(f"hai-agent-runtime download failed: {exc} (url: {url})") from exc
    return digest.hexdigest()


@contextmanager
def _progress(url: str, total: int | None) -> Iterator[Callable[[int], None]]:
    """Rich progress bar on a TTY; plain log lines otherwise."""
    if not sys.stderr.isatty():
        logger.info("downloading hai-agent-runtime from %s", url)
        yield lambda _n: None
        logger.info("download complete")
        return

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=Console(stderr=True),
    ) as progress:
        task_id = progress.add_task("hai-agent-runtime", total=total)
        yield lambda n: progress.update(task_id, advance=n)
