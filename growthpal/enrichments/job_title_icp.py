"""Step 5: Job title ICP match — role relevance check (GATE)."""

from typing import Any

from growthpal.ai.openai_client import chat_json
from growthpal.ai.prompts import job_title_icp_prompt
from growthpal.config import CampaignConfig
from growthpal.constants import Model
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register


@register
class JobTitleICPStep(EnrichmentStep):
    name = "job_title_icp"
    is_gate = True

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        job_title = lead.get("job_title") or lead.get("raw_title") or ""
        target_titles = campaign_config.target_titles

        if not job_title or not target_titles:
            return {
                "title_relevant": False,
                "title_relevance_reason": "No job title or target titles available",
                "_model": Model.GPT4O_MINI,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        messages = job_title_icp_prompt(job_title, target_titles)
        result = await chat_json(messages, model=Model.GPT4O_MINI, max_tokens=200)
        data = result["data"]

        return {
            "title_relevant": bool(data.get("relevant", False)),
            "title_relevance_reason": data.get("reason", ""),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
