"""hai-agent-runtime stand-ins that prove their identity like the real binary; run as a script for a healthy stub."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from hai_agents_local.runtime.identity import CHALLENGE_HEADER, PROOF_HEADER

SCRIPT = os.path.abspath(__file__)


class ProvingHandler(BaseHTTPRequestHandler):
    """Answers each request's challenge with an HMAC keyed by ``token``."""

    token = ""

    def end_headers(self) -> None:
        challenge = self.headers.get(CHALLENGE_HEADER, "")
        self.send_header(PROOF_HEADER, hmac.new(self.token.encode(), challenge.encode(), hashlib.sha256).hexdigest())
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


class _HealthyHandler(ProvingHandler):
    def do_GET(self) -> None:
        body = json.dumps({"status": "ok", "recipe": os.environ.get("HAI_AGENT_RUNTIME_RECIPE", "shared")}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    _HealthyHandler.token = os.environ["HAI_AGENT_RUNTIME_API_TOKEN"]
    HTTPServer(("127.0.0.1", int(os.environ["HAI_AGENT_RUNTIME_PORT"])), _HealthyHandler).serve_forever()
