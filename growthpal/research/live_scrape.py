"""Layer 3: Live website scrape + structured extraction.

Cost: ~$0.001/lead (HTTP requests, no APIs)
Reuses the existing scraper but adds structured data extraction.
"""

from __future__ import annotations

from typing import Any

import httpx

from growthpal.research.domain_utils import domain_to_url
from growthpal.research.extractors import (
    extract_json_ld,
    extract_meta_tags,
    extract_opengraph,
    extract_organization_from_json_ld,
    extract_tech_from_html,
    compute_data_quality_score,
)
from growthpal.scrapers.website import _extract_text, _get_http_client
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

# Subpages to check for richer data
SUBPAGES = ["/about", "/about-us", "/company", "/products", "/pricing"]


async def live_scrape_research(domain: str, existing_data: dict | None = None) -> dict[str, Any]:
    """Layer 3: Live scrape homepage + key subpages for structured data.

    Builds on data from previous layers.
    """
    result: dict[str, Any] = dict(existing_data or {})
    result["_layer"] = 3
    result["_cost"] = 0.0  # Just HTTP requests

    base_url = domain_to_url(domain)
    client = _get_http_client()

    all_text_parts = []

    # Scrape homepage + subpages
    urls = [base_url] + [f"{base_url}{path}" for path in SUBPAGES]

    for url in urls:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                continue

            html = response.text
            headers = dict(response.headers)

            # Only do full extraction on homepage
            if url == base_url:
                # JSON-LD
                json_ld_items = extract_json_ld(html)
                if json_ld_items and not result.get("json_ld_data"):
                    result["json_ld_data"] = json_ld_items
                    org_data = extract_organization_from_json_ld(json_ld_items)
                    for key, value in org_data.items():
                        if value and not result.get(key):
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

                # Tech stack
                tech = extract_tech_from_html(html, headers)
                if tech and not result.get("tech_stack"):
                    all_tech = []
                    for items in tech.values():
                        all_tech.extend(items)
                    result["tech_stack"] = all_tech
                    if tech.get("cms"):
                        result["cms"] = tech["cms"][0]
                    if tech.get("hosting"):
                        result["hosting"] = tech["hosting"][0]

            # Collect text for potential AI use later
            text = _extract_text(html, max_length=3000)
            if text:
                all_text_parts.append(text)

        except Exception as e:
            log.debug(f"Layer 3: Failed to scrape {url}: {e}")
            continue

    # Store raw scraped text for downstream use
    if all_text_parts:
        result["_scraped_text"] = "\n\n".join(all_text_parts)[:10000]

    result["data_quality_score"] = compute_data_quality_score(result)
    return result
