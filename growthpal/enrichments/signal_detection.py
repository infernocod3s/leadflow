"""Step 6: Signal detection — uses cached company data + Serper search.

Now uses data from company_cache instead of re-scraping + GPT-4o.
Falls back to AI synthesis only when cached signals are stale/missing.
"""

import json
from typing import Any

from growthpal.ai.router import chat_json
from growthpal.ai.prompts import signal_detection_prompt
from growthpal.config import CampaignConfig
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register
from growthpal.research.cache import get_cached_signals
from growthpal.research.domain_utils import normalize_domain
from growthpal.research.serper import search_company_info
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


@register
class SignalDetectionStep(EnrichmentStep):
    name = "signal_detection"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        company_summary = lead.get("company_summary", "")
        website = lead.get("website") or lead.get("raw_website") or ""
        company_name = lead.get("company_name") or lead.get("raw_company") or ""

        # Check if signals were already populated by company_research cascade
        existing_signals = lead.get("signals")
        existing_tech = lead.get("tech_stack")
        if existing_signals and existing_signals != "[]" and existing_tech and existing_tech != "[]":
            log.info(f"[signal_detection] Signals already populated from cascade, skipping AI")
            return {
                "_model": None,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        # Check cached signals
        if website:
            domain = normalize_domain(website)
            cached = get_cached_signals(domain, max_age_hours=campaign_config.signals_cache_ttl_hours)
            if cached:
                log.info(f"[signal_detection] Using cached signals for {domain}")
                return {
                    "tech_stack": json.dumps(cached.get("tech_stack", [])),
                    "signals": json.dumps(cached.get("signals", [])),
                    "funding_signal": json.dumps(cached.get("funding_signal") or {}),
                    "hiring_signal": json.dumps(cached.get("hiring_signal") or {}),
                    "_model": None,
                    "_input_tokens": 0,
                    "_output_tokens": 0,
                    "_cost": 0.0,
                }

        # Build context from search results instead of re-scraping
        search_context = ""
        search_cost = 0.0
        if website and company_name:
            try:
                search_data = await search_company_info(
                    normalize_domain(website), company_name
                )
                snippets = [r.get("snippet", "") for r in search_data.get("results", [])[:5]]
                search_context = "\n".join(s for s in snippets if s)
                search_cost = search_data.get("cost", 0.0)
            except Exception:
                pass

        # AI signal detection using configured model
        context = f"{company_summary}\n\n{search_context}" if search_context else company_summary
        messages = signal_detection_prompt(context, "")
        model = campaign_config.classification_model

        result = await chat_json(messages, model=model, max_tokens=800)
        data = result["data"]

        total_cost = result["cost"] + search_cost

        return {
            "tech_stack": json.dumps(data.get("tech_stack", [])),
            "signals": json.dumps(data.get("signals", [])),
            "funding_signal": json.dumps(data.get("funding_signal") or {}),
            "hiring_signal": json.dumps(data.get("hiring_signal") or {}),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": total_cost,
        }
