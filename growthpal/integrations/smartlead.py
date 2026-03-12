"""Smartlead API client for pushing enriched leads to campaigns."""

from __future__ import annotations

import httpx

from growthpal.config import get_config
from growthpal.constants import PipelineStatus
from growthpal.db import queries as db
from growthpal.utils.logger import get_logger
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

BASE_URL = "https://server.smartlead.ai/api/v1"

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _api_key() -> str:
    return get_config().smartlead_api_key


@async_retry(max_retries=3, exceptions=(httpx.HTTPError,))
async def add_lead_to_campaign(
    campaign_id: int,
    email: str,
    first_name: str = "",
    last_name: str = "",
    company_name: str = "",
    custom_fields: dict | None = None,
) -> dict:
    """Add a single lead to a Smartlead campaign."""
    client = _get_client()

    payload = {
        "api_key": _api_key(),
        "lead_list": [
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company_name,
                **(custom_fields or {}),
            }
        ],
        "settings": {
            "ignore_global_block_list": False,
            "ignore_unsubscribe_list": False,
        },
    }

    response = await client.post(
        f"{BASE_URL}/campaigns/{campaign_id}/leads",
        json=payload,
        params={"api_key": _api_key()},
    )
    response.raise_for_status()
    return response.json()


async def push_leads_to_smartlead(
    campaign_slug: str,
    smartlead_campaign_id: int,
    limit: int = 500,
) -> int:
    """Push enriched leads to Smartlead campaign.

    Returns:
        Number of leads pushed.
    """
    campaign = db.get_campaign(campaign_slug)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_slug}")

    leads = db.get_leads_by_status(
        campaign["id"],
        PipelineStatus.EMAIL_GENERATED,
        limit=limit,
    )

    if not leads:
        log.info("No leads ready to push.")
        return 0

    pushed = 0
    for lead in leads:
        try:
            custom_fields = {}
            if lead.get("email_subject"):
                custom_fields["email_subject"] = lead["email_subject"]
            if lead.get("email_body"):
                custom_fields["email_body"] = lead["email_body"]
            if lead.get("company_summary"):
                custom_fields["company_summary"] = lead["company_summary"]

            await add_lead_to_campaign(
                campaign_id=smartlead_campaign_id,
                email=lead.get("email", ""),
                first_name=lead.get("first_name", ""),
                last_name=lead.get("last_name", ""),
                company_name=lead.get("company_name", ""),
                custom_fields=custom_fields,
            )

            db.update_lead_status(lead["id"], PipelineStatus.PUSHED)
            pushed += 1

            if pushed % 50 == 0:
                log.info(f"Pushed {pushed}/{len(leads)} leads...")

        except Exception as e:
            log.error(f"Failed to push lead {lead.get('email')}: {e}")
            db.update_lead_status(lead["id"], PipelineStatus.ERROR, error_message=f"Smartlead push: {e}")

    log.info(f"Pushed {pushed} leads to Smartlead campaign {smartlead_campaign_id}")
    return pushed


@async_retry(max_retries=2, exceptions=(httpx.HTTPError,))
async def get_campaign_info(campaign_id: int) -> dict:
    """Get Smartlead campaign details."""
    client = _get_client()
    response = await client.get(
        f"{BASE_URL}/campaigns/{campaign_id}",
        params={"api_key": _api_key()},
    )
    response.raise_for_status()
    return response.json()
