"""All database operations for GrowthPal."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from growthpal.constants import PipelineStatus
from growthpal.db.client import get_db
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


# ── Clients ──────────────────────────────────────────────────────────────────


def get_or_create_client(name: str) -> dict:
    db = get_db()
    result = db.table("clients").select("*").eq("name", name).execute()
    if result.data:
        return result.data[0]
    result = db.table("clients").insert({"name": name}).execute()
    return result.data[0]


# ── Campaigns ────────────────────────────────────────────────────────────────


def get_campaign(slug: str) -> dict | None:
    db = get_db()
    result = db.table("campaigns").select("*").eq("slug", slug).execute()
    return result.data[0] if result.data else None


def create_campaign(client_id: str, slug: str, config: dict | None = None) -> dict:
    db = get_db()
    result = db.table("campaigns").insert({
        "client_id": client_id,
        "slug": slug,
        "config": config or {},
    }).execute()
    return result.data[0]


def get_or_create_campaign(client_name: str, slug: str, config: dict | None = None) -> dict:
    campaign = get_campaign(slug)
    if campaign:
        return campaign
    client = get_or_create_client(client_name)
    return create_campaign(client["id"], slug, config)


def list_campaigns() -> list[dict]:
    db = get_db()
    result = db.table("campaigns").select("*, clients(name)").order("created_at", desc=True).execute()
    return result.data


# ── Leads ────────────────────────────────────────────────────────────────────


def insert_leads(leads: list[dict]) -> list[dict]:
    if not leads:
        return []
    db = get_db()
    result = db.table("leads").insert(leads).execute()
    return result.data


def get_leads_by_status(
    campaign_id: str,
    status: PipelineStatus | list[PipelineStatus],
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    db = get_db()
    q = db.table("leads").select("*").eq("campaign_id", campaign_id)
    if isinstance(status, list):
        q = q.in_("pipeline_status", [s.value for s in status])
    else:
        q = q.eq("pipeline_status", status.value)
    result = q.order("created_at").range(offset, offset + limit - 1).execute()
    return result.data


def update_lead(lead_id: str, data: dict) -> dict:
    db = get_db()
    result = db.table("leads").update(data).eq("id", lead_id).execute()
    return result.data[0] if result.data else {}


def update_lead_status(lead_id: str, status: PipelineStatus, **extra: Any) -> dict:
    data: dict[str, Any] = {"pipeline_status": status.value}
    if status == PipelineStatus.ERROR and "error_message" in extra:
        data["error_message"] = extra["error_message"]
    if status == PipelineStatus.PUSHED:
        data["pushed_at"] = datetime.now(timezone.utc).isoformat()
    if status in (PipelineStatus.ENRICHED, PipelineStatus.EMAIL_GENERATED):
        data["enriched_at"] = datetime.now(timezone.utc).isoformat()
    data.update({k: v for k, v in extra.items() if k not in ("error_message",)})
    return update_lead(lead_id, data)


def get_lead_by_email(email: str, campaign_id: str | None = None) -> dict | None:
    db = get_db()
    q = db.table("leads").select("*").eq("raw_email", email)
    if campaign_id:
        q = q.eq("campaign_id", campaign_id)
    result = q.execute()
    return result.data[0] if result.data else None


def get_campaign_lead_counts(campaign_id: str) -> dict[str, int]:
    """Get lead counts grouped by pipeline status."""
    db = get_db()
    result = db.table("leads").select("pipeline_status").eq("campaign_id", campaign_id).execute()
    counts: dict[str, int] = {}
    for row in result.data:
        status = row["pipeline_status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


# ── Enrichment Logs ──────────────────────────────────────────────────────────


def log_enrichment(
    lead_id: str,
    campaign_id: str,
    step_name: str,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
    duration_ms: int = 0,
    success: bool = True,
    error_message: str | None = None,
) -> dict:
    db = get_db()
    result = db.table("enrichment_logs").insert({
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "step_name": step_name,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
        "duration_ms": duration_ms,
        "success": success,
        "error_message": error_message,
    }).execute()
    return result.data[0] if result.data else {}


# ── Pipeline Runs ────────────────────────────────────────────────────────────


def create_pipeline_run(campaign_id: str, total_leads: int, config: dict | None = None) -> dict:
    db = get_db()
    result = db.table("pipeline_runs").insert({
        "campaign_id": campaign_id,
        "total_leads": total_leads,
        "config": config or {},
    }).execute()
    return result.data[0]


def update_pipeline_run(run_id: str, data: dict) -> dict:
    db = get_db()
    result = db.table("pipeline_runs").update(data).eq("id", run_id).execute()
    return result.data[0] if result.data else {}


# ── Cost Summaries ───────────────────────────────────────────────────────────


def get_campaign_costs(campaign_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("enrichment_logs")
        .select("step_name, model, success")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    # Aggregate in Python for simplicity
    steps: dict[str, dict] = {}
    for row in result.data:
        step = row["step_name"]
        if step not in steps:
            steps[step] = {"calls": 0, "success": 0, "failures": 0}
        steps[step]["calls"] += 1
        if row["success"]:
            steps[step]["success"] += 1
        else:
            steps[step]["failures"] += 1
    return [{"step": k, **v} for k, v in steps.items()]


def get_campaign_total_cost(campaign_id: str) -> float:
    db = get_db()
    result = (
        db.table("enrichment_logs")
        .select("cost")
        .eq("campaign_id", campaign_id)
        .execute()
    )
    return sum(row["cost"] for row in result.data)
