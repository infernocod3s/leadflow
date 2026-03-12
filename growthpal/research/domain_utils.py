"""Domain normalization and URL utilities."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_domain(url_or_domain: str) -> str:
    """Extract and normalize domain from a URL or domain string.

    Examples:
        normalize_domain("https://www.stripe.com/pricing") -> "stripe.com"
        normalize_domain("stripe.com") -> "stripe.com"
        normalize_domain("www.stripe.com") -> "stripe.com"
    """
    url = url_or_domain.strip().lower()

    # Add scheme if missing for urlparse to work
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    domain = parsed.hostname or parsed.path.split("/")[0]

    if not domain:
        return url_or_domain.strip().lower()

    # Strip www prefix
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def domain_to_url(domain: str) -> str:
    """Convert a bare domain to an https URL."""
    domain = normalize_domain(domain)
    return f"https://{domain}"
