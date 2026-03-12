"""Step 1: Company research — 5-layer cascade replaces GPT-4o scraping.

Supports both single-lead `process()` and batch `process_batch()`.
"""

import json
from typing import Any

from growthpal.config import CampaignConfig
from growthpal.constants import Model
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register
from growthpal.research.cascade import research_company
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


def _build_result_from_data(data: dict, website: str) -> dict[str, Any]:
    """Convert cascade output into the enrichment result format."""
    summary_parts = []
    if data.get("description"):
        summary_parts.append(data["description"])
    if data.get("industry"):
        summary_parts.append(f"Industry: {data['industry']}")
    if data.get("employee_count"):
        summary_parts.append(f"Employees: {data['employee_count']}")
    if data.get("funding"):
        summary_parts.append(f"Funding: {data['funding']}")
    if data.get("products"):
        products = data["products"]
        if isinstance(products, list):
            names = [p["name"] if isinstance(p, dict) else str(p) for p in products[:5]]
            summary_parts.append(f"Products: {', '.join(names)}")
    if data.get("target_market"):
        summary_parts.append(f"Target market: {data['target_market']}")

    company_summary = ". ".join(summary_parts) if summary_parts else data.get("company_name", "")

    return {
        "company_summary": company_summary,
        "industry": data.get("industry", ""),
        "company_employee_count": data.get("employee_count", ""),
        "company_funding": data.get("funding", ""),
        "website": website,
        "tech_stack": json.dumps(data.get("tech_stack", [])),
        "signals": json.dumps(data.get("signals", [])),
        "funding_signal": json.dumps(data.get("funding_signal") or {}),
        "hiring_signal": json.dumps(data.get("hiring_signal") or {}),
        "_model": data.get("_model"),
        "_input_tokens": data.get("_input_tokens", 0),
        "_output_tokens": data.get("_output_tokens", 0),
        "_cost": data.get("_total_cost", 0.0),
        "_research_layer": data.get("_resolved_by", "unknown"),
    }


@register
class CompanyResearchStep(EnrichmentStep):
    name = "company_research"
    supports_batch = True

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        website = lead.get("raw_website") or lead.get("website") or ""
        company_name = lead.get("raw_company") or lead.get("company_name") or ""

        if not website:
            return {
                "company_summary": "No website available",
                "_model": None,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        data = await research_company(
            website=website,
            company_name=company_name,
            min_quality=campaign_config.min_data_quality_score,
            enabled_layers=campaign_config.research_layers_enabled,
            cache_ttl_hours=campaign_config.cache_ttl_hours,
            research_model=campaign_config.research_model,
            search_provider=campaign_config.search_provider,
        )

        log.info(
            f"[company_research] {website}: resolved by {data.get('_resolved_by', '?')}, "
            f"layers={data.get('_layers_run', [])}, cost=${data.get('_total_cost', 0):.6f}"
        )

        return _build_result_from_data(data, website)

    async def process_batch(
        self, leads: list[dict], campaign_config: CampaignConfig
    ) -> dict[str, dict[str, Any]]:
        """Batch company research — domain-deduplicated concurrent cascade.

        Returns: {lead_id: result_dict}
        """
        from growthpal.research.batch_cascade import research_companies_batch
        from growthpal.research.domain_utils import normalize_domain

        # Run batch cascade
        domain_results = await research_companies_batch(
            leads=leads,
            min_quality=campaign_config.min_data_quality_score,
            enabled_layers=campaign_config.research_layers_enabled,
            cache_ttl_hours=campaign_config.cache_ttl_hours,
            research_model=campaign_config.research_model,
            search_provider=campaign_config.search_provider,
        )

        # Map domain results back to individual leads
        results: dict[str, dict[str, Any]] = {}
        for lead in leads:
            lead_id = lead["id"]
            website = lead.get("raw_website") or lead.get("website") or ""
            if not website:
                results[lead_id] = {
                    "company_summary": "No website available",
                    "_model": None,
                    "_input_tokens": 0,
                    "_output_tokens": 0,
                    "_cost": 0.0,
                }
                continue

            domain = normalize_domain(website)
            data = domain_results.get(domain, {})
            if data:
                results[lead_id] = _build_result_from_data(data, website)
            else:
                results[lead_id] = {
                    "company_summary": "Research failed",
                    "_model": None,
                    "_input_tokens": 0,
                    "_output_tokens": 0,
                    "_cost": 0.0,
                }

        return results
