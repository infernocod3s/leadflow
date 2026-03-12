"""Layer 0: Company cache — deduplicates research across leads.

Includes in-memory LRU (50k domains) and batch Supabase operations.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from growthpal.db.client import get_db
from growthpal.utils.logger import get_logger

log = get_logger(__name__)

# ── In-memory LRU cache ────────────────────────────────────────────────────
_MEMORY_CACHE_MAX = 50_000
_memory_cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()  # domain -> (data, timestamp)


def _memory_get(domain: str, max_age_hours: int = 168) -> dict | None:
    """Get from in-memory LRU. Returns None if missing or stale."""
    entry = _memory_cache.get(domain)
    if entry is None:
        return None
    data, ts = entry
    age_hours = (time.time() - ts) / 3600
    if age_hours > max_age_hours:
        return None
    # Move to end (most recently used)
    _memory_cache.move_to_end(domain)
    return data


def _memory_set(domain: str, data: dict) -> None:
    """Store in in-memory LRU, evicting oldest if full."""
    _memory_cache[domain] = (data, time.time())
    _memory_cache.move_to_end(domain)
    while len(_memory_cache) > _MEMORY_CACHE_MAX:
        _memory_cache.popitem(last=False)


def get_cached_company(domain: str, max_age_hours: int = 168) -> dict | None:
    """Get cached company data if fresh enough.

    Checks in-memory LRU first, then Supabase.
    """
    # Check in-memory LRU first
    mem = _memory_get(domain, max_age_hours)
    if mem is not None:
        log.debug(f"Memory cache hit for {domain}")
        return mem

    db = get_db()
    result = db.table("company_cache").select("*").eq("domain", domain).execute()

    if not result.data:
        return None

    row = result.data[0]

    # Check freshness
    updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600

    if age_hours > max_age_hours:
        log.debug(f"Cache stale for {domain} (age={age_hours:.0f}h > {max_age_hours}h)")
        return None

    log.debug(f"Cache hit for {domain} (age={age_hours:.0f}h, quality={row.get('data_quality_score', 0)})")
    # Populate memory cache
    _memory_set(domain, row)
    return row


def _serialize_row(domain: str, data: dict[str, Any]) -> dict:
    """Prepare a row for Supabase upsert — strip underscored keys, serialize JSONB."""
    row = {
        "domain": domain,
        **{k: v for k, v in data.items() if not k.startswith("_")},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for field in ("products", "tech_stack", "signals", "funding_signal",
                  "hiring_signal", "social_links", "json_ld_data", "layer_costs"):
        if field in row and isinstance(row[field], (dict, list)):
            row[field] = json.dumps(row[field])
    return row


def upsert_company_cache(domain: str, data: dict[str, Any]) -> dict:
    """Insert or update company cache entry."""
    db = get_db()
    row = _serialize_row(domain, data)
    result = db.table("company_cache").upsert(row, on_conflict="domain").execute()
    out = result.data[0] if result.data else {}
    # Update in-memory cache
    _memory_set(domain, {**data, "domain": domain})
    return out


def get_cached_signals(domain: str, max_age_hours: int = 72) -> dict | None:
    """Get cached signal data if fresh enough.

    Args:
        domain: Normalized domain
        max_age_hours: Max signal cache age (default 3 days)
    """
    db = get_db()
    result = (
        db.table("company_cache")
        .select("signals, tech_stack, funding_signal, hiring_signal, signals_at")
        .eq("domain", domain)
        .execute()
    )

    if not result.data:
        return None

    row = result.data[0]
    signals_at = row.get("signals_at")
    if not signals_at:
        return None

    updated = datetime.fromisoformat(signals_at.replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600

    if age_hours > max_age_hours:
        return None

    return row


# ── Batch operations ───────────────────────────────────────────────────────


def _chunks(items: list, size: int):
    """Yield successive chunks from items."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def batch_get_cached_companies(
    domains: list[str],
    max_age_hours: int = 168,
) -> dict[str, dict]:
    """Batch cache lookup — returns {domain: data} for all hits.

    1. Checks in-memory LRU first
    2. Fetches remaining from Supabase in one `.in_()` query per 500-chunk
    """
    result: dict[str, dict] = {}
    remaining: list[str] = []

    # Memory cache pass
    for d in domains:
        mem = _memory_get(d, max_age_hours)
        if mem is not None:
            result[d] = mem
        else:
            remaining.append(d)

    if not remaining:
        log.info(f"[batch_cache] {len(result)} memory hits, 0 DB lookups")
        return result

    # Supabase batch lookup in chunks of 500
    db = get_db()
    cutoff = datetime.now(timezone.utc)

    for chunk in _chunks(remaining, 500):
        try:
            resp = (
                db.table("company_cache")
                .select("*")
                .in_("domain", chunk)
                .execute()
            )
            for row in resp.data:
                domain = row["domain"]
                updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                age_hours = (cutoff - updated_at).total_seconds() / 3600
                if age_hours <= max_age_hours:
                    quality = row.get("data_quality_score", 0.0)
                    result[domain] = row
                    _memory_set(domain, row)
        except Exception as e:
            log.warning(f"[batch_cache] Supabase lookup failed for chunk: {e}")

    log.info(f"[batch_cache] {len(result)} hits ({len(result) - len(remaining) + len(remaining)} memory, {len(result)} total) out of {len(domains)} domains")
    return result


def batch_upsert_company_cache(entries: dict[str, dict[str, Any]]) -> int:
    """Batch upsert {domain: data} to company_cache in 500-row chunks.

    Returns number of rows upserted.
    """
    if not entries:
        return 0

    db = get_db()
    rows = [_serialize_row(domain, data) for domain, data in entries.items()]
    total = 0

    for chunk in _chunks(rows, 500):
        try:
            db.table("company_cache").upsert(chunk, on_conflict="domain").execute()
            total += len(chunk)
        except Exception as e:
            log.warning(f"[batch_cache] Batch upsert failed for chunk of {len(chunk)}: {e}")

    # Update memory cache
    for domain, data in entries.items():
        _memory_set(domain, {**data, "domain": domain})

    log.info(f"[batch_cache] Upserted {total} rows")
    return total
