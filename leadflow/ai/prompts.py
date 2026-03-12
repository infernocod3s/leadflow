"""All prompt templates for enrichment steps."""


def company_research_prompt(website_content: str, company_name: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a B2B company research analyst. Analyze the website content and "
                "produce a concise company summary. Respond in JSON with these fields:\n"
                '- "summary": 2-3 sentence company description\n'
                '- "industry": primary industry\n'
                '- "employee_count": estimated range (e.g. "50-200")\n'
                '- "funding": any funding info found, or "unknown"\n'
                '- "products": list of main products/services\n'
                '- "target_market": who they sell to\n'
            ),
        },
        {
            "role": "user",
            "content": f"Company: {company_name}\n\nWebsite content:\n{website_content[:6000]}",
        },
    ]


def icp_qualification_prompt(
    company_summary: str,
    icp_description: str,
    target_industries: list[str],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a lead qualification expert. Determine if this company matches the "
                "Ideal Customer Profile (ICP). Respond in JSON:\n"
                '- "qualified": true/false\n'
                '- "reason": 1-2 sentence explanation\n'
                '- "confidence": 0.0-1.0\n'
                '- "matching_criteria": list of matched ICP criteria\n'
            ),
        },
        {
            "role": "user",
            "content": (
                f"ICP Description:\n{icp_description}\n\n"
                f"Target Industries: {', '.join(target_industries)}\n\n"
                f"Company Info:\n{company_summary}"
            ),
        },
    ]


def job_title_cleaning_prompt(raw_title: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Clean and normalize this job title. Fix typos, expand abbreviations, "
                "standardize formatting. Respond in JSON:\n"
                '- "clean_title": normalized title\n'
                '- "seniority": one of [C-Suite, VP, Director, Manager, Senior, Mid, Junior, Unknown]\n'
                '- "department": one of [Engineering, Marketing, Sales, Operations, Finance, HR, Product, Design, Executive, Other]\n'
            ),
        },
        {"role": "user", "content": f"Job title: {raw_title}"},
    ]


def name_cleaning_prompt(
    first_name: str, last_name: str, company_name: str
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Clean and normalize these name fields. Fix capitalization, remove titles/suffixes, "
                "handle encoding issues. Respond in JSON:\n"
                '- "first_name": cleaned first name\n'
                '- "last_name": cleaned last name\n'
                '- "company_name": cleaned company name (remove Inc, LLC, etc. from display name)\n'
            ),
        },
        {
            "role": "user",
            "content": (
                f"First name: {first_name}\n"
                f"Last name: {last_name}\n"
                f"Company: {company_name}"
            ),
        },
    ]


def job_title_icp_prompt(
    job_title: str, target_titles: list[str]
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Determine if this job title is relevant to the target persona. "
                "Consider semantic similarity, not just exact matches. Respond in JSON:\n"
                '- "relevant": true/false\n'
                '- "reason": brief explanation\n'
                '- "closest_match": which target title it\'s closest to, or null\n'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Job title: {job_title}\n\n"
                f"Target titles:\n" + "\n".join(f"- {t}" for t in target_titles)
            ),
        },
    ]


def signal_detection_prompt(
    company_summary: str, website_content: str
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Analyze this company for sales-relevant signals. Respond in JSON:\n"
                '- "tech_stack": list of technologies detected\n'
                '- "signals": list of objects with {type, detail, relevance_score}\n'
                '  Signal types: hiring, funding, expansion, product_launch, partnership, pain_point\n'
                '- "funding_signal": {stage, amount, date} or null\n'
                '- "hiring_signal": {roles, count, departments} or null\n'
                '- "summary": 1-2 sentence signal summary for the SDR\n'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Company Summary:\n{company_summary}\n\n"
                f"Website Content:\n{website_content[:4000]}"
            ),
        },
    ]


def email_generation_prompt(
    lead: dict,
    campaign_config: dict,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an expert cold email copywriter for B2B outbound sales. "
                "Write a personalized cold email. Respond in JSON:\n"
                '- "subject": email subject line (under 50 chars, no clickbait)\n'
                '- "body": email body (under 150 words, conversational tone)\n'
                '- "variant": "A" (always A for first version)\n\n'
                "Rules:\n"
                "- Mention something specific about their company\n"
                "- Connect their situation to the sender's value prop\n"
                "- Keep it short and scannable\n"
                "- End with a soft CTA\n"
                "- No fake familiarity or over-the-top flattery\n"
                "- Use {{first_name}} as merge tag for their name\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Lead info:\n"
                f"- Name: {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
                f"- Title: {lead.get('job_title', '')}\n"
                f"- Company: {lead.get('company_name', '')}\n"
                f"- Company Summary: {lead.get('company_summary', '')}\n"
                f"- Signals: {lead.get('signals', {})}\n\n"
                f"Sender info:\n"
                f"- Name: {campaign_config.get('sender_name', '')}\n"
                f"- Company: {campaign_config.get('sender_company', '')}\n"
                f"- Value prop: {campaign_config.get('sender_value_prop', '')}\n"
                f"- CTA: {campaign_config.get('email_cta', '')}\n"
                f"- Tone: {campaign_config.get('email_tone', 'professional')}\n"
            ),
        },
    ]
