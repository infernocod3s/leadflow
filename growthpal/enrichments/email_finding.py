"""Email finding — waterfall across Prospeo → TryKitt → BetterContact.

Order:
1. Prospeo (free credits from deal — use first)
2. TryKitt (fallback)
3. BetterContact (final fallback — self-verifies, also returns phone)

Emails from Prospeo and TryKitt need separate verification.
BetterContact emails are pre-verified.
"""

from __future__ import annotations

import json
from typing import Any

from growthpal.config import CampaignConfig
from growthpal.enrichments.base import EnrichmentStep
from growthpal.integrations import bettercontact, prospeo, trykitt
from growthpal.pipeline.registry import register
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


def _get_domain(lead: dict) -> str:
    """Extract domain from website or email."""
    website = lead.get("website") or lead.get("raw_website") or ""
    if website:
        domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        return domain

    # Try to extract from existing email
    email = lead.get("raw_email") or ""
    if "@" in email:
        return email.split("@")[1]

    return ""


@register
class EmailFindingStep(EnrichmentStep):
    """Waterfall email finding: Prospeo → TryKitt → BetterContact.

    Runs after ICP qualification (only find emails for qualified leads).
    """

    name = "email_finding"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        # Skip if we already have a verified email from AI-Ark
        existing_email = lead.get("email") or lead.get("raw_email") or ""
        if existing_email and lead.get("raw_extra", {}).get("aiark_verified"):
            log.debug(f"[email_finding] Skipping — already have AI-Ark verified email")
            return {"_needs_verification": False}

        first_name = lead.get("first_name") or lead.get("raw_first_name") or ""
        last_name = lead.get("last_name") or lead.get("raw_last_name") or ""
        domain = _get_domain(lead)
        linkedin = lead.get("raw_linkedin") or lead.get("linkedin_url") or ""

        if not domain and not linkedin:
            log.warning(f"[email_finding] No domain or LinkedIn URL — cannot find email")
            return {}

        result: dict[str, Any] = {}
        needs_verification = True

        # 1. Prospeo (free credits — try first)
        try:
            if linkedin:
                prospeo_result = await prospeo.find_email_by_linkedin(linkedin)
            else:
                prospeo_result = await prospeo.find_email(first_name, last_name, domain)

            if prospeo_result.get("found"):
                result["email"] = prospeo_result["email"]
                result["_email_provider"] = "prospeo"
                log.info(f"[email_finding] Prospeo found: {result['email']}")
                return {**result, "_needs_verification": True}
        except Exception as e:
            log.warning(f"[email_finding] Prospeo failed: {e}")

        # 2. TryKitt (fallback)
        if first_name and last_name and domain:
            try:
                trykitt_result = await trykitt.find_email(first_name, last_name, domain)

                if trykitt_result.get("found"):
                    result["email"] = trykitt_result["email"]
                    result["_email_provider"] = "trykitt"
                    log.info(f"[email_finding] TryKitt found: {result['email']}")
                    return {**result, "_needs_verification": True}
            except Exception as e:
                log.warning(f"[email_finding] TryKitt failed: {e}")

        # 3. BetterContact (final fallback — self-verifies)
        try:
            bc_result = await bettercontact.find_email(
                first_name, last_name, domain, linkedin_url=linkedin
            )

            if bc_result.get("found"):
                result["email"] = bc_result["email"]
                result["_email_provider"] = "bettercontact"
                if bc_result.get("phone"):
                    result["phone"] = bc_result["phone"]
                log.info(f"[email_finding] BetterContact found: {result['email']}")
                # BetterContact self-verifies — no separate verification needed
                return {**result, "_needs_verification": False}
        except Exception as e:
            log.warning(f"[email_finding] BetterContact failed: {e}")

        log.info(f"[email_finding] No email found across all providers")
        return {}
