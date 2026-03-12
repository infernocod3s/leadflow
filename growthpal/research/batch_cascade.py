"""Batch research cascade — domain-deduplicated, concurrent, with per-service semaphores.

Flow:
1. Extract + deduplicate domains from leads
2. Batch cache lookup (single Supabase query)
3. Run cascade on cache misses concurrently with per-service semaphores
4. Batch upsert results to cache
5. Return {domain: company_data}
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from growthpal.research.cache import batch_get_cached_companies, batch_upsert_company_cache
from growthpal.research.domain_utils import normalize_domain
from growthpal.research.extractors import compute_data_quality_score
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

# ── Per-service semaphores (configurable via env) ──────────────────────────
_semaphores: dict[str, asyncio.Semaphore] = {}

_SEMAPHORE_DEFAULTS = {
    "http_general": 200,
    "dns": 100,
    "commoncrawl": 50,
    "search_api": 30,
    "ai_api": 50,
    "supabase": 50,
}


def _get_semaphore(name: str) -> asyncio.Semaphore:
    """Get or create a per-service semaphore."""
    if name not in _semaphores:
        limit = int(os.getenv(f"SEMAPHORE_{name.upper()}", _SEMAPHORE_DEFAULTS.get(name, 50)))
        _semaphores[name] = asyncio.Semaphore(limit)
    return _semaphores[name]


def reset_semaphores() -> None:
    """Reset all semaphores (for testing)."""
    _semaphores.clear()


async def _cascade_single_domain(
    domain: str,
    company_name: str,
    existing_data: dict | None,
    min_quality: float,
    enabled_layers: list[int],
    research_model: str,
    search_provider: str,
) -> dict[str, Any]:
    """Run the research cascade on a single domain with semaphore gating."""
    data: dict[str, Any] = dict(existing_data or {})
    if company_name:
        data["company_name"] = company_name

    layers_run: list[int] = []
    layer_costs: dict[str, float] = {}
    total_cost = 0.0

    # ── Layer 1: Heuristics (HTTP + DNS) ──────────────────────────────
    if 1 in enabled_layers:
        from growthpal.research.heuristics import heuristic_research

        try:
            async with _get_semaphore("http_general"):
                l1 = await heuristic_research(domain)
            layers_run.append(1)
            cost = l1.pop("_cost", 0.0)
            l1.pop("_layer", None)
            layer_costs["layer_1"] = cost
            total_cost += cost

            for k, v in l1.items():
                if v and not data.get(k):
                    data[k] = v
                elif k == "data_quality_score":
                    data[k] = v

            if data.get("data_quality_score", 0.0) >= min_quality:
                return _finalize_batch(domain, data, layers_run, layer_costs, total_cost, "layer_1")
        except Exception as e:
            log.debug(f"[batch_cascade] {domain}: layer 1 failed: {e}")

    # ── Layer 2: CommonCrawl ──────────────────────────────────────────
    if 2 in enabled_layers:
        from growthpal.research.commoncrawl import commoncrawl_research

        try:
            async with _get_semaphore("commoncrawl"):
                l2 = await commoncrawl_research(domain, existing_data=data)
            layers_run.append(2)
            cost = l2.pop("_cost", 0.0)
            l2.pop("_layer", None)
            layer_costs["layer_2"] = cost
            total_cost += cost

            for k, v in l2.items():
                if v and not data.get(k):
                    data[k] = v
                elif k == "data_quality_score":
                    data[k] = v

            if data.get("data_quality_score", 0.0) >= min_quality:
                return _finalize_batch(domain, data, layers_run, layer_costs, total_cost, "layer_2")
        except Exception as e:
            log.debug(f"[batch_cascade] {domain}: layer 2 failed: {e}")

    # ── Layer 3: Live Scrape ──────────────────────────────────────────
    if 3 in enabled_layers:
        from growthpal.research.live_scrape import live_scrape_research

        try:
            async with _get_semaphore("http_general"):
                l3 = await live_scrape_research(domain, existing_data=data)
            layers_run.append(3)
            cost = l3.pop("_cost", 0.0)
            l3.pop("_layer", None)
            layer_costs["layer_3"] = cost
            total_cost += cost

            for k, v in l3.items():
                if v and not data.get(k):
                    data[k] = v
                elif k == "data_quality_score":
                    data[k] = v

            if data.get("data_quality_score", 0.0) >= min_quality:
                return _finalize_batch(domain, data, layers_run, layer_costs, total_cost, "layer_3")
        except Exception as e:
            log.debug(f"[batch_cascade] {domain}: layer 3 failed: {e}")

    # ── Layer 4: AI Research ──────────────────────────────────────────
    if 4 in enabled_layers:
        from growthpal.research.ai_research import ai_research

        try:
            async with _get_semaphore("search_api"), _get_semaphore("ai_api"):
                l4 = await ai_research(
                    domain, company_name=company_name,
                    existing_data=data, model=research_model,
                    search_provider=search_provider,
                )
            layers_run.append(4)
            cost = l4.pop("_cost", 0.0)
            l4.pop("_layer", None)
            layer_costs["layer_4"] = cost
            total_cost += cost

            for k, v in l4.items():
                if v and not k.startswith("_"):
                    if not data.get(k) or k == "data_quality_score":
                        data[k] = v

            data["_input_tokens"] = l4.get("_input_tokens", 0)
            data["_output_tokens"] = l4.get("_output_tokens", 0)
            data["_model"] = l4.get("_model", research_model)

            return _finalize_batch(domain, data, layers_run, layer_costs, total_cost, "layer_4")
        except Exception as e:
            log.debug(f"[batch_cascade] {domain}: layer 4 failed: {e}")

    resolved = f"layer_{layers_run[-1]}" if layers_run else "none"
    return _finalize_batch(domain, data, layers_run, layer_costs, total_cost, resolved)


def _finalize_batch(
    domain: str,
    data: dict[str, Any],
    layers_run: list[int],
    layer_costs: dict[str, float],
    total_cost: float,
    resolved_by: str,
) -> dict[str, Any]:
    """Finalize without caching — batch_cascade handles bulk caching."""
    data["_total_cost"] = total_cost
    data["_layers_run"] = layers_run
    data["_resolved_by"] = resolved_by
    data["resolved_by"] = resolved_by
    data["layer_costs"] = layer_costs
    return data


async def research_companies_batch(
    leads: list[dict],
    min_quality: float = 0.6,
    enabled_layers: list[int] | None = None,
    cache_ttl_hours: int = 168,
    research_model: str = "gemini-2.0-flash-lite",
    search_provider: str = "serper",
) -> dict[str, dict]:
    """Batch research: dedup by domain, batch cache lookup, concurrent cascade.

    Args:
        leads: List of lead dicts (must have raw_website/website + raw_company/company_name)
        min_quality: Minimum data quality score
        enabled_layers: Which layers to run (default all)
        cache_ttl_hours: Cache freshness threshold
        research_model: AI model for Layer 4
        search_provider: "serper" or "tavily"

    Returns:
        {domain: company_data} for all unique domains
    """
    if enabled_layers is None:
        enabled_layers = [0, 1, 2, 3, 4]

    # ── Step 1: Extract + deduplicate domains ──────────────────────────
    domain_map: dict[str, str] = {}  # domain -> best company_name
    for lead in leads:
        website = lead.get("raw_website") or lead.get("website") or ""
        if not website:
            continue
        domain = normalize_domain(website)
        if domain and domain not in domain_map:
            domain_map[domain] = lead.get("raw_company") or lead.get("company_name") or ""

    all_domains = list(domain_map.keys())
    log.info(f"[batch_cascade] {len(leads)} leads → {len(all_domains)} unique domains")

    if not all_domains:
        return {}

    results: dict[str, dict] = {}

    # ── Step 2: Batch cache lookup ─────────────────────────────────────
    cache_hits: dict[str, dict] = {}
    if 0 in enabled_layers:
        cache_hits = batch_get_cached_companies(all_domains, max_age_hours=cache_ttl_hours)
        for domain, data in cache_hits.items():
            quality = data.get("data_quality_score", 0.0)
            if quality >= min_quality:
                data["_total_cost"] = 0.0
                data["_layers_run"] = [0]
                data["_resolved_by"] = "cache"
                results[domain] = data

    cache_misses = [d for d in all_domains if d not in results]
    log.info(f"[batch_cascade] {len(results)} cache hits, {len(cache_misses)} misses to research")

    if not cache_misses:
        return results

    # ── Step 3: Concurrent cascade on misses ───────────────────────────
    # Use partial cache data as starting point if available
    async def _research_one(domain: str) -> tuple[str, dict]:
        existing = cache_hits.get(domain)  # partial cache data
        name = domain_map.get(domain, "")
        data = await _cascade_single_domain(
            domain=domain,
            company_name=name,
            existing_data=existing,
            min_quality=min_quality,
            enabled_layers=[l for l in enabled_layers if l != 0],  # skip cache layer
            research_model=research_model,
            search_provider=search_provider,
        )
        return domain, data

    tasks = [asyncio.create_task(_research_one(d)) for d in cache_misses]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results
    to_cache: dict[str, dict] = {}
    for item in completed:
        if isinstance(item, Exception):
            log.warning(f"[batch_cascade] Domain research failed: {item}")
            continue
        domain, data = item
        results[domain] = data
        # Prepare for batch cache upsert (strip underscore keys)
        cache_data = {k: v for k, v in data.items() if not k.startswith("_")}
        cache_data["resolved_by"] = data.get("_resolved_by", "unknown")
        to_cache[domain] = cache_data

    # ── Step 4: Batch cache upsert ─────────────────────────────────────
    if to_cache:
        try:
            batch_upsert_company_cache(to_cache)
        except Exception as e:
            log.warning(f"[batch_cascade] Batch cache upsert failed: {e}")

    total_cost = sum(d.get("_total_cost", 0.0) for d in results.values())
    log.info(
        f"[batch_cascade] Done: {len(results)} domains researched, "
        f"${total_cost:.4f} total cost"
    )
    return results
