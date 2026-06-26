"""`holo retina-proxy`: fix HiDPI click-coordinate mismatch on Retina displays."""

from __future__ import annotations

from typing import Annotated

import tyro


def retina_proxy(
    host: Annotated[str, tyro.conf.arg(help="Address to bind to.")] = "127.0.0.1",
    port: Annotated[int, tyro.conf.arg(help="Port to listen on.")] = 8001,
    upstream: Annotated[
        str,
        tyro.conf.arg(help="Upstream OpenAI-compatible model server URL."),
    ] = "http://localhost:8000",
    scale: Annotated[
        float | None,
        tyro.conf.arg(
            help=(
                "HiDPI backing scale factor (images are divided by this value). "
                "Auto-detected from NSScreen when omitted (macOS only); "
                "pass --scale 2 explicitly if auto-detection fails."
            )
        ),
    ] = None,
) -> None:
    """
    Start a transparent OpenAI-compatible proxy that downscales Retina screenshots
    to the logical screen resolution before forwarding them to the model server.

    On macOS HiDPI displays the hai-agent-runtime captures screenshots at the
    physical pixel size (e.g. 3024 × 1964) but drives the desktop with pyautogui's
    logical coordinates (e.g. 1512 × 982).  Because the runtime uses the received
    image dimensions to map model coordinates back to screen positions, every click
    lands at roughly 2× the intended position.

    This proxy fixes that by halving the embedded screenshots before the model ever
    sees them.  Point holo at the proxy with --base-url or HAI_AGENT_RUNTIME_BASE_URL:

        holo retina-proxy &
        holo run --base-url http://localhost:8001/v1 "your task"
    """
    from holo_desktop.retina_proxy import serve

    serve(host=host, port=port, upstream=upstream, scale=scale)
