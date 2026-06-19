"""`holo login`: portal sign-in via RFC 8252 loopback + PKCE."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import platform
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Annotated, Any

import httpx
import tyro

from holo_desktop.agent_client.model_gateway import (
    GATEWAY_PROBE_TIMEOUT_S,
    probe_model_access,
    resolve_gateway_url,
)
from holo_desktop.cli.bootstrap import USER_ENV_PATH, load_holo_env, read_user_env_key, save_hai_key
from holo_desktop.cli.login_pages import ERROR_HTML, SUCCESS_HTML
from holo_desktop.cli.profile import Profile, load_profile, save_profile
from holo_desktop.settings import HoloSettings, load_holo_settings

if TYPE_CHECKING:
    from rich.console import Console

# EU portal: US portal mints keys the model gateway rejects with 401.
PORTAL_BASE = "https://portal.api.eu.hcompany.ai"
SIGN_IN_TIMEOUT_S = 180


class _LoopbackServer(HTTPServer):
    """HTTPServer + slots for the one-shot OAuth callback payload."""

    captured_code: str | None = None
    captured_error: tuple[str, str | None] | None = None
    expected_state: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot loopback; stashes `?code=...` or `?error=...` on the server."""

    server: _LoopbackServer

    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        state = params.get("state", [None])[0]
        if code:
            # Lenient: reject only a returned state that disagrees, so a portal that omits state still works.
            if state is not None and state != self.server.expected_state:
                self.server.captured_error = ("invalid_state", "state parameter did not match")
                self._respond(400, ERROR_HTML)
                return
            self.server.captured_code = code
            self._respond(200, SUCCESS_HTML)
        elif error:
            self.server.captured_error = (error, params.get("error_description", [None])[0])
            self._respond(400, ERROR_HTML)
        else:
            # Drive-by request (favicon, extension probe): drain and wait for the real callback.
            self.send_response(404)
            self.end_headers()

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object, **__: object) -> None:
        return


def _pkce_pair() -> tuple[str, str]:
    """RFC 7636 S256: 43-char URL-safe verifier, base64url(SHA-256(verifier)) challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _key_label() -> str:
    """Per-machine Portal key name, e.g. ``HoloDesktop CLI (hostname)``."""
    host = platform.node().split(".", 1)[0] or "device"
    return f"HoloDesktop CLI ({host})"


def _await_code(challenge: str, state: str, err: Console) -> tuple[str, str]:
    """Bind loopback, open browser, return (code, redirect_uri). Exits on error or timeout."""
    with _LoopbackServer(("127.0.0.1", 0), _CallbackHandler) as server:
        server.timeout = 1.0
        server.expected_state = state
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}/"
        authorize_url = (
            f"{PORTAL_BASE}/api/auth/authorize"
            f"?provider=google"
            f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
            f"&state={state}"
        )

        err.print(f"Opening [cyan]{PORTAL_BASE}[/cyan] in your browser...")
        if not webbrowser.open(authorize_url):
            err.print(f"  (couldn't open browser; paste this URL: {authorize_url})")

        deadline = time.monotonic() + SIGN_IN_TIMEOUT_S
        while server.captured_code is None:
            if server.captured_error is not None:
                code, desc = server.captured_error
                detail = f": {desc}" if desc else ""
                err.print(f"[red]x[/red] sign-in failed ({code}){detail}.")
                sys.exit(1)
            if time.monotonic() > deadline:
                err.print("[red]x[/red] timed out after 3 minutes.")
                sys.exit(1)
            server.handle_request()
        return server.captured_code, redirect_uri


def _portal_get(client: httpx.Client, path: str) -> Any:  # Any: portal JSON shape varies per endpoint
    r = client.get(f"{PORTAL_BASE}{path}")
    r.raise_for_status()
    return r.json()


def _is_key_name_collision(exc: httpx.HTTPStatusError) -> bool:
    """Portal returns 400 + `api_key_name_already_exists` when a key with the same name already lives in the org."""
    return exc.response.status_code == 400 and "api_key_name_already_exists" in exc.response.text


def _mint_key_resilient(client: httpx.Client, org_id: str, label: str) -> dict[str, Any]:  # Any: portal key JSON
    """Mint a key; on a name collision, reclaim the stale per-machine key (list-by-name + delete + remint, one round)."""
    keys_url = f"{PORTAL_BASE}/api/organizations/{org_id}/keys/"
    try:
        r = client.post(keys_url, json={"name": label})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        if not _is_key_name_collision(exc):
            raise
    keys = _portal_get(client, f"/api/organizations/{org_id}/keys/")
    stale = next((k for k in keys if k.get("name") == label), None)
    if stale is None:
        raise RuntimeError(f"key {label!r} flagged as duplicate but absent from list response")
    deleted = client.delete(f"{keys_url}{stale['id']}")
    if deleted.status_code != 404:
        deleted.raise_for_status()
    r = client.post(keys_url, json={"name": label})
    r.raise_for_status()
    return r.json()


def _format_http_error(exc: httpx.HTTPError) -> str:
    """Status + URL only; never echo response bodies (may contain server-side detail)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{exc.response.status_code} from {exc.request.url}"
    return str(exc)


def _delete_key_by_id(client: httpx.Client, org_id: str, key_id: str) -> None:
    """Best-effort revoke of a known per-machine key; tolerated 404 means it's already gone."""
    if not key_id:
        return
    with contextlib.suppress(httpx.HTTPError):
        r = client.delete(f"{PORTAL_BASE}/api/organizations/{org_id}/keys/{key_id}")
        if r.status_code != 404:
            r.raise_for_status()


def _is_h_company_host(host: str) -> bool:
    return host == "hcompany.ai" or host.endswith(".hcompany.ai")


def _verify_model_access(key: str, err: Console, *, settings: HoloSettings) -> None:
    """Exit non-zero when the gateway denies the (already-saved) key: a portal key can authenticate yet lack Holo3 access (401)."""
    if settings.runtime.base_url:
        return  # self-hosted inference: the portal key is not used against the gateway
    gateway_url = resolve_gateway_url(os.environ)
    host = urllib.parse.urlparse(gateway_url).hostname or ""
    if not _is_h_company_host(host):
        err.print(
            f"[yellow]![/yellow] skipping model-access check: gateway [cyan]{host or gateway_url}[/cyan] is not an H Company endpoint."
        )
        return
    if probe_model_access(gateway_url, key, GATEWAY_PROBE_TIMEOUT_S) == "unauthorized":
        err.print("[red]x[/red] signed in, but this key has no Holo3 model access (gateway rejected it).")
        err.print("  The key is saved; your org likely lacks model entitlement. Contact the H Company portal team.")
        sys.exit(1)


def login(
    force: Annotated[bool, tyro.conf.arg(help="Re-OAuth and rotate the per-machine key.")] = False,
) -> None:
    """Sign in to H Company. No-op if already signed in; pass --force to rotate the key or switch identities."""
    from rich.console import Console

    err = Console(stderr=True)
    # Layered env (process > ~/.holo/.env > cwd .env) so base-url overrides reach the gateway probe.
    load_holo_env()
    settings = load_holo_settings()

    if not force:
        existing_key = read_user_env_key()
        existing_profile = load_profile()
        if existing_key and existing_profile:
            suffix = f" / org [bold]{existing_profile.org_name}[/bold]" if existing_profile.org_name else ""
            err.print(f"[green]ok[/green] already signed in as [bold]{existing_profile.email}[/bold]{suffix}")
            err.print(f"  HAI_API_KEY at [cyan]{USER_ENV_PATH}[/cyan]")
            err.print("  Run [cyan]holo login --force[/cyan] to rotate the key or switch identities.")
            return

    try:
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(32)
        code, redirect_uri = _await_code(challenge, state, err)

        with httpx.Client(timeout=20.0) as client:
            tok = client.post(
                f"{PORTAL_BASE}/api/auth/desktop/exchange",
                json={"code": code, "code_verifier": verifier, "redirect_uri": redirect_uri},
            )
            tok.raise_for_status()
            jwt = tok.json()["access_token"]
            client.headers["Authorization"] = f"Bearer {jwt}"

            me = _portal_get(client, "/api/auth/me")
            user = me.get("user") or {}
            email = user.get("email")
            org_id = me.get("org_id") or (me.get("organization") or {}).get("id")
            org_name = (me.get("organization") or {}).get("name")
            if not org_id:
                owned = _portal_get(client, "/api/organizations/owned")
                if not owned:
                    err.print("[red]x[/red] no organization to mint a key against.")
                    sys.exit(1)
                org_id = owned[0]["id"]
                org_name = org_name or owned[0].get("name")

            if not email:
                err.print("[red]x[/red] portal did not return an email for this user.")
                sys.exit(1)

            # Drop the prior per-machine key if profile still points at it in this org.
            prev = load_profile()
            if prev is not None and prev.org_id == org_id:
                _delete_key_by_id(client, org_id, prev.key_id)

            label = _key_label()
            minted_body = _mint_key_resilient(client, org_id, label)
            key = minted_body["key"]
            key_id = minted_body.get("id") or ""
    except KeyboardInterrupt:
        err.print()
        err.print("[yellow]cancelled[/yellow].")
        sys.exit(130)
    except (httpx.HTTPError, KeyError, RuntimeError) as exc:
        if isinstance(exc, httpx.HTTPError):
            msg = _format_http_error(exc)
        elif isinstance(exc, KeyError):
            msg = f"missing field {exc}"
        else:
            msg = str(exc)
        err.print(f"[red]x[/red] portal sign-in failed: {msg}")
        sys.exit(1)

    # Persist before the entitlement gate: minting revoked the prior key, so don't strand ~/.holo/.env on a dead secret.
    save_hai_key(key)
    save_profile(
        Profile(
            email=email,
            org_id=org_id,
            key_id=key_id,
            key_label=label,
            org_name=org_name,
        )
    )

    _verify_model_access(key, err, settings=settings)

    err.print()
    suffix = f" / org [bold]{org_name}[/bold]" if org_name else ""
    err.print(f"[green]ok[/green] signed in as [bold]{email}[/bold]{suffix}")
    err.print(f"  HAI_API_KEY saved to [cyan]{USER_ENV_PATH}[/cyan]")
