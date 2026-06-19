"""Host-side HTTP bridge for NemoClaw sandbox MCP servers."""

from __future__ import annotations

import base64
import binascii
import contextlib
import hmac
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, ValidationError

from holo_desktop.cli.hosts import resolve_holo_command
from holo_desktop.customization import HOLO_DIR
from holo_desktop.fs import atomic_write_json
from holo_desktop.host_integrations.nemoclaw.constants import BRIDGE_BIND_HOST, BRIDGE_PORT

DEFAULT_HOST = BRIDGE_BIND_HOST
DEFAULT_PORT = BRIDGE_PORT
TOKEN_ENV = "HOLO_NEMOCLAW_BRIDGE_TOKEN"
RUN_LOG_TAIL_CHARS = 12000
POLL_WAIT_SECONDS = 9.0
POLL_INTERVAL_SECONDS = 0.5
MAX_JSON_BODY_BYTES = 32 * 1024 * 1024
MAX_MEDIA_ITEMS = 8
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_TOTAL_MEDIA_BYTES = 20 * 1024 * 1024
COMPLETED_RUN_RETENTION_SECONDS = 15 * 60
RESTORED_EXIT_CODE_UNAVAILABLE = 1
RUN_ID_LENGTH = 32
RUN_ID_CHARS = frozenset("0123456789abcdef")


class BridgeRequestError(Exception):
    """Client request error that should become a JSON HTTP response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class BridgeRun:
    """A launched `holo run` process and its captured output files."""

    process: subprocess.Popen[bytes] | None
    pid: int | None
    stdout_path: Path
    stderr_path: Path
    media_dir: Path | None = None
    returncode: int | None = None
    finished_at: float | None = None
    output: dict[str, str] | None = None


class RunOutput(BaseModel):
    """Captured stdout/stderr tails of a finished run."""

    model_config = ConfigDict(frozen=True)
    stdout: str
    stderr: str


class BridgeRunMetadata(BaseModel):
    """On-disk record of a run, so a restarted bridge can still answer polls."""

    model_config = ConfigDict(extra="ignore")
    pid: int | None = None
    stdout_path: str
    stderr_path: str
    media_dir: str | None = None
    returncode: int | None = None
    finished_at: float | None = None
    output: RunOutput | None = None


class NemoClawBridgeServer(ThreadingHTTPServer):
    """HTTP server carrying the auth token, run registry, and storage dirs."""

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        token: str,
        runs_dir: Path,
        media_dir: Path,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.token = token
        self.runs_dir = runs_dir
        self.media_dir = media_dir
        self.runs: dict[str, BridgeRun] = {}
        self._registry_lock = Lock()
        self._run_locks: dict[str, Lock] = {}


class NemoClawBridgeHandler(BaseHTTPRequestHandler):
    """Small JSON API that lets the sandbox start, poll, and cancel host Holo runs."""

    server: NemoClawBridgeServer

    def do_GET(self) -> None:
        if self.path != "/health":
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        self._prune_completed_runs()
        self._json(200, {"ok": True, "name": "holo-nemoclaw-bridge", "auth": True, "runs": len(self.server.runs)})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        action = self.path.strip("/") or "request"
        try:
            if self.path == "/launch":
                self._launch()
                return
            if self.path == "/poll":
                self._poll()
                return
            if self.path == "/kill":
                self._kill()
                return
        except BridgeRequestError as exc:
            self._json(exc.status, {"ok": False, "error": exc.message})
            return
        except (OSError, RuntimeError) as exc:
            self._json(500, {"ok": False, "error": f"{action} failed: {exc}"})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def _launch(self) -> None:
        run_id, bridge_run = self._start_holo_run()
        if bridge_run is None:
            return
        self._json(
            200,
            {
                "ok": True,
                "status": "running",
                "run_id": run_id,
                "message": (
                    "Started. Do not answer the user yet. Call holo_desktop_poll with this run_id until it completes."
                ),
            },
        )

    def _poll(self) -> None:
        run_id = self._run_id_from_payload()
        with self._run_lock(run_id):
            bridge_run = self._get_run(run_id)
            if bridge_run is None:
                self._json(404, {"ok": False, "error": f"unknown run_id: {run_id}"})
                return
            if bridge_run.finished_at is not None and bridge_run.output is not None:
                self._json(200, self._completed_payload(run_id, bridge_run))
                return
            returncode = self._wait_for_returncode(bridge_run)
            if returncode is None:
                self._persist_run(run_id, bridge_run)
                self._json(
                    200,
                    {
                        "ok": True,
                        "status": "running",
                        "run_id": run_id,
                        "message": (
                            "Still running. The user is waiting for completion; call holo_desktop_poll again with this "
                            "same run_id now. Do not launch another HoloDesktop task and do not ask the user to poll."
                        ),
                    },
                )
                return
            bridge_run.returncode = returncode
            bridge_run.finished_at = time.time()
            bridge_run.output = self._output(bridge_run)
            self._persist_run(run_id, bridge_run)
            self._cleanup_run_files(bridge_run)
            self._json(200, self._completed_payload(run_id, bridge_run))

    def _kill(self) -> None:
        run_id = self._run_id_from_payload()
        with self._run_lock(run_id):
            bridge_run = self._get_run(run_id)
            if bridge_run is None:
                self._json(404, {"ok": False, "error": f"unknown run_id: {run_id}"})
                return
            self._terminate_run(bridge_run)
            bridge_run.returncode = bridge_run.returncode if bridge_run.returncode is not None else -signal.SIGTERM
            bridge_run.finished_at = time.time()
            bridge_run.output = self._output(bridge_run)
            self._persist_run(run_id, bridge_run)
            self._cleanup_run_files(bridge_run)
            self._json(200, {"ok": True, "status": "cancelled", "run_id": run_id})

    def _wait_for_returncode(self, bridge_run: BridgeRun) -> int | None:
        if bridge_run.returncode is not None:
            return bridge_run.returncode
        deadline = time.monotonic() + POLL_WAIT_SECONDS
        while True:
            returncode = (
                bridge_run.process.poll() if bridge_run.process is not None else _restored_returncode(bridge_run.pid)
            )
            if returncode is not None or time.monotonic() >= deadline:
                return returncode
            time.sleep(POLL_INTERVAL_SECONDS)

    def _start_holo_run(self) -> tuple[str, BridgeRun | None]:
        payload = self._read_payload()
        task_value = payload.get("task")
        task = task_value.strip() if isinstance(task_value, str) else ""
        if not task:
            raise BridgeRequestError(400, "task is required")

        task, media_dir = self._task_with_media(task, payload.get("media"))
        env = self._env()
        command = resolve_holo_command(path=env.get("PATH"))

        run_id = uuid.uuid4().hex
        self.server.runs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.server.runs_dir / f"{run_id}.stdout.log"
        stderr_path = self.server.runs_dir / f"{run_id}.stderr.log"
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                [command, "run", task],
                stdout=stdout_file,
                stderr=stderr_file,
                env=env,
            )
        bridge_run = BridgeRun(
            process=process,
            pid=process.pid,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            media_dir=media_dir,
        )
        self._store_run(run_id, bridge_run)
        self._prune_completed_runs()
        return run_id, bridge_run

    def _task_with_media(self, task: str, media: object) -> tuple[str, Path | None]:
        if media is None:
            return task, None
        if not isinstance(media, list):
            raise BridgeRequestError(400, "media must be a list")
        if len(media) > MAX_MEDIA_ITEMS:
            raise BridgeRequestError(413, "too many media items")

        decoded_media: list[tuple[str, bytes]] = []
        total_media_bytes = 0
        for i, item in enumerate(media):
            if not isinstance(item, dict):
                raise BridgeRequestError(400, "each media item must be an object")
            basename = Path(str(item.get("name") or f"attachment-{i}")).name or f"attachment-{i}"
            name = f"{i}-{basename}"
            encoded = item.get("data_base64")
            if not isinstance(encoded, str) or not encoded:
                raise BridgeRequestError(400, "each media item needs data_base64")
            data = _decode_media(encoded)
            total_media_bytes += len(data)
            if len(data) > MAX_MEDIA_BYTES:
                raise BridgeRequestError(413, "media item is too large")
            if total_media_bytes > MAX_TOTAL_MEDIA_BYTES:
                raise BridgeRequestError(413, "total media payload is too large")
            decoded_media.append((name, data))

        if not decoded_media:
            return task, None

        host_files: list[tuple[str, str]] = []
        media_run_dir = self.server.media_dir / uuid.uuid4().hex
        media_run_dir.mkdir(parents=True, exist_ok=True)
        for name, data in decoded_media:
            host_path = media_run_dir / name
            host_path.write_bytes(data)
            host_files.append((str(host_path), host_path.as_uri()))

        files = "\n".join(f"- {path}\n  file URL: {uri}" for path, uri in host_files)
        return (
            "NemoClaw attached these files on the host. They are the source of truth for this task:\n"
            f"{files}\n\n"
            "If the task depends on image or document contents, first open or preview one of the listed host file "
            "paths or file URLs and read that opened file. You may paste a file URL into the browser address bar to "
            "view the file directly. Ignore any already-visible receipt, image, browser tab, chat screenshot, or "
            "previous Preview window unless it is showing one of the listed file paths.\n\n"
            f"{task}"
        ), media_run_dir

    def _output(self, bridge_run: BridgeRun) -> dict[str, str]:
        if bridge_run.output is not None:
            return bridge_run.output
        return {
            "stdout": _tail_text(bridge_run.stdout_path),
            "stderr": _tail_text(bridge_run.stderr_path),
        }

    def _completed_payload(self, run_id: str, bridge_run: BridgeRun) -> dict[str, object]:
        returncode = bridge_run.returncode
        payload: dict[str, object] = {
            "ok": returncode == 0,
            "status": "completed" if returncode == 0 else "failed",
            "run_id": run_id,
            **self._output(bridge_run),
        }
        if returncode is not None:
            payload["returncode"] = returncode
        if returncode is None or returncode == RESTORED_EXIT_CODE_UNAVAILABLE:
            payload["message"] = "Holo process finished after bridge restart; exit code unavailable."
        return payload

    def _cleanup_run_files(self, bridge_run: BridgeRun) -> None:
        with contextlib.suppress(OSError):
            bridge_run.stdout_path.unlink()
        with contextlib.suppress(OSError):
            bridge_run.stderr_path.unlink()
        if bridge_run.media_dir is not None:
            shutil.rmtree(bridge_run.media_dir, ignore_errors=True)

    def _get_run(self, run_id: str) -> BridgeRun | None:
        with self.server._registry_lock:
            bridge_run = self.server.runs.get(run_id)
        if bridge_run is not None:
            return bridge_run
        bridge_run = self._load_run(run_id)
        if bridge_run is not None:
            self._store_run(run_id, bridge_run)
        return bridge_run

    def _store_run(self, run_id: str, bridge_run: BridgeRun) -> None:
        with self.server._registry_lock:
            self.server.runs[run_id] = bridge_run
        self._persist_run(run_id, bridge_run)

    def _run_lock(self, run_id: str) -> Lock:
        with self.server._registry_lock:
            lock = self.server._run_locks.get(run_id)
            if lock is None:
                lock = Lock()
                self.server._run_locks[run_id] = lock
            return lock

    def _persist_run(self, run_id: str, bridge_run: BridgeRun) -> None:
        self.server.runs_dir.mkdir(parents=True, exist_ok=True)
        metadata = BridgeRunMetadata(
            pid=bridge_run.pid,
            stdout_path=str(bridge_run.stdout_path),
            stderr_path=str(bridge_run.stderr_path),
            media_dir=str(bridge_run.media_dir) if bridge_run.media_dir is not None else None,
            returncode=bridge_run.returncode,
            finished_at=bridge_run.finished_at,
            output=RunOutput.model_validate(bridge_run.output) if bridge_run.output is not None else None,
        )
        atomic_write_json(self._run_metadata_path(run_id), metadata.model_dump(mode="json"))

    def _load_run(self, run_id: str) -> BridgeRun | None:
        try:
            text = self._run_metadata_path(run_id).read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            metadata = BridgeRunMetadata.model_validate_json(text)
        except ValidationError:
            return None
        return BridgeRun(
            process=None,
            pid=metadata.pid,
            stdout_path=Path(metadata.stdout_path),
            stderr_path=Path(metadata.stderr_path),
            media_dir=Path(metadata.media_dir) if metadata.media_dir is not None else None,
            returncode=metadata.returncode,
            finished_at=metadata.finished_at,
            output=metadata.output.model_dump() if metadata.output is not None else None,
        )

    def _run_metadata_path(self, run_id: str) -> Path:
        if not _is_run_id(run_id):
            raise BridgeRequestError(400, "run_id is invalid")
        return self.server.runs_dir / f"{run_id}.json"

    def _prune_completed_runs(self) -> None:
        now = time.time()
        self.server.runs_dir.mkdir(parents=True, exist_ok=True)
        for metadata_path in self.server.runs_dir.glob("*.json"):
            run_id = metadata_path.stem
            if not _is_run_id(run_id):
                continue
            bridge_run = self._load_run(run_id)
            if bridge_run is None or bridge_run.finished_at is None:
                continue
            if now - bridge_run.finished_at < COMPLETED_RUN_RETENTION_SECONDS:
                continue
            self._cleanup_run_files(bridge_run)
            with contextlib.suppress(OSError):
                metadata_path.unlink()
            with self.server._registry_lock:
                self.server.runs.pop(run_id, None)
                self.server._run_locks.pop(run_id, None)

    def _terminate_run(self, bridge_run: BridgeRun) -> None:
        if bridge_run.process is not None:
            returncode = bridge_run.process.poll()
            if returncode is not None:
                bridge_run.returncode = returncode
                return
            bridge_run.process.terminate()
            try:
                bridge_run.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                bridge_run.process.kill()
                bridge_run.process.wait(timeout=3)
            bridge_run.returncode = bridge_run.process.returncode
            return
        if bridge_run.pid is not None:
            _terminate_pid(bridge_run.pid)

    def _run_id_from_payload(self) -> str:
        run_id = self._read_payload().get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise BridgeRequestError(400, "run_id is required")
        run_id = run_id.strip()
        if not _is_run_id(run_id):
            raise BridgeRequestError(400, "run_id is invalid")
        return run_id

    def _read_payload(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise BridgeRequestError(400, "invalid Content-Length") from None
        if length > MAX_JSON_BODY_BYTES:
            raise BridgeRequestError(413, "request body is too large")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BridgeRequestError(400, "invalid JSON") from None
        if not isinstance(payload, dict):
            raise BridgeRequestError(400, "JSON body must be an object")
        return payload

    def _authorized(self) -> bool:
        expected = self.server.token
        header = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(header, f"Bearer {expected}")

    def _env(self) -> dict[str, str]:
        existing_path = os.environ.get("PATH", "")
        return {
            **os.environ,
            "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{existing_path}",
        }

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def bridge_server(
    host: Annotated[str, tyro.conf.arg(help="Host/interface to bind for the NemoClaw sandbox bridge.")] = DEFAULT_HOST,
    port: Annotated[int, tyro.conf.arg(help="Port the NemoClaw sandbox bridge listens on.")] = DEFAULT_PORT,
    token_file: Annotated[
        Path | None, tyro.conf.arg(help="File containing the bearer token required by the bridge.")
    ] = None,
) -> None:
    """Start the authenticated host bridge used by `holo install nemoclaw`."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token and token_file is not None:
        token = token_file.expanduser().read_text(encoding="utf-8").strip()
    if not token:
        print(
            f"No bridge token found. Set {TOKEN_ENV} or pass --token-file from `holo install nemoclaw`.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    bridge_root = HOLO_DIR / "nemoclaw"
    server = NemoClawBridgeServer(
        (host, port),
        NemoClawBridgeHandler,
        token=token,
        runs_dir=bridge_root / "runs",
        media_dir=bridge_root / "media",
    )
    server.serve_forever()


def _tail_text(path: Path) -> str:
    try:
        data = path.read_bytes()[-RUN_LOG_TAIL_CHARS:]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _decode_media(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error:
        raise BridgeRequestError(400, "media data_base64 is invalid") from None


def _is_run_id(value: str) -> bool:
    return len(value) == RUN_ID_LENGTH and all(char in RUN_ID_CHARS for char in value)


def _restored_returncode(pid: int | None) -> int | None:
    if pid is not None and _pid_running(pid):
        return None
    return RESTORED_EXIT_CODE_UNAVAILABLE


def _pid_running(pid: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return completed.returncode == 0 and str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
        return
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not _pid_running(pid):
            return
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    tyro.cli(bridge_server)
