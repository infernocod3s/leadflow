"""Step 7: Email generation — generate cold email copy.

Now uses configurable model (default: DeepSeek V3) instead of GPT-4o.
"""

from typing import Any

from growthpal.ai.router import chat_json
from growthpal.ai.prompts import email_generation_prompt
from growthpal.config import CampaignConfig
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register


@register
class EmailGenerationStep(EnrichmentStep):
    name = "email_generation"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        config_dict = {
            "sender_name": campaign_config.sender_name,
            "sender_company": campaign_config.sender_company,
            "sender_value_prop": campaign_config.sender_value_prop,
            "email_cta": campaign_config.email_cta,
            "email_tone": campaign_config.email_tone,
        }

        messages = email_generation_prompt(lead, config_dict)
        model = campaign_config.email_generation_model
        result = await chat_json(messages, model=model, max_tokens=600)
        data = result["data"]

        return {
            "email_subject": data.get("subject", ""),
            "email_body": data.get("body", ""),
            "email_variant": data.get("variant", "A"),
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
