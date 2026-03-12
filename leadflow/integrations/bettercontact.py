"""BetterContact API client — email + phone enrichment (self-verifying)."""

from __future__ import annotations

import asyncio

import httpx

from leadflow.config import get_config
from leadflow.utils.logger import get_logger
from leadflow.utils.retry import async_retry

log = get_logger(__name__)

BASE_URL = "https://app.bettercontact.rocks/api"

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


@async_retry(max_retries=2, exceptions=(httpx.HTTPError,))
async def find_email(
    first_name: str,
    last_name: str,
    domain: str,
    linkedin_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Find and verify email using BetterContact.

    BetterContact self-verifies, so no need for separate verification.

    Returns:
        Dict with 'email', 'phone', 'verified', 'found' keys.
    """
    key = api_key or get_config().bettercontact_api_key
    if not key:
        return {"found": False, "email": None, "provider": "bettercontact"}

    client = _get_client()

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "company_domain": domain,
    }
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url

    # BetterContact is async — submit then poll for result
    response = await client.post(
        f"{BASE_URL}/v1/enrich",
        json=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    # If result is immediate
    email = _extract_email(data)
    if email:
        return _build_result(data, email)

    # If async — poll for result
    request_id = data.get("id") or data.get("request_id")
    if request_id:
        return await _poll_result(client, key, request_id)

    return {"found": False, "email": None, "provider": "bettercontact"}


async def _poll_result(client: httpx.AsyncClient, api_key: str, request_id: str) -> dict:
    """Poll BetterContact for async enrichment result."""
    for _ in range(10):  # Max 10 attempts, ~30 seconds
        await asyncio.sleep(3)

        response = await client.get(
            f"{BASE_URL}/v1/enrich/{request_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        if response.status_code == 202:
            continue  # Still processing

        response.raise_for_status()
        data = response.json()

        email = _extract_email(data)
        if email:
            return _build_result(data, email)

        status = data.get("status", "")
        if status in ("completed", "failed", "not_found"):
            break

    return {"found": False, "email": None, "provider": "bettercontact"}


def _extract_email(data: dict) -> str | None:
    """Extract email from various BetterContact response formats."""
    return (
        data.get("email")
        or data.get("data", {}).get("email")
        or data.get("result", {}).get("email")
    )


def _build_result(data: dict, email: str) -> dict:
    """Build standardized result dict."""
    phone = (
        data.get("phone")
        or data.get("data", {}).get("phone")
        or data.get("result", {}).get("phone")
    )

    log.debug(f"[bettercontact] Found {email}" + (f" + phone {phone}" if phone else ""))

    return {
        "found": True,
        "email": email,
        "phone": phone,
        "verified": True,  # BetterContact self-verifies
        "provider": "bettercontact",
    }
