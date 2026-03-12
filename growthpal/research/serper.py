"""Serper.dev search API client for web search queries.

Cost: $0.0003/search (at 2500 credits plan)
"""

from __future__ import annotations

from typing import Any

import httpx

from growthpal.config import get_config
from growthpal.http import get_http_client
from growthpal.utils.logger import get_logger
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

SERPER_API_URL = "https://google.serper.dev/search"


@async_retry(max_retries=2, exceptions=(httpx.HTTPError, httpx.TimeoutException))
async def serper_search(query: str, num_results: int = 5) -> dict[str, Any]:
    """Search the web using Serper.dev.

    Args:
        query: Search query string
        num_results: Number of results to return

    Returns:
        Dict with: organic (list of results), cost
    """
    cfg = get_config()
    if not cfg.serper_api_key:
        raise ValueError("SERPER_API_KEY not configured")

    client = get_http_client()
    response = await client.post(
        SERPER_API_URL,
        headers={
            "X-API-KEY": cfg.serper_api_key,
            "Content-Type": "application/json",
        },
        json={
            "q": query,
            "num": num_results,
        },
    )
    response.raise_for_status()
    data = response.json()

    return {
        "organic": data.get("organic", []),
        "knowledge_graph": data.get("knowledgeGraph", {}),
        "answer_box": data.get("answerBox", {}),
        "cost": 0.0003,  # ~$0.0003 per search
    }


async def search_company_info(domain: str, company_name: str = "") -> dict[str, Any]:
    """Search for company information using multiple queries.

    Returns combined search results with cost.
    """
    queries = []
    search_name = company_name or domain.split(".")[0]

    # Primary query
    queries.append(f'"{search_name}" company')

    # Funding/employee query
    queries.append(f'"{search_name}" funding employees OR headcount')

    all_results = []
    total_cost = 0.0

    for query in queries:
        try:
            result = await serper_search(query, num_results=3)
            all_results.extend(result.get("organic", []))
            total_cost += result.get("cost", 0.0003)

            # Include knowledge graph if available
            kg = result.get("knowledge_graph", {})
            if kg:
                all_results.append({
                    "title": kg.get("title", ""),
                    "snippet": kg.get("description", ""),
                    "link": kg.get("website", ""),
                    "_type": "knowledge_graph",
                    "_data": kg,
                })
        except Exception as e:
            log.debug(f"Serper search failed for query '{query}': {e}")
            continue

    return {
        "results": all_results,
        "cost": total_cost,
    }
