"""Layer 2: CommonCrawl — free historical web data via CDX Index API.

Cost: ~$0.0005/lead (just HTTP requests to CC index + WARC fetch)
"""

from __future__ import annotations

import gzip
from typing import Any

import httpx

from growthpal.http import get_http_client
from growthpal.research.extractors import (
    extract_json_ld,
    extract_meta_tags,
    extract_opengraph,
    extract_organization_from_json_ld,
    extract_tech_from_html,
    compute_data_quality_score,
)
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

CDX_API_URL = "https://index.commoncrawl.org/CC-MAIN-2024-51-index"


async def _query_cdx_index(domain: str) -> list[dict]:
    """Query CommonCrawl CDX Index for a domain's pages."""
    client = get_http_client()
    try:
        response = await client.get(
            CDX_API_URL,
            params={
                "url": f"{domain}/*",
                "output": "json",
                "limit": 5,
                "filter": "status:200",
                "fl": "url,filename,offset,length,status",
            },
        )
        if response.status_code != 200:
            return []

        lines = response.text.strip().split("\n")
        if len(lines) < 2:  # First line is header
            return []

        import json
        results = []
        for line in lines[1:]:  # Skip header
            try:
                results.append(json.loads(line))
            except Exception:
                continue
        return results

    except Exception as e:
        log.debug(f"CDX query failed for {domain}: {e}")
        return []


async def _fetch_warc_content(filename: str, offset: int, length: int) -> str | None:
    """Fetch HTML content from a WARC file using byte-range request."""
    client = get_http_client()
    warc_url = f"https://data.commoncrawl.org/{filename}"

    try:
        response = await client.get(
            warc_url,
            headers={"Range": f"bytes={offset}-{offset + length - 1}"},
        )
        if response.status_code not in (200, 206):
            return None

        # Decompress gzip WARC content
        try:
            decompressed = gzip.decompress(response.content)
            text = decompressed.decode("utf-8", errors="replace")
        except Exception:
            text = response.text

        # Extract HTML body from WARC record
        # WARC format: headers \r\n\r\n HTTP response \r\n\r\n HTML
        parts = text.split("\r\n\r\n", 2)
        if len(parts) >= 3:
            return parts[2]
        elif len(parts) >= 2:
            return parts[1]
        return text

    except Exception as e:
        log.debug(f"WARC fetch failed: {e}")
        return None


async def commoncrawl_research(domain: str, existing_data: dict | None = None) -> dict[str, Any]:
    """Layer 2: Extract company data from CommonCrawl archives.

    Args:
        domain: Normalized domain
        existing_data: Data from previous layers to merge with

    Returns company data dict with _cost, _layer fields.
    """
    result: dict[str, Any] = dict(existing_data or {})
    result["_layer"] = 2
    result["_cost"] = 0.0  # Free!

    # Query CDX index
    entries = await _query_cdx_index(domain)
    if not entries:
        log.debug(f"Layer 2: No CommonCrawl data for {domain}")
        result["data_quality_score"] = compute_data_quality_score(result)
        return result

    # Fetch the first (most recent) entry's WARC content
    entry = entries[0]
    try:
        offset = int(entry.get("offset", 0))
        length = int(entry.get("length", 0))
    except (ValueError, TypeError):
        result["data_quality_score"] = compute_data_quality_score(result)
        return result

    html = await _fetch_warc_content(entry["filename"], offset, length)
    if not html:
        result["data_quality_score"] = compute_data_quality_score(result)
        return result

    # Extract structured data from archived HTML
    json_ld_items = extract_json_ld(html)
    if json_ld_items and not result.get("json_ld_data"):
        result["json_ld_data"] = json_ld_items
        org_data = extract_organization_from_json_ld(json_ld_items)
        for key, value in org_data.items():
            if value and not result.get(key):
                result[key] = value

    og = extract_opengraph(html)
    if og.get("site_name") and not result.get("company_name"):
        result["company_name"] = og["site_name"]
    if og.get("description") and not result.get("description"):
        result["description"] = og["description"]

    meta = extract_meta_tags(html)
    if meta.get("description") and not result.get("description"):
        result["description"] = meta["description"]

    tech = extract_tech_from_html(html)
    if tech and not result.get("tech_stack"):
        all_tech = []
        for items in tech.values():
            all_tech.extend(items)
        result["tech_stack"] = all_tech

    result["data_quality_score"] = compute_data_quality_score(result)
    return result
