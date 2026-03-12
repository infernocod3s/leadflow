"""Step 1: Company research — scrape website + AI summary."""

from typing import Any

from growthpal.ai.openai_client import chat_json
from growthpal.ai.prompts import company_research_prompt
from growthpal.config import CampaignConfig
from growthpal.constants import Model
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register
from growthpal.scrapers.website import scrape_multiple_pages
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


@register
class CompanyResearchStep(EnrichmentStep):
    name = "company_research"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        website = lead.get("raw_website") or lead.get("website") or ""
        company_name = lead.get("raw_company") or lead.get("company_name") or ""

        if not website:
            return {
                "company_summary": "No website available",
                "_model": Model.GPT4O,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        # Scrape website
        content = await scrape_multiple_pages(website)
        if not content:
            content = f"Company: {company_name}. No website content could be scraped."

        # AI analysis
        messages = company_research_prompt(content, company_name)
        result = await chat_json(messages, model=Model.GPT4O, max_tokens=500)
        data = result["data"]

        return {
            "company_summary": data.get("summary", ""),
            "industry": data.get("industry", ""),
            "company_employee_count": data.get("employee_count", ""),
            "company_funding": data.get("funding", ""),
            "website": website,
            "_model": result["model"],
            "_input_tokens": result["input_tokens"],
            "_output_tokens": result["output_tokens"],
            "_cost": result["cost"],
        }
