"""Custom AI enrichment — user-defined prompts for any enrichment task.

Configure in campaign YAML like:

custom_ai_steps:
  - name: "find_investors"
    prompt: |
      Find the investors and funding history for {{company_name}}.
      Look at their website and any available data.
    output_field: "investors"
    model: "gpt-4o"
    scrape_website: true

  - name: "pain_points"
    prompt: |
      Based on {{company_summary}} and their industry ({{industry}}),
      what are the top 3 business pain points this company likely faces?
    output_field: "pain_points"
    model: "gpt-4o-mini"

  - name: "competitor_analysis"
    prompt: |
      Who are the main competitors of {{company_name}}?
      Company info: {{company_summary}}
    output_field: "competitors"
    model: "gpt-4o"
    is_gate: true
    gate_field: "has_competitors"
"""

from __future__ import annotations

import json
import re
from typing import Any

from growthpal.ai.openai_client import chat_json
from growthpal.config import CampaignConfig
from growthpal.constants import Model
from growthpal.enrichments.base import EnrichmentStep
from growthpal.scrapers.website import scrape_website
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

# Matches {{field_name}} placeholders
TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


def _render_prompt(template: str, lead: dict) -> str:
    """Replace {{field_name}} placeholders with lead data."""

    def replacer(match: re.Match) -> str:
        field = match.group(1)
        value = lead.get(field, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value) if value else f"[no {field}]"

    return TEMPLATE_RE.sub(replacer, template)


class CustomAIStep(EnrichmentStep):
    """A dynamically configured AI enrichment step.

    Created at runtime from campaign YAML config — not registered via decorator.
    """

    def __init__(
        self,
        name: str,
        prompt_template: str,
        output_field: str = "custom_result",
        model: str = Model.GPT4O,
        scrape_website: bool = False,
        is_gate: bool = False,
        gate_field: str | None = None,
        max_tokens: int = 500,
    ):
        self.name = name
        self.prompt_template = prompt_template
        self.output_field = output_field
        self.model = model
        self._scrape_website = scrape_website
        self.is_gate = is_gate
        self.gate_field = gate_field
        self.max_tokens = max_tokens

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        # Optionally scrape website for more context
        website_content = ""
        if self._scrape_website:
            website = lead.get("website") or lead.get("raw_website") or ""
            if website:
                try:
                    website_content = await scrape_website(website)
                except Exception:
                    website_content = ""

        # Inject website_content into lead dict for template rendering
        lead_with_extras = {**lead, "website_content": website_content}

        # Render the user's prompt
        rendered_prompt = _render_prompt(self.prompt_template, lead_with_extras)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a B2B data research assistant. Respond in JSON with a "
                    f'"{self.output_field}" field containing your answer. '
                    "Be concise and factual. If you can't find the information, "
                    'set the field to null and add a "confidence" field set to 0.'
                ),
            },
            {"role": "user", "content": rendered_prompt},
        ]

        if self.is_gate:
            messages[0]["content"] += (
                f'\nAlso include a boolean field "{self.gate_field}" '
                "indicating if this lead should continue in the pipeline."
            )

        result = await chat_json(
            messages, model=self.model, max_tokens=self.max_tokens
        )
        data = result["data"]

        output: dict[str, Any] = {
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }

        # Store result in raw_extra JSONB (custom fields don't have dedicated columns)
        # We merge into raw_extra so all custom enrichment data is preserved
        existing_extra = lead.get("raw_extra") or {}
        if isinstance(existing_extra, str):
            try:
                existing_extra = json.loads(existing_extra)
            except json.JSONDecodeError:
                existing_extra = {}

        existing_extra[self.output_field] = data.get(self.output_field)
        output["raw_extra"] = json.dumps(existing_extra)

        # For gate steps, also set the gate field
        if self.is_gate and self.gate_field:
            gate_value = bool(data.get(self.gate_field, False))
            existing_extra[self.gate_field] = gate_value
            output["raw_extra"] = json.dumps(existing_extra)
            # Store gate result so _check_gate can find it
            output[f"_custom_gate_{self.gate_field}"] = gate_value

        return output


def load_custom_steps(campaign_config: CampaignConfig) -> list[CustomAIStep]:
    """Load custom AI steps from campaign config.

    Reads the 'custom_ai_steps' list from the campaign YAML.
    """
    step_defs = getattr(campaign_config, "custom_ai_steps", None) or []
    steps = []

    for step_def in step_defs:
        if not isinstance(step_def, dict):
            continue

        name = step_def.get("name")
        prompt = step_def.get("prompt")
        if not name or not prompt:
            log.warning(f"Skipping custom step with missing name or prompt: {step_def}")
            continue

        steps.append(
            CustomAIStep(
                name=f"custom:{name}",
                prompt_template=prompt,
                output_field=step_def.get("output_field", name),
                model=step_def.get("model", Model.GPT4O),
                scrape_website=step_def.get("scrape_website", False),
                is_gate=step_def.get("is_gate", False),
                gate_field=step_def.get("gate_field"),
                max_tokens=step_def.get("max_tokens", 500),
            )
        )

    log.info(f"Loaded {len(steps)} custom AI steps")
    return steps
