"""Tavily search API client — alternative to Serper for A/B testing.

Cost: ~$0.001/search (extract mode) or $0.0005/search (basic)
Same interface as serper.py for drop-in swapping.
"""

from __future__ import annotations

from typing import Any

import httpx

from growthpal.config import get_config
from growthpal.http import get_http_client
from growthpal.utils.logger import get_logger
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


@async_retry(max_retries=2, exceptions=(httpx.HTTPError, httpx.TimeoutException))
async def tavily_search(
    query: str,
    num_results: int = 5,
    search_depth: str = "basic",
    include_raw_content: bool = False,
) -> dict[str, Any]:
    """Search using the Tavily API.

    Args:
        query: Search query string
        num_results: Max number of results
        search_depth: "basic" ($0.0005) or "advanced" ($0.001)
        include_raw_content: Include extracted page content

    Returns:
        Dict with: results (list), cost
    """
    cfg = get_config()
    if not cfg.tavily_api_key:
        raise ValueError("TAVILY_API_KEY not configured")

    client = get_http_client()
    response = await client.post(
        TAVILY_API_URL,
        json={
            "api_key": cfg.tavily_api_key,
            "query": query,
            "max_results": num_results,
            "search_depth": search_depth,
            "include_raw_content": include_raw_content,
            "include_answer": True,
        },
    )
    response.raise_for_status()
    data = response.json()

    cost = 0.001 if search_depth == "advanced" else 0.0005

    # Normalize to match Serper's result format
    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "snippet": r.get("content", ""),
            "link": r.get("url", ""),
            "_raw_content": r.get("raw_content", ""),
        })

    return {
        "organic": results,
        "answer": data.get("answer", ""),
        "cost": cost,
    }


async def search_company_info(domain: str, company_name: str = "") -> dict[str, Any]:
    """Search for company information — same interface as serper.search_company_info.

    Returns: {results: list, cost: float}
    """
    search_name = company_name or domain.split(".")[0]

    queries = [
        f'"{search_name}" company',
        f'"{search_name}" funding employees OR headcount',
    ]

    all_results = []
    total_cost = 0.0

    for query in queries:
        try:
            result = await tavily_search(query, num_results=3, search_depth="basic")
            all_results.extend(result.get("organic", []))
            total_cost += result.get("cost", 0.0005)

            # Tavily provides a direct answer — include it as a synthetic result
            answer = result.get("answer", "")
            if answer:
                all_results.append({
                    "title": f"Tavily Answer: {search_name}",
                    "snippet": answer,
                    "link": "",
                    "_type": "ai_answer",
                })
        except Exception as e:
            log.debug(f"Tavily search failed for query '{query}': {e}")
            continue

    return {
        "results": all_results,
        "cost": total_cost,
        "search_provider": "tavily",
    }
