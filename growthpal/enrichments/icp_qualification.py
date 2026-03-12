"""Step 2: ICP qualification — qualify company vs Ideal Customer Profile (GATE)."""

from typing import Any

from growthpal.ai.openai_client import chat_json
from growthpal.ai.prompts import icp_qualification_prompt
from growthpal.config import CampaignConfig
from growthpal.constants import Model
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


@register
class ICPQualificationStep(EnrichmentStep):
    name = "icp_qualification"
    is_gate = True

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        company_summary = lead.get("company_summary", "")
        icp_description = campaign_config.icp_description
        target_industries = campaign_config.target_industries

        if not company_summary or company_summary == "No website available":
            return {
                "icp_qualified": False,
                "icp_reason": "No company data available for qualification",
                "_model": Model.GPT4O,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        messages = icp_qualification_prompt(company_summary, icp_description, target_industries)
        result = await chat_json(messages, model=Model.GPT4O, max_tokens=300)
        data = result["data"]

        return {
            "icp_qualified": bool(data.get("qualified", False)),
            "icp_reason": data.get("reason", ""),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
