"""Step 4: Name cleaning — fix first/last name + company name."""

from typing import Any

from leadflow.ai.openai_client import chat_json
from leadflow.ai.prompts import name_cleaning_prompt
from leadflow.config import CampaignConfig
from leadflow.constants import Model
from leadflow.enrichments.base import EnrichmentStep
from leadflow.pipeline.registry import register


@register
class NameCleaningStep(EnrichmentStep):
    name = "name_cleaning"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        first = lead.get("raw_first_name") or lead.get("first_name") or ""
        last = lead.get("raw_last_name") or lead.get("last_name") or ""
        company = lead.get("raw_company") or lead.get("company_name") or ""

        if not any([first, last, company]):
            return {
                "_model": Model.GPT4O_MINI,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        messages = name_cleaning_prompt(first, last, company)
        result = await chat_json(messages, model=Model.GPT4O_MINI, max_tokens=200)
        data = result["data"]

        return {
            "first_name": data.get("first_name", first),
            "last_name": data.get("last_name", last),
            "company_name": data.get("company_name", company),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
