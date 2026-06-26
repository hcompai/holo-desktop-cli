"""
Transparent OpenAI-compatible proxy that downscales Retina screenshots before
forwarding to the model server.

Background
----------
On macOS HiDPI (Retina) displays, ``pyautogui`` captures screenshots at the
*physical* pixel resolution (e.g. 3024 × 1964) but accepts click coordinates
in the *logical* resolution (e.g. 1512 × 982).  The ``hai-agent-runtime``
converts normalised model coordinates back to screen positions using the
dimensions of the image it received from the model server — so when the model
saw a 3024 × 1964 image it computes click targets in that larger space, passes
them to ``pyautogui``, and every click lands at roughly 2× the intended
position (off-screen or at screen edges for most targets).

This proxy sits between ``holo`` (via ``--base-url``) and the model server
(e.g. ``llama-server``).  It intercepts ``/v1/chat/completions`` requests,
rescales any embedded ``data:image/…`` base64 images down by the display's
backing scale factor (typically 2× on Retina), then forwards the modified
request to the real model server.  The model sees a logical-resolution image
and returns coordinates in that space; the runtime's coordinate conversion then
produces the correct ``pyautogui`` click positions.

Usage
-----
Start the proxy (default: listens on 8001, forwards to 8000)::

    uv run holo retina-proxy

Then point ``holo`` at the proxy instead of the model server::

    uv run holo run --base-url http://localhost:8001/v1 "your task"

Or set it permanently::

    export HAI_AGENT_RUNTIME_BASE_URL=http://localhost:8001/v1
"""

from __future__ import annotations

import base64
import io
import json
import logging
import sys
from typing import AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from PIL import Image

logger = logging.getLogger(__name__)


def _backing_scale_factor() -> float:
    """Return the main display's HiDPI backing scale factor (2.0 on Retina, 1.0 elsewhere)."""
    if sys.platform != "darwin":
        return 1.0
    try:
        from AppKit import NSScreen  # type: ignore[import-not-found]

        return float(NSScreen.mainScreen().backingScaleFactor())
    except Exception:
        logger.debug("Could not read NSScreen backing scale factor; defaulting to 1.0", exc_info=True)
        return 1.0


def _resize_data_url(data_url: str, scale: float) -> str:
    """
    Decode a ``data:image/…;base64,…`` URL, downscale the image by *1/scale*,
    and return the re-encoded data URL.  Leaves the string unchanged if it is
    not a data URL or if *scale* ≤ 1.
    """
    if scale <= 1.0 or not data_url.startswith("data:image/"):
        return data_url

    header, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)

    img = Image.open(io.BytesIO(raw))
    new_w = max(1, round(img.width / scale))
    new_h = max(1, round(img.height / scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    # Preserve original format where possible, fall back to JPEG for photos.
    fmt = img.format or ("PNG" if "png" in header else "JPEG")
    img.save(buf, format=fmt)
    resized_encoded = base64.b64encode(buf.getvalue()).decode()

    mime = header.split(";")[0].split(":")[1]
    return f"data:{mime};base64,{resized_encoded}"


def _patch_messages(messages: list, scale: float) -> list:
    """Walk OpenAI message content and downscale any embedded images."""
    patched = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            patched.append(msg)
            continue
        new_content = []
        for part in content:
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                new_url = _resize_data_url(url, scale)
                if new_url is not url:
                    part = {**part, "image_url": {**part["image_url"], "url": new_url}}
                    logger.debug("Downscaled image by 1/%.1f", scale)
            new_content.append(part)
        patched.append({**msg, "content": new_content})
    return patched


def build_app(upstream: str, scale: float) -> FastAPI:
    """Return a FastAPI app that proxies to *upstream*, downscaling images by *1/scale*."""
    app = FastAPI(title="holo-retina-proxy", docs_url=None, redoc_url=None)
    client = httpx.AsyncClient(base_url=upstream, timeout=600.0)

    @app.on_event("startup")
    async def _startup() -> None:
        logger.info("retina-proxy: backing scale %.1f, upstream %s", scale, upstream)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await client.aclose()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(request: Request, path: str) -> Response:
        body = await request.body()

        # Only patch chat completions requests that carry images.
        if path in ("v1/chat/completions", "chat/completions") and scale > 1.0:
            try:
                payload = json.loads(body)
                if "messages" in payload:
                    payload["messages"] = _patch_messages(payload["messages"], scale)
                    body = json.dumps(payload).encode()
            except Exception:
                logger.debug("Could not parse chat/completions body; forwarding as-is", exc_info=True)

        # Strip hop-by-hop headers that must not be forwarded.
        forward_headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "transfer-encoding", "connection", "content-length")
        }

        upstream_req = client.build_request(
            method=request.method,
            url=path,
            params=request.query_params,
            headers=forward_headers,
            content=body,
        )
        upstream_resp = await client.send(upstream_req, stream=True)

        # Stream the response back to the caller.
        async def _stream() -> AsyncIterator[bytes]:
            async for chunk in upstream_resp.aiter_bytes():
                yield chunk
            await upstream_resp.aclose()

        response_headers = {
            k: v
            for k, v in upstream_resp.headers.items()
            if k.lower() not in ("transfer-encoding", "connection", "content-length")
        }
        return StreamingResponse(
            _stream(),
            status_code=upstream_resp.status_code,
            headers=response_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )

    return app


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
    upstream: str = "http://localhost:8000",
    scale: float | None = None,
    log_level: str = "info",
) -> None:
    """
    Start the retina proxy server.

    Args:
        host: Address to bind to (default: 127.0.0.1).
        port: Port to listen on (default: 8001).
        upstream: Upstream OpenAI-compatible server URL (default: http://localhost:8000).
        scale: HiDPI scale factor to divide image dimensions by.
               Auto-detected from NSScreen if not provided (macOS only).
        log_level: Uvicorn log level (default: info).
    """
    if scale is None:
        scale = _backing_scale_factor()
        if scale <= 1.0:
            logger.warning(
                "retina-proxy: scale factor is %.1f — no images will be resized. "
                "Pass --scale 2 explicitly if auto-detection failed.",
                scale,
            )
    app = build_app(upstream=upstream, scale=scale)
    uvicorn.run(app, host=host, port=port, log_level=log_level)
