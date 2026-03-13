"""Step 10: Email generation — generate cold email copy.

Now uses configurable model (default: DeepSeek V3) instead of GPT-4o.
Supports strategy-specific email prompts when strategy_routing is configured.
"""

import json
import re
from typing import Any

from growthpal.ai.router import chat_json
from growthpal.ai.prompts import email_generation_prompt
from growthpal.config import CampaignConfig
from growthpal.enrichments.base import EnrichmentStep
from growthpal.enrichments.strategy_router import get_strategy_by_id
from growthpal.pipeline.registry import register
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

# Matches {{field_name}} and {{dotted.field}} placeholders
_TEMPLATE_RE = re.compile(r"\{\{([\w.]+)\}\}")


def _render_strategy_prompt(template: str, lead: dict) -> str:
    """Replace {{field}} placeholders with lead data. Supports dot notation."""

    def replacer(match: re.Match) -> str:
        field_path = match.group(1)
        # Simple field
        if "." not in field_path:
            value = lead.get(field_path, "")
        else:
            # Dot notation: resolve nested
            from growthpal.enrichments.strategy_router import resolve_field
            value = resolve_field(lead, field_path)

        if value is None:
            return f"[no {field_path}]"
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value) if value else f"[no {field_path}]"

    return _TEMPLATE_RE.sub(replacer, template)


@register
class EmailGenerationStep(EnrichmentStep):
    name = "email_generation"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        strategy_id = lead.get("strategy_id")

        # If strategy is assigned, use strategy-specific prompt
        if strategy_id:
            strategy = get_strategy_by_id(campaign_config, strategy_id)
            if strategy and strategy.get("email_prompt"):
                return await self._process_with_strategy(lead, campaign_config, strategy)

        # Default: use generic email generation prompt (backward compat)
        return await self._process_generic(lead, campaign_config)

    async def _process_with_strategy(
        self, lead: dict, campaign_config: CampaignConfig, strategy: dict
    ) -> dict[str, Any]:
        """Generate email using a strategy-specific prompt template."""
        rendered_prompt = _render_strategy_prompt(strategy["email_prompt"], lead)

        config_context = (
            f"Sender: {campaign_config.sender_name} from {campaign_config.sender_company}\n"
            f"Value prop: {campaign_config.sender_value_prop}\n"
            f"CTA: {campaign_config.email_cta}\n"
            f"Tone: {campaign_config.email_tone}"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert cold email copywriter. Generate a personalized "
                    "cold email based on the specific angle and lead data provided.\n\n"
                    "Rules:\n"
                    "- Use {{first_name}} as merge tag for the recipient's first name\n"
                    "- Mention specific company details to show research\n"
                    "- Keep it under 120 words\n"
                    "- Soft CTA, no hard sell\n"
                    "- No fake familiarity or flattery\n"
                    "- No emojis or excessive punctuation\n\n"
                    f"Sender context:\n{config_context}\n\n"
                    'Respond in JSON: {"subject": "...", "body": "..."}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Strategy: {strategy.get('name', strategy['id'])}\n\n"
                    f"Lead: {lead.get('first_name', '')} {lead.get('last_name', '')} "
                    f"— {lead.get('job_title', '')} at {lead.get('company_name', '')}\n"
                    f"Company summary: {lead.get('company_summary', '')}\n\n"
                    f"Angle-specific prompt:\n{rendered_prompt}"
                ),
            },
        ]

        model = campaign_config.email_generation_model
        result = await chat_json(messages, model=model, max_tokens=600)
        data = result["data"]

        log.info(
            f"[email_generation] Generated email with strategy '{strategy['id']}' "
            f"for {lead.get('email', '?')}"
        )

        return {
            "email_subject": data.get("subject", ""),
            "email_body": data.get("body", ""),
            "email_variant": strategy["id"],
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }

    async def _process_generic(
        self, lead: dict, campaign_config: CampaignConfig
    ) -> dict[str, Any]:
        """Generate email using the original generic prompt."""
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
