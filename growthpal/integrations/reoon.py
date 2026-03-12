"""Reoon API client — email verification."""

from __future__ import annotations

import httpx

from growthpal.config import get_config
from growthpal.utils.logger import get_logger
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

BASE_URL = "https://emailverifier.reoon.com/api/v1"

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=20.0)
    return _http_client


@async_retry(max_retries=2, exceptions=(httpx.HTTPError,))
async def verify_email(
    email: str,
    api_key: str | None = None,
) -> dict:
    """Verify an email address using Reoon.

    Returns:
        Dict with 'valid', 'status', 'confidence' keys.
        status: 'valid', 'invalid', 'risky', 'unknown'
    """
    key = api_key or get_config().reoon_api_key
    if not key:
        return {"valid": None, "status": "unknown", "provider": "reoon"}

    client = _get_client()
    response = await client.get(
        f"{BASE_URL}/verify",
        params={"email": email, "key": key, "mode": "quick"},
    )
    response.raise_for_status()
    data = response.json()

    status = data.get("status", "unknown").lower()
    is_valid = status == "valid"
    is_risky = status in ("risky", "accept_all", "unknown")

    log.debug(f"[reoon] {email} → {status}")

    return {
        "valid": is_valid,
        "risky": is_risky,
        "status": status,
        "confident": status in ("valid", "invalid"),  # True if Reoon is sure
        "provider": "reoon",
        "details": data,
    }
