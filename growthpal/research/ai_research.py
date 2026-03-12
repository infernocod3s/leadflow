"""Layer 4: AI-powered research — search + scrape + AI synthesis.

Cost: ~$0.008/lead (Serper search + Gemini Flash Lite analysis)
Only triggered if layers 0-3 don't meet quality threshold.
"""

from __future__ import annotations

from typing import Any

from growthpal.ai.router import chat_json
from growthpal.constants import Model
from growthpal.research.extractors import compute_data_quality_score
from growthpal.scrapers.website import scrape_website
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


async def _search_company(domain: str, company_name: str, search_provider: str = "serper") -> dict:
    """Dispatch to the configured search provider."""
    if search_provider == "tavily":
        from growthpal.research.tavily import search_company_info
    else:
        from growthpal.research.serper import search_company_info
    return await search_company_info(domain, company_name)

COMPANY_ANALYSIS_PROMPT = """You are a B2B company research analyst. Analyze the provided information about a company and extract structured data.

Company domain: {domain}
Company name (if known): {company_name}

Available information:
{context}

Return a JSON object with these fields (use null for unknown):
{{
    "company_name": "official company name",
    "description": "1-2 sentence description of what the company does",
    "industry": "primary industry (e.g. SaaS, Fintech, Healthcare, E-commerce)",
    "employee_count": "approximate headcount (e.g. '50-100', '1000+')",
    "funding": "funding info if available (e.g. 'Series B, $50M')",
    "products": ["list of main products/services"],
    "target_market": "who they sell to (e.g. 'SMB', 'Enterprise', 'Consumer')",
    "tech_stack": ["detected technologies"],
    "signals": ["notable business signals - growth, hiring, product launches, etc."]
}}"""


async def ai_research(
    domain: str,
    company_name: str = "",
    existing_data: dict | None = None,
    model: str = Model.GEMINI_FLASH_LITE,
    search_provider: str = "serper",
) -> dict[str, Any]:
    """Layer 4: AI-powered company research using search + synthesis.

    Uses Serper for web search, then AI to synthesize findings into structured data.
    """
    result: dict[str, Any] = dict(existing_data or {})
    result["_layer"] = 4
    total_cost = 0.0

    # Step 1: Web search for company info
    search_name = company_name or result.get("company_name", "") or domain.split(".")[0]

    try:
        search_results = await _search_company(domain, search_name, search_provider)
        total_cost += search_results.get("cost", 0.0)
    except Exception as e:
        log.warning(f"Layer 4: Search failed for {domain} ({search_provider}): {e}")
        search_results = {"results": []}

    # Step 2: Build context from search results + existing data
    context_parts = []

    # Add existing data as context
    if existing_data:
        for key in ("company_name", "description", "industry", "employee_count",
                     "email_provider", "tech_stack", "products"):
            val = existing_data.get(key)
            if val:
                context_parts.append(f"{key}: {val}")

    # Add scraped text from Layer 3
    scraped_text = result.pop("_scraped_text", "")
    if scraped_text:
        context_parts.append(f"Website content:\n{scraped_text[:3000]}")

    # Add search results
    for sr in search_results.get("results", [])[:6]:
        snippet = sr.get("snippet", "")
        title = sr.get("title", "")
        if sr.get("_type") == "knowledge_graph":
            kg = sr.get("_data", {})
            kg_info = []
            for k in ("description", "type", "founded", "headquarters", "employees", "revenue"):
                if kg.get(k):
                    kg_info.append(f"{k}: {kg[k]}")
            if kg_info:
                context_parts.append(f"Knowledge Graph: {'; '.join(kg_info)}")
        elif snippet:
            context_parts.append(f"[{title}] {snippet}")

    # Step 3: Scrape a top search result page for more data
    for sr in search_results.get("results", [])[:2]:
        link = sr.get("link", "")
        if link and domain not in link:
            try:
                extra_text = await scrape_website(link)
                if extra_text:
                    context_parts.append(f"From {link}:\n{extra_text[:2000]}")
                break
            except Exception:
                continue

    if not context_parts:
        log.debug(f"Layer 4: No context gathered for {domain}")
        result["data_quality_score"] = compute_data_quality_score(result)
        result["_cost"] = total_cost
        return result

    # Step 4: AI synthesis
    context = "\n\n".join(context_parts)
    prompt = COMPANY_ANALYSIS_PROMPT.format(
        domain=domain,
        company_name=search_name,
        context=context[:6000],
    )

    messages = [
        {"role": "system", "content": "You are a B2B company research analyst. Return JSON only."},
        {"role": "user", "content": prompt},
    ]

    try:
        ai_result = await chat_json(messages, model=model, max_tokens=600)
        total_cost += ai_result.get("cost", 0.0)
        data = ai_result.get("data", {})

        # Merge AI results (don't overwrite existing good data)
        for key, value in data.items():
            if value and (value != "null") and not result.get(key):
                result[key] = value

        # Store AI token usage for logging
        result["_input_tokens"] = ai_result.get("input_tokens", 0)
        result["_output_tokens"] = ai_result.get("output_tokens", 0)
        result["_model"] = model

    except Exception as e:
        log.warning(f"Layer 4: AI synthesis failed for {domain}: {e}")

    result["data_quality_score"] = compute_data_quality_score(result)
    result["_cost"] = total_cost
    return result
