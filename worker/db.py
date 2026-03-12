"""Supabase REST API access for worker — uses HTTPS (IPv4 compatible)."""

from __future__ import annotations

from supabase import Client, create_client

from worker.config import SUPABASE_KEY, SUPABASE_URL

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def claim_leads(campaign_id: str, batch_size: int, worker_id: str) -> list[dict]:
    """Atomically claim a batch of leads for processing via RPC."""
    db = get_db()
    result = db.rpc(
        "claim_leads",
        {"p_campaign_id": campaign_id, "p_batch_size": batch_size, "p_worker_id": worker_id},
    ).execute()
    return result.data or []


def release_stale_claims(timeout_minutes: int = 30) -> int:
    """Release leads claimed by crashed workers via RPC."""
    db = get_db()
    result = db.rpc("release_stale_claims", {"p_timeout_minutes": timeout_minutes}).execute()
    return result.data if isinstance(result.data, int) else 0


def get_active_campaigns() -> list[dict]:
    """Get campaigns that have leads waiting to be processed."""
    db = get_db()

    # Get distinct campaigns with pending leads
    result = (
        db.table("leads")
        .select("campaign_id")
        .in_("pipeline_status", ["imported", "error"])
        .is_("claimed_by", "null")
        .execute()
    )

    if not result.data:
        return []

    # Deduplicate campaign IDs and count
    campaign_counts: dict[str, int] = {}
    for row in result.data:
        cid = row["campaign_id"]
        campaign_counts[cid] = campaign_counts.get(cid, 0) + 1

    # Fetch campaign details
    campaigns = []
    for cid, count in campaign_counts.items():
        c_result = db.table("campaigns").select("*").eq("id", cid).execute()
        if c_result.data:
            campaign = c_result.data[0]
            campaign["pending_count"] = count
            campaigns.append(campaign)

    return sorted(campaigns, key=lambda c: c["pending_count"], reverse=True)


def get_campaign_by_slug(slug: str) -> dict | None:
    """Get a single campaign by slug."""
    db = get_db()
    result = db.table("campaigns").select("*").eq("slug", slug).execute()
    return result.data[0] if result.data else None


def get_worker_stats() -> dict:
    """Get global processing stats."""
    db = get_db()
    result = db.table("leads").select("pipeline_status").execute()

    stats = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "disqualified": 0,
        "pushed": 0,
        "errored": 0,
        "total": 0,
    }

    for row in result.data or []:
        status = row["pipeline_status"]
        stats["total"] += 1
        if status == "imported":
            stats["pending"] += 1
        elif status == "in_progress":
            stats["processing"] += 1
        elif status in ("enriched", "email_generated"):
            stats["completed"] += 1
        elif status == "disqualified":
            stats["disqualified"] += 1
        elif status == "pushed":
            stats["pushed"] += 1
        elif status == "error":
            stats["errored"] += 1

    return stats
