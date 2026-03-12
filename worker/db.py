"""Direct Postgres access for worker — uses psycopg2 for atomic operations."""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from worker.config import DATABASE_URL

_conn = None


def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL)
        _conn.autocommit = True
    return _conn


def claim_leads(campaign_id: str, batch_size: int, worker_id: str) -> list[dict]:
    """Atomically claim a batch of leads for processing."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM claim_leads(%s, %s, %s)",
            (campaign_id, batch_size, worker_id),
        )
        return [dict(row) for row in cur.fetchall()]


def release_stale_claims(timeout_minutes: int = 30) -> int:
    """Release leads claimed by crashed workers."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT release_stale_claims(%s)", (timeout_minutes,))
        return cur.fetchone()[0]


def get_active_campaigns() -> list[dict]:
    """Get campaigns that have leads waiting to be processed."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT c.id, c.slug, c.config,
                   COUNT(l.id) FILTER (WHERE l.pipeline_status IN ('imported', 'error') AND l.claimed_by IS NULL) AS pending_count
            FROM campaigns c
            JOIN leads l ON l.campaign_id = c.id
            WHERE l.pipeline_status IN ('imported', 'error')
            AND l.claimed_by IS NULL
            GROUP BY c.id, c.slug, c.config
            HAVING COUNT(l.id) FILTER (WHERE l.pipeline_status IN ('imported', 'error') AND l.claimed_by IS NULL) > 0
            ORDER BY pending_count DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def get_campaign_by_slug(slug: str) -> dict | None:
    """Get a single campaign by slug."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM campaigns WHERE slug = %s", (slug,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_worker_stats() -> dict:
    """Get global processing stats for the worker dashboard."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE pipeline_status = 'imported') AS pending,
                COUNT(*) FILTER (WHERE pipeline_status = 'in_progress') AS processing,
                COUNT(*) FILTER (WHERE pipeline_status IN ('enriched', 'email_generated')) AS completed,
                COUNT(*) FILTER (WHERE pipeline_status = 'qualified') AS qualified,
                COUNT(*) FILTER (WHERE pipeline_status = 'disqualified') AS disqualified,
                COUNT(*) FILTER (WHERE pipeline_status = 'pushed') AS pushed,
                COUNT(*) FILTER (WHERE pipeline_status = 'error') AS errored,
                COUNT(*) AS total
            FROM leads
        """)
        return dict(cur.fetchone())


def get_campaign_queue_stats(campaign_id: str) -> list[dict]:
    """Get queue stats for a specific campaign."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM campaign_queue_stats(%s)", (campaign_id,))
        return [dict(row) for row in cur.fetchall()]
