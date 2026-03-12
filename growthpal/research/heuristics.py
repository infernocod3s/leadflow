"""Layer 1: Heuristic data extraction — DNS, HTTP headers, JSON-LD, SSL.

Cost: ~$0.000005/lead (just DNS + HTTP requests, no APIs)
"""

from __future__ import annotations

import asyncio
import ssl
import socket
from typing import Any

import httpx

from growthpal.http import get_http_client
from growthpal.research.domain_utils import domain_to_url
from growthpal.research.extractors import (
    detect_email_provider,
    extract_json_ld,
    extract_meta_tags,
    extract_opengraph,
    extract_organization_from_json_ld,
    extract_tech_from_html,
    compute_data_quality_score,
)
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


async def _resolve_mx(domain: str) -> list[str]:
    """Resolve MX records for a domain via DNS."""
    try:
        import dns.resolver
        loop = asyncio.get_event_loop()
        answers = await loop.run_in_executor(None, lambda: dns.resolver.resolve(domain, "MX"))
        return [str(r.exchange).rstrip(".") for r in answers]
    except Exception:
        return []


async def _get_ssl_org(domain: str) -> str | None:
    """Extract organization name from SSL certificate."""
    try:
        loop = asyncio.get_event_loop()

        def _fetch_cert():
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert = s.getpeercert()
                if cert:
                    subject = dict(x[0] for x in cert.get("subject", ()))
                    return subject.get("organizationName")
            return None

        return await loop.run_in_executor(None, _fetch_cert)
    except Exception:
        return None


async def heuristic_research(domain: str) -> dict[str, Any]:
    """Layer 1: Extract company data from DNS, HTTP response, and structured HTML.

    Returns company data dict with _cost, _layer fields.
    """
    result: dict[str, Any] = {"_layer": 1, "_cost": 0.0}
    url = domain_to_url(domain)

    # Run DNS MX, SSL cert, and HTTP GET in parallel
    mx_task = _resolve_mx(domain)
    ssl_task = _get_ssl_org(domain)

    try:
        client = get_http_client()
        http_response = await client.get(url)
        http_response.raise_for_status()
        html = http_response.text
        headers = dict(http_response.headers)
    except Exception as e:
        log.debug(f"Layer 1: HTTP fetch failed for {domain}: {e}")
        html = ""
        headers = {}

    mx_records, ssl_org = await asyncio.gather(mx_task, ssl_task, return_exceptions=True)

    # Handle exceptions from gather
    if isinstance(mx_records, Exception):
        mx_records = []
    if isinstance(ssl_org, Exception):
        ssl_org = None

    # Email provider from MX
    if mx_records:
        provider = detect_email_provider(mx_records)
        if provider:
            result["email_provider"] = provider

    # SSL org name
    if ssl_org:
        result["company_name"] = ssl_org

    if not html:
        result["data_quality_score"] = compute_data_quality_score(result)
        return result

    # JSON-LD extraction (richest structured data source)
    json_ld_items = extract_json_ld(html)
    if json_ld_items:
        result["json_ld_data"] = json_ld_items
        org_data = extract_organization_from_json_ld(json_ld_items)
        for key, value in org_data.items():
            if value:
                result[key] = value

    # OpenGraph
    og = extract_opengraph(html)
    if og.get("site_name") and not result.get("company_name"):
        result["company_name"] = og["site_name"]
    if og.get("description") and not result.get("description"):
        result["description"] = og["description"]

    # Meta tags
    meta = extract_meta_tags(html)
    if meta.get("description") and not result.get("description"):
        result["description"] = meta["description"]
    if meta.get("application-name") and not result.get("company_name"):
        result["company_name"] = meta["application-name"]

    # Tech stack
    tech = extract_tech_from_html(html, headers)
    if tech:
        result["tech_stack"] = []
        for category, items in tech.items():
            result["tech_stack"].extend(items)
        # Set CMS/hosting from detected tech
        if tech.get("cms"):
            result["cms"] = tech["cms"][0]
        if tech.get("hosting"):
            result["hosting"] = tech["hosting"][0]

    result["data_quality_score"] = compute_data_quality_score(result)
    return result
