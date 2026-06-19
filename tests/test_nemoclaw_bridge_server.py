"""Tests for the NemoClaw host bridge request boundary."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from urllib import error, request

import pytest

from holo_desktop.host_integrations.nemoclaw import bridge_server as bridge_mod
from holo_desktop.host_integrations.nemoclaw.bridge_server import BridgeRun, NemoClawBridgeHandler, NemoClawBridgeServer


@contextmanager
def _bridge_server(tmp_path: Path) -> Iterator[tuple[str, NemoClawBridgeServer]]:
    server = NemoClawBridgeServer(
        ("127.0.0.1", 0),
        NemoClawBridgeHandler,
        token="secret",
        runs_dir=tmp_path / "runs",
        media_dir=tmp_path / "media",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


@contextmanager
def _bridge_handler(tmp_path: Path) -> Iterator[NemoClawBridgeHandler]:
    server = NemoClawBridgeServer(
        ("127.0.0.1", 0),
        NemoClawBridgeHandler,
        token="secret",
        runs_dir=tmp_path / "runs",
        media_dir=tmp_path / "media",
    )
    handler = object.__new__(NemoClawBridgeHandler)
    handler.server = server
    try:
        yield handler
    finally:
        server.server_close()


def _post(base_url: str, path: str, payload: bytes | dict[str, object]) -> tuple[int, dict[str, object]]:
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}{path}",
        data=data,
        method="POST",
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=5.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_bridge_default_host_is_loopback() -> None:
    assert bridge_mod.DEFAULT_HOST == "127.0.0.1"


def test_bridge_rejects_invalid_json(tmp_path: Path) -> None:
    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/launch", b"{")

    assert status == 400
    assert body["error"] == "invalid JSON"


def test_bridge_rejects_oversized_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "MAX_JSON_BODY_BYTES", 4)

    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/launch", {"task": "hello"})

    assert status == 413
    assert body["error"] == "request body is too large"


def test_bridge_rejects_invalid_media_base64(tmp_path: Path) -> None:
    payload = {"task": "submit this receipt", "media": [{"name": "receipt.png", "data_base64": "not base64!"}]}

    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/launch", payload)

    assert status == 400
    assert body["error"] == "media data_base64 is invalid"


def test_bridge_rejects_oversized_media_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "MAX_MEDIA_BYTES", 3)
    payload = {
        "task": "submit this receipt",
        "media": [{"name": "receipt.png", "data_base64": base64.b64encode(b"1234").decode("ascii")}],
    }

    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/launch", payload)

    assert status == 413
    assert body["error"] == "media item is too large"


def test_bridge_rejects_missing_run_id(tmp_path: Path) -> None:
    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/poll", {})

    assert status == 400
    assert body["error"] == "run_id is required"


def test_bridge_rejects_run_id_path_traversal(tmp_path: Path) -> None:
    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/poll", {"run_id": "../outside"})

    assert status == 400
    assert body["error"] == "run_id is invalid"
    assert not (tmp_path / "outside.json").exists()


def test_bridge_launch_returns_json_when_holo_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_resolve_holo_command(*, path: str | None = None) -> str:
        raise RuntimeError("missing holo")

    monkeypatch.setattr(bridge_mod, "resolve_holo_command", fail_resolve_holo_command)

    with _bridge_server(tmp_path) as (base_url, _):
        status, body = _post(base_url, "/launch", {"task": "hello"})

    assert status == 500
    assert body["ok"] is False
    assert body["error"] == "launch failed: missing holo"
    assert not (tmp_path / "runs").exists()


def test_bridge_launch_resolves_holo_against_child_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen: dict[str, str | None] = {}

    def fake_resolve_holo_command(*, path: str | None = None) -> str:
        seen["path"] = path
        return sys.executable

    with _bridge_handler(tmp_path) as handler:
        monkeypatch.setattr(bridge_mod, "resolve_holo_command", fake_resolve_holo_command)
        monkeypatch.setattr(handler, "_read_payload", lambda: {"task": "hello"})
        monkeypatch.setattr(handler, "_env", lambda: {"PATH": str(bin_dir)})

        _, bridge_run = handler._start_holo_run()

    assert bridge_run is not None
    assert bridge_run.process is not None
    bridge_run.process.wait(timeout=5.0)
    assert seen["path"] == str(bin_dir)


def test_bridge_launch_resolves_holo_before_opening_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_resolve_holo_command(*, path: str | None = None) -> str:
        raise RuntimeError("missing holo")

    with _bridge_handler(tmp_path) as handler:
        monkeypatch.setattr(bridge_mod, "resolve_holo_command", fail_resolve_holo_command)
        monkeypatch.setattr(handler, "_read_payload", lambda: {"task": "hello"})

        with pytest.raises(RuntimeError, match="missing holo"):
            handler._start_holo_run()

    assert not (tmp_path / "runs").exists()


def test_bridge_repeated_completed_poll_returns_cached_output(tmp_path: Path) -> None:
    run_id = "a" * bridge_mod.RUN_ID_LENGTH

    with _bridge_server(tmp_path) as (base_url, server):
        server.runs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = server.runs_dir / f"{run_id}.stdout.log"
        stderr_path = server.runs_dir / f"{run_id}.stderr.log"
        stdout_file = stdout_path.open("wb")
        stderr_file = stderr_path.open("wb")
        process = subprocess.Popen(
            [sys.executable, "-c", "print('done from holo')"],
            stdout=stdout_file,
            stderr=stderr_file,
        )
        stdout_file.close()
        stderr_file.close()
        server.runs[run_id] = BridgeRun(
            process=process,
            pid=process.pid,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

        first_status, first_body = _post(base_url, "/poll", {"run_id": run_id})
        second_status, second_body = _post(base_url, "/poll", {"run_id": run_id})

    assert first_status == 200
    assert first_body["status"] == "completed"
    assert "done from holo" in str(first_body["stdout"])
    assert second_status == 200
    assert second_body["status"] == "completed"
    assert second_body["stdout"] == first_body["stdout"]


def test_bridge_poll_recovers_persisted_run_output(tmp_path: Path) -> None:
    run_id = "b" * bridge_mod.RUN_ID_LENGTH

    with _bridge_server(tmp_path) as (base_url, server):
        server.runs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = server.runs_dir / f"{run_id}.stdout.log"
        stderr_path = server.runs_dir / f"{run_id}.stderr.log"
        stdout_path.write_text("restored output", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        (server.runs_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "pid": None,
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "media_dir": None,
                    "returncode": None,
                    "finished_at": None,
                    "output": None,
                }
            ),
            encoding="utf-8",
        )

        status, body = _post(base_url, "/poll", {"run_id": run_id})

    assert status == 200
    assert body["ok"] is False
    assert body["status"] == "failed"
    assert body["returncode"] == bridge_mod.RESTORED_EXIT_CODE_UNAVAILABLE
    assert body["stdout"] == "restored output"
    assert "exit code unavailable" in str(body["message"])


def test_bridge_marks_attached_files_as_source_of_truth(tmp_path: Path) -> None:
    handler = object.__new__(NemoClawBridgeHandler)
    handler.server = type("Server", (), {"media_dir": tmp_path / "media"})()

    task, media_dir = handler._task_with_media(
        "Submit the expense form.",
        [{"name": "receipt.png", "data_base64": base64.b64encode(b"receipt").decode("ascii")}],
    )

    assert media_dir is not None
    assert "source of truth" in task
    assert "file URL: file://" in task
    assert "browser address bar" in task
    assert "Ignore any already-visible receipt" in task
    assert "Submit the expense form." in task


def test_bridge_prefixes_duplicate_attachment_names(tmp_path: Path) -> None:
    handler = object.__new__(NemoClawBridgeHandler)
    handler.server = type("Server", (), {"media_dir": tmp_path / "media"})()

    _, media_dir = handler._task_with_media(
        "Use both files.",
        [
            {"name": "receipt.png", "data_base64": base64.b64encode(b"first").decode("ascii")},
            {"name": "receipt.png", "data_base64": base64.b64encode(b"second").decode("ascii")},
        ],
    )

    assert media_dir is not None
    files = sorted(path.name for path in media_dir.iterdir())
    assert files == ["0-receipt.png", "1-receipt.png"]
    assert (media_dir / "0-receipt.png").read_bytes() == b"first"
    assert (media_dir / "1-receipt.png").read_bytes() == b"second"
