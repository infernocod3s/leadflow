"""Website scraper using httpx + BeautifulSoup."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from leadflow.utils.logger import get_logger
from leadflow.utils.retry import async_retry

log = get_logger(__name__)

_http_client: httpx.AsyncClient | None = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=15.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
    return _http_client


def _extract_text(html: str, max_length: int = 8000) -> str:
    """Extract readable text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    return text[:max_length]


@async_retry(max_retries=2, exceptions=(httpx.HTTPError, httpx.TimeoutException))
async def scrape_website(url: str) -> str:
    """Scrape a website and return cleaned text content.

    Args:
        url: Website URL (with or without https://)

    Returns:
        Cleaned text content from the page.
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    client = _get_http_client()
    response = await client.get(url)
    response.raise_for_status()

    return _extract_text(response.text)


async def scrape_multiple_pages(base_url: str, paths: list[str] | None = None) -> str:
    """Scrape multiple pages from a website and combine content.

    Default paths: /, /about, /product (or /products)
    """
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    base_url = base_url.rstrip("/")
    paths = paths or ["/", "/about", "/products"]

    all_text = []
    for path in paths:
        try:
            text = await scrape_website(f"{base_url}{path}")
            if text:
                all_text.append(f"--- {path} ---\n{text}")
        except Exception:
            continue  # Skip pages that fail

    return "\n\n".join(all_text) if all_text else ""
