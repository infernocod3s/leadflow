"""Email verification — Reoon → BounceBan waterfall.

Only runs on emails from Prospeo/TryKitt (not BetterContact, which self-verifies).

Order:
1. Reoon — if confident (valid/invalid), use that
2. BounceBan — fallback if Reoon returns uncertain/risky
"""

from __future__ import annotations

from typing import Any

from leadflow.config import CampaignConfig
from leadflow.constants import PipelineStatus
from leadflow.enrichments.base import EnrichmentStep
from leadflow.integrations import bounceban, reoon
from leadflow.pipeline.registry import register
from leadflow.utils.logger import get_logger

log = get_logger(__name__)


@register
class EmailVerificationStep(EnrichmentStep):
    """Verify emails: Reoon → BounceBan (if uncertain).

    Acts as a GATE — invalid emails get disqualified.
    Skips verification for BetterContact emails (already verified).
    """

    name = "email_verification"
    is_gate = True

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        email = lead.get("email") or ""
        if not email:
            return {"_email_verified": False, "_verification_skip": "no_email"}

        # Skip if BetterContact (self-verifying) or AI-Ark verified
        needs_verification = lead.get("_needs_verification", True)
        if not needs_verification:
            log.debug(f"[email_verification] Skipping {email} — pre-verified")
            return {"_email_verified": True}

        # 1. Reoon
        try:
            reoon_result = await reoon.verify_email(email)

            if reoon_result.get("confident"):
                is_valid = reoon_result.get("valid", False)
                log.info(f"[email_verification] Reoon: {email} → {'valid' if is_valid else 'invalid'}")
                return {
                    "_email_verified": is_valid,
                    "_verification_provider": "reoon",
                    "_verification_status": reoon_result.get("status", "unknown"),
                }
        except Exception as e:
            log.warning(f"[email_verification] Reoon failed for {email}: {e}")

        # 2. BounceBan (fallback for uncertain results)
        try:
            bb_result = await bounceban.verify_email(email)
            is_valid = bb_result.get("valid", False)
            log.info(f"[email_verification] BounceBan: {email} → {'valid' if is_valid else 'invalid'}")
            return {
                "_email_verified": is_valid,
                "_verification_provider": "bounceban",
                "_verification_status": bb_result.get("status", "unknown"),
            }
        except Exception as e:
            log.warning(f"[email_verification] BounceBan failed for {email}: {e}")

        # Both failed — treat as risky but don't disqualify
        log.warning(f"[email_verification] Both verifiers failed for {email} — treating as unverified")
        return {"_email_verified": True, "_verification_provider": "none"}
