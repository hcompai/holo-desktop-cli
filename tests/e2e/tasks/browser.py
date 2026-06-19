from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import _macos, _preserve
from .._domain import PreparedTask, TaskCase
from ..evaluators.browser import DownloadedFileEvaluator


class BrowserDownloadFile(TaskCase):
    """Task that asks Holo to download a local fixture file through the browser."""

    def prepare(self, workspace: Path) -> PreparedTask:
        filename = f"{_macos.unique_token('download')}.txt"
        content = f"download fixture {_macos.unique_token('download-content')}\n"
        target_path = Path.home() / "Downloads" / filename
        return prepare_browser_download_task(
            case=self,
            workspace=workspace,
            filename=filename,
            content=content,
            target_path=target_path,
            browser_name="Safari",
            command_line_warning="Terminal",
        )


def prepare_browser_download_task(
    *,
    case: TaskCase,
    workspace: Path,
    filename: str,
    content: str,
    target_path: Path,
    browser_name: str,
    command_line_warning: str,
) -> PreparedTask:
    server = _LocalDownloadServer(filename=filename, content=content)
    server.start()
    target_path.unlink(missing_ok=True)

    def cleanup() -> None:
        server.stop()
        target_path.unlink(missing_ok=True)

    def preserve(artifact_dir: Path) -> None:
        _preserve.copy_path(target_path, artifact_dir, name=target_path.name)

    instruction = (
        f"Open {browser_name} and go to {server.url!r}. Download the linked file named {filename!r}. "
        f"Leave the downloaded file in the default Downloads folder. Do not use {command_line_warning} "
        "or any command line tool. Then stop."
    )
    return PreparedTask(
        case=case,
        instruction=instruction,
        workspace=workspace,
        evaluator=DownloadedFileEvaluator(target_path, content),
        metadata={"url": server.url, "filename": filename, "download_path": str(target_path), "app": browser_name},
        cleanup=cleanup,
        preserve_artifacts=preserve,
    )


class _LocalDownloadServer:
    def __init__(self, *, filename: str, content: str) -> None:
        self.filename = filename
        self.content = content
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        filename = self.filename
        content = self.content

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/download":
                    payload = content.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                body = f"""
                    <!doctype html>
                    <html>
                      <head><title>Holo E2E Download</title></head>
                      <body>
                        <h1>Download Fixture</h1>
                        <a href="/download" download="{filename}">Download {filename}</a>
                      </body>
                    </html>
                    """.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


BROWSER_DOWNLOAD_FILE = BrowserDownloadFile(
    id="browser_download_file",
    intent="download a local browser fixture and leave it in the Downloads folder",
    app_family="browser",
    requires=frozenset({"browser", "filesystem", "local-http"}),
)
