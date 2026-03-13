"""Smartlead API client for pushing enriched leads to campaigns."""

from __future__ import annotations

import httpx

from growthpal.config import CampaignConfig, get_config
from growthpal.constants import PipelineStatus
from growthpal.db import queries as db
from growthpal.enrichments.strategy_router import get_strategy_by_id, get_strategy_config
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


def _resolve_campaign_id(
    lead: dict,
    default_campaign_id: int,
    campaign_config: CampaignConfig | None = None,
) -> int:
    """Resolve the Smartlead campaign ID for a lead.

    If the lead has a strategy_id and the strategy defines its own
    smartlead_campaign_id, use that. Otherwise fall back to default.
    """
    strategy_id = lead.get("strategy_id")
    if strategy_id and campaign_config:
        strategy = get_strategy_by_id(campaign_config, strategy_id)
        if strategy and strategy.get("smartlead_campaign_id"):
            return int(strategy["smartlead_campaign_id"])
    return default_campaign_id


async def push_leads_to_smartlead(
    campaign_slug: str,
    smartlead_campaign_id: int,
    limit: int = 500,
    campaign_config: CampaignConfig | None = None,
) -> int:
    """Push enriched leads to Smartlead campaign(s).

    When strategy routing is configured, each lead is routed to its
    strategy's Smartlead campaign. Otherwise all go to the default campaign.

    Returns:
        Number of leads pushed.
    """
    campaign = db.get_campaign(campaign_slug)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_slug}")

    # Load campaign config from DB if not provided
    if campaign_config is None and campaign.get("config"):
        campaign_config = CampaignConfig.from_dict(campaign["config"])

    leads = db.get_leads_by_status(
        campaign["id"],
        PipelineStatus.EMAIL_GENERATED,
        limit=limit,
    )

    if not leads:
        log.info("No leads ready to push.")
        return 0

    pushed = 0
    campaign_counts: dict[int, int] = {}  # Track pushes per Smartlead campaign

    for lead in leads:
        try:
            target_campaign_id = _resolve_campaign_id(
                lead, smartlead_campaign_id, campaign_config
            )

            custom_fields = {}
            if lead.get("email_subject"):
                custom_fields["email_subject"] = lead["email_subject"]
            if lead.get("email_body"):
                custom_fields["email_body"] = lead["email_body"]
            if lead.get("company_summary"):
                custom_fields["company_summary"] = lead["company_summary"]

            await add_lead_to_campaign(
                campaign_id=target_campaign_id,
                email=lead.get("email", ""),
                first_name=lead.get("first_name", ""),
                last_name=lead.get("last_name", ""),
                company_name=lead.get("company_name", ""),
                custom_fields=custom_fields,
            )

            db.update_lead_status(lead["id"], PipelineStatus.PUSHED)
            pushed += 1
            campaign_counts[target_campaign_id] = campaign_counts.get(target_campaign_id, 0) + 1

            if pushed % 50 == 0:
                log.info(f"Pushed {pushed}/{len(leads)} leads...")

        except Exception as e:
            log.error(f"Failed to push lead {lead.get('email')}: {e}")
            db.update_lead_status(lead["id"], PipelineStatus.ERROR, error_message=f"Smartlead push: {e}")

    # Log per-campaign breakdown
    if len(campaign_counts) > 1:
        breakdown = ", ".join(f"campaign {cid}: {cnt}" for cid, cnt in campaign_counts.items())
        log.info(f"Pushed {pushed} leads across Smartlead campaigns: {breakdown}")
    else:
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
