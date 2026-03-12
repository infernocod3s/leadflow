"""Lead processing worker — polls for leads and runs the enrichment pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from worker.config import (
    BATCH_SIZE,
    CAMPAIGN_SLUGS,
    CONCURRENCY,
    POLL_INTERVAL,
    STALE_CLAIM_TIMEOUT,
    WORKER_ID,
)
from worker.db import claim_leads, get_active_campaigns, get_campaign_by_slug, release_stale_claims
from worker.stats import stats

log = logging.getLogger("worker.processor")


async def process_batch_for_campaign(campaign_id: str, campaign_slug: str) -> dict:
    """Claim and process a batch of leads for a campaign."""
    # Import here to avoid circular imports and ensure registration
    import growthpal.enrichments  # noqa: F401
    from growthpal.config import CampaignConfig
    from growthpal.pipeline.batch import process_batch
    from growthpal.pipeline.registry import build_pipeline
    from growthpal.utils.cost_tracker import CostTracker

    # Claim leads atomically
    leads = claim_leads(campaign_id, BATCH_SIZE, WORKER_ID)
    if not leads:
        return {"processed": 0, "qualified": 0, "disqualified": 0, "errors": 0}

    log.info(f"[{campaign_slug}] Claimed {len(leads)} leads")
    stats.batches_processed += 1

    # Load campaign config if available
    config_path = Path("configs") / f"{campaign_slug}.yaml"
    campaign_config = CampaignConfig()
    if config_path.exists():
        campaign_config = CampaignConfig.from_yaml(config_path)

    # Build pipeline and process
    steps = build_pipeline(["all"], campaign_config)
    cost_tracker = CostTracker()

    batch_stats = await process_batch(
        leads=leads,
        steps=steps,
        campaign_config=campaign_config,
        cost_tracker=cost_tracker,
        concurrency=CONCURRENCY,
    )

    # Update worker stats
    stats.leads_processed += batch_stats["processed"]
    stats.leads_qualified += batch_stats["qualified"]
    stats.leads_disqualified += batch_stats["disqualified"]
    stats.leads_errored += batch_stats["errors"]
    stats.total_cost += cost_tracker.total_cost

    log.info(
        f"[{campaign_slug}] Batch done: "
        f"{batch_stats['processed']} processed, "
        f"{batch_stats['qualified']} qualified, "
        f"{batch_stats['errors']} errors, "
        f"${cost_tracker.total_cost:.4f} cost"
    )

    return batch_stats


async def worker_loop():
    """Main worker loop — continuously polls for and processes leads."""
    log.info(f"Worker {WORKER_ID} starting (batch={BATCH_SIZE}, concurrency={CONCURRENCY})")

    # Parse campaign filter
    target_slugs = [s.strip() for s in CAMPAIGN_SLUGS.split(",") if s.strip()] if CAMPAIGN_SLUGS else []
    if target_slugs:
        log.info(f"Targeting campaigns: {target_slugs}")
    else:
        log.info("Processing all campaigns with pending leads")

    stale_check_interval = 300  # Check for stale claims every 5 minutes
    last_stale_check = 0

    while True:
        try:
            # Periodically release stale claims from crashed workers
            now = time.monotonic()
            if now - last_stale_check > stale_check_interval:
                released = release_stale_claims(STALE_CLAIM_TIMEOUT)
                if released > 0:
                    log.info(f"Released {released} stale claims")
                last_stale_check = now

            # Find campaigns with pending leads
            if target_slugs:
                campaigns = []
                for slug in target_slugs:
                    c = get_campaign_by_slug(slug)
                    if c:
                        campaigns.append(c)
            else:
                campaigns = get_active_campaigns()

            if not campaigns:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Process each campaign
            total_processed = 0
            for campaign in campaigns:
                try:
                    result = await process_batch_for_campaign(
                        campaign_id=str(campaign["id"]),
                        campaign_slug=campaign["slug"],
                    )
                    total_processed += result["processed"]
                except Exception as e:
                    log.error(f"Error processing campaign {campaign['slug']}: {e}")
                    stats.errors.append(f"{campaign['slug']}: {str(e)[:200]}")

            # If nothing was processed, wait before polling again
            if total_processed == 0:
                await asyncio.sleep(POLL_INTERVAL)

        except Exception as e:
            log.error(f"Worker loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)
