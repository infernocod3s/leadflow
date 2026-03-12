"""Step 6: Signal detection — tech stack, funding, hiring signals."""

import json
from typing import Any

from leadflow.ai.openai_client import chat_json
from leadflow.ai.prompts import signal_detection_prompt
from leadflow.config import CampaignConfig
from leadflow.constants import Model
from leadflow.enrichments.base import EnrichmentStep
from leadflow.pipeline.registry import register
from leadflow.scrapers.website import scrape_website
from leadflow.utils.logger import get_logger

log = get_logger(__name__)


@register
class SignalDetectionStep(EnrichmentStep):
    name = "signal_detection"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        company_summary = lead.get("company_summary", "")
        website = lead.get("website") or lead.get("raw_website") or ""

        # Get website content (may already be cached from company_research)
        website_content = ""
        if website:
            try:
                website_content = await scrape_website(website)
            except Exception:
                pass

        messages = signal_detection_prompt(company_summary, website_content)
        result = await chat_json(messages, model=Model.GPT4O, max_tokens=800)
        data = result["data"]

        return {
            "tech_stack": json.dumps(data.get("tech_stack", [])),
            "signals": json.dumps(data.get("signals", [])),
            "funding_signal": json.dumps(data.get("funding_signal") or {}),
            "hiring_signal": json.dumps(data.get("hiring_signal") or {}),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
