"""BounceBan API client — email verification (fallback after Reoon)."""

from __future__ import annotations

import httpx

from leadflow.config import get_config
from leadflow.utils.logger import get_logger
from leadflow.utils.retry import async_retry

log = get_logger(__name__)

BASE_URL = "https://api.bounceban.com/v1"

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
    """Verify an email address using BounceBan.

    Used as fallback when Reoon returns uncertain results.

    Returns:
        Dict with 'valid', 'status' keys.
    """
    key = api_key or get_config().bounceban_api_key
    if not key:
        return {"valid": None, "status": "unknown", "provider": "bounceban"}

    client = _get_client()
    response = await client.get(
        f"{BASE_URL}/verify",
        params={"email": email, "apikey": key},
    )
    response.raise_for_status()
    data = response.json()

    status = data.get("status", "unknown").lower()
    result = data.get("result", "unknown").lower()

    # Normalize to valid/invalid/risky
    is_valid = result in ("deliverable", "valid") or status in ("deliverable", "valid")

    log.debug(f"[bounceban] {email} → {result}")

    return {
        "valid": is_valid,
        "status": result or status,
        "provider": "bounceban",
        "details": data,
    }
