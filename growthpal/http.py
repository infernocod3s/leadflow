"""Shared HTTP client — single connection pool for all modules.

All modules should import `get_http_client()` from here instead of
creating their own httpx.AsyncClient instances.
"""

from __future__ import annotations

import httpx

_http_client: httpx.AsyncClient | None = None

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient singleton.

    Pool: 2000 max connections, 500 keepalive.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            limits=httpx.Limits(
                max_connections=2000,
                max_keepalive_connections=500,
            ),
        )
    return _http_client


async def close_http_client() -> None:
    """Gracefully close the shared HTTP client. Call on shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
