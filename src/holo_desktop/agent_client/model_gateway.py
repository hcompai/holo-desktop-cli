"""Live model-gateway entitlement probe."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import httpx

from holo_desktop.settings import GatewaySettings

# This base URL is itself the OpenAI `/v1/models` route, so a GET with the key doubles as an entitlement check.
PRODUCTION_GATEWAY_URL = "https://api.hcompany.ai/v1/models"
GATEWAY_PROBE_TIMEOUT_S = 10.0

GatewayAccess = Literal["entitled", "unauthorized", "unverifiable"]


def resolve_gateway_url(environ: Mapping[str, str]) -> str:
    """Gateway the login entitlement probe targets: a `HAI_BASE_URL` regional override, else production."""
    return GatewaySettings.model_validate(environ).base_url or PRODUCTION_GATEWAY_URL


def probe_model_access(gateway_url: str, api_key: str, timeout_s: float) -> GatewayAccess:
    """GET the gateway model-list with `api_key`; classify entitled / unauthorized / unverifiable."""
    try:
        response = httpx.get(gateway_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout_s)
    except httpx.HTTPError:
        return "unverifiable"
    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        return "unauthorized"
    if response.status_code == httpx.codes.OK:
        return "entitled"
    return "unverifiable"
