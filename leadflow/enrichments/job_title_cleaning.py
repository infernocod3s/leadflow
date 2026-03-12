"""Step 3: Job title cleaning — normalize job titles."""

from typing import Any

from leadflow.ai.openai_client import chat_json
from leadflow.ai.prompts import job_title_cleaning_prompt
from leadflow.config import CampaignConfig
from leadflow.constants import Model
from leadflow.enrichments.base import EnrichmentStep
from leadflow.pipeline.registry import register


@register
class JobTitleCleaningStep(EnrichmentStep):
    name = "job_title_cleaning"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        raw_title = lead.get("raw_title") or lead.get("job_title") or ""

        if not raw_title:
            return {
                "job_title": "",
                "_model": Model.GPT4O_MINI,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        messages = job_title_cleaning_prompt(raw_title)
        result = await chat_json(messages, model=Model.GPT4O_MINI, max_tokens=200)
        data = result["data"]

        return {
            "job_title": data.get("clean_title", raw_title),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
