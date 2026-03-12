"""TryKitt API client — email finding."""

from __future__ import annotations

import httpx

from leadflow.config import get_config
from leadflow.utils.logger import get_logger
from leadflow.utils.retry import async_retry

log = get_logger(__name__)

BASE_URL = "https://app.trykitt.ai/api"

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=20.0)
    return _http_client


@async_retry(max_retries=2, exceptions=(httpx.HTTPError,))
async def find_email(
    first_name: str,
    last_name: str,
    domain: str,
    api_key: str | None = None,
) -> dict:
    """Find email address using TryKitt.

    Returns:
        Dict with 'email', 'confidence', 'found' keys.
    """
    key = api_key or get_config().trykitt_api_key
    if not key:
        return {"found": False, "email": None, "provider": "trykitt"}

    client = _get_client()
    response = await client.post(
        f"{BASE_URL}/v1/email-finder",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "domain": domain,
        },
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    email = data.get("email") or data.get("data", {}).get("email")
    confidence = data.get("confidence", 0) or data.get("data", {}).get("confidence", 0)

    if email:
        log.debug(f"[trykitt] Found {email} (confidence: {confidence})")
        return {
            "found": True,
            "email": email,
            "confidence": confidence,
            "provider": "trykitt",
        }

    return {"found": False, "email": None, "provider": "trykitt"}
