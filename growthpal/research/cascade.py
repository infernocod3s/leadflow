"""5-Layer Research Cascade — orchestrates company data extraction.

Layer 0: Cache lookup ($0)
Layer 1: Heuristics — DNS, HTTP headers, JSON-LD, SSL ($0.000005)
Layer 2: CommonCrawl — archived web data ($0.0005)
Layer 3: Live scrape — HTTP GET + structured extraction ($0.001)
Layer 4: AI research — Serper search + AI synthesis ($0.008)

Average cost: ~$0.00013/lead (most resolve at layers 1-2)
"""

from __future__ import annotations

from typing import Any

from growthpal.research.cache import get_cached_company, upsert_company_cache
from growthpal.research.domain_utils import normalize_domain
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


async def research_company(
    website: str,
    company_name: str = "",
    min_quality: float = 0.6,
    enabled_layers: list[int] | None = None,
    cache_ttl_hours: int = 168,
    research_model: str = "gemini-2.0-flash-lite",
    search_provider: str = "serper",
) -> dict[str, Any]:
    """Run the 5-layer research cascade for a company.

    Normalizes domain, checks cache, then runs layers in order until
    data quality threshold is met.

    Args:
        website: Company website URL or domain
        company_name: Optional known company name
        min_quality: Minimum data quality score to stop (0.0-1.0)
        enabled_layers: Which layers to run (default: all [0,1,2,3,4])
        cache_ttl_hours: Cache freshness threshold
        research_model: AI model for Layer 4

    Returns:
        Dict with company data + metadata:
            - All company fields (company_name, description, industry, etc.)
            - _total_cost: Total cost across all layers
            - _layers_run: List of layer numbers executed
            - _resolved_by: Layer that met quality threshold (e.g. "layer_1")
            - data_quality_score: Final quality score
    """
    if not website:
        return {
            "company_name": company_name,
            "description": "",
            "_total_cost": 0.0,
            "_layers_run": [],
            "_resolved_by": "none",
            "data_quality_score": 0.0,
        }

    domain = normalize_domain(website)
    if enabled_layers is None:
        enabled_layers = [0, 1, 2, 3, 4]

    layers_run: list[int] = []
    layer_costs: dict[str, float] = {}
    total_cost = 0.0
    data: dict[str, Any] = {}
    if company_name:
        data["company_name"] = company_name

    # ── Layer 0: Cache ──────────────────────────────────────────────
    if 0 in enabled_layers:
        cached = get_cached_company(domain, max_age_hours=cache_ttl_hours)
        if cached:
            quality = cached.get("data_quality_score", 0.0)
            if quality >= min_quality:
                log.info(f"[cascade] {domain}: cache hit (quality={quality})")
                cached["_total_cost"] = 0.0
                cached["_layers_run"] = [0]
                cached["_resolved_by"] = "cache"
                return cached
            else:
                # Partial cache — use as starting data
                data = {k: v for k, v in cached.items()
                        if v and k not in ("id", "created_at", "updated_at",
                                           "company_info_at", "signals_at")}
                layers_run.append(0)

    # ── Layer 1: Heuristics ─────────────────────────────────────────
    if 1 in enabled_layers:
        from growthpal.research.heuristics import heuristic_research

        try:
            l1 = await heuristic_research(domain)
            layers_run.append(1)
            cost = l1.pop("_cost", 0.0)
            l1.pop("_layer", None)
            layer_costs["layer_1"] = cost
            total_cost += cost

            # Merge (don't overwrite existing good data)
            for k, v in l1.items():
                if v and not data.get(k):
                    data[k] = v
                elif k == "data_quality_score":
                    data[k] = v

            quality = data.get("data_quality_score", 0.0)
            log.info(f"[cascade] {domain}: layer 1 done (quality={quality:.2f})")

            if quality >= min_quality:
                return _finalize(domain, data, layers_run, layer_costs, total_cost, "layer_1")
        except Exception as e:
            log.warning(f"[cascade] {domain}: layer 1 failed: {e}")

    # ── Layer 2: CommonCrawl ────────────────────────────────────────
    if 2 in enabled_layers:
        from growthpal.research.commoncrawl import commoncrawl_research

        try:
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

            quality = data.get("data_quality_score", 0.0)
            log.info(f"[cascade] {domain}: layer 2 done (quality={quality:.2f})")

            if quality >= min_quality:
                return _finalize(domain, data, layers_run, layer_costs, total_cost, "layer_2")
        except Exception as e:
            log.warning(f"[cascade] {domain}: layer 2 failed: {e}")

    # ── Layer 3: Live Scrape ────────────────────────────────────────
    if 3 in enabled_layers:
        from growthpal.research.live_scrape import live_scrape_research

        try:
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

            quality = data.get("data_quality_score", 0.0)
            log.info(f"[cascade] {domain}: layer 3 done (quality={quality:.2f})")

            if quality >= min_quality:
                return _finalize(domain, data, layers_run, layer_costs, total_cost, "layer_3")
        except Exception as e:
            log.warning(f"[cascade] {domain}: layer 3 failed: {e}")

    # ── Layer 4: AI Research ────────────────────────────────────────
    if 4 in enabled_layers:
        from growthpal.research.ai_research import ai_research

        try:
            l4 = await ai_research(domain, company_name=company_name,
                                   existing_data=data, model=research_model,
                                   search_provider=search_provider)
            layers_run.append(4)
            cost = l4.pop("_cost", 0.0)
            l4.pop("_layer", None)
            layer_costs["layer_4"] = cost
            total_cost += cost

            # Layer 4 can overwrite since it's the most comprehensive
            for k, v in l4.items():
                if v and not k.startswith("_"):
                    if not data.get(k) or k == "data_quality_score":
                        data[k] = v

            quality = data.get("data_quality_score", 0.0)
            log.info(f"[cascade] {domain}: layer 4 done (quality={quality:.2f})")

            # Store AI metadata for enrichment logging
            data["_input_tokens"] = l4.get("_input_tokens", 0)
            data["_output_tokens"] = l4.get("_output_tokens", 0)
            data["_model"] = l4.get("_model", research_model)

            return _finalize(domain, data, layers_run, layer_costs, total_cost, "layer_4")
        except Exception as e:
            log.warning(f"[cascade] {domain}: layer 4 failed: {e}")

    # All layers exhausted
    resolved = f"layer_{layers_run[-1]}" if layers_run else "none"
    return _finalize(domain, data, layers_run, layer_costs, total_cost, resolved)


def _finalize(
    domain: str,
    data: dict[str, Any],
    layers_run: list[int],
    layer_costs: dict[str, float],
    total_cost: float,
    resolved_by: str,
) -> dict[str, Any]:
    """Finalize cascade results: cache + add metadata."""
    data["_total_cost"] = total_cost
    data["_layers_run"] = layers_run
    data["_resolved_by"] = resolved_by
    data["resolved_by"] = resolved_by
    data["layer_costs"] = layer_costs

    # Cache the result
    try:
        cache_data = {k: v for k, v in data.items() if not k.startswith("_")}
        cache_data["resolved_by"] = resolved_by
        upsert_company_cache(domain, cache_data)
    except Exception as e:
        log.warning(f"[cascade] Failed to cache {domain}: {e}")

    quality = data.get("data_quality_score", 0.0)
    log.info(
        f"[cascade] {domain}: resolved by {resolved_by} "
        f"(quality={quality:.2f}, cost=${total_cost:.6f}, layers={layers_run})"
    )

    return data
