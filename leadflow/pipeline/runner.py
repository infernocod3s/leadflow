"""Pipeline orchestrator — coordinates batch processing across leads."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from leadflow.config import CampaignConfig
from leadflow.constants import DEFAULT_BATCH_SIZE, PipelineStatus
from leadflow.db import queries as db
from leadflow.pipeline.batch import process_batch
from leadflow.pipeline.registry import build_pipeline
from leadflow.utils.cost_tracker import CostTracker
from leadflow.utils.logger import get_logger
from leadflow.utils.progress import LiveDashboard, PipelineProgress

log = get_logger(__name__)


async def run_pipeline(
    campaign_slug: str,
    step_names: list[str] | None = None,
    concurrency: int = 20,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    campaign_config: CampaignConfig | None = None,
) -> dict:
    """Run the enrichment pipeline for a campaign."""
    # Get campaign
    campaign = db.get_campaign(campaign_slug)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_slug}")

    campaign_id = campaign["id"]

    # Create campaign config if not provided
    if campaign_config is None:
        campaign_config = CampaignConfig()

    # Resolve steps (includes custom AI + Deepline if configured)
    steps = build_pipeline(step_names or ["all"], campaign_config)
    step_str = ", ".join(s.name for s in steps)
    log.info(f"Pipeline steps: {step_str}")

    # Create pipeline run record
    cost_tracker = CostTracker()

    # Determine which leads to process
    fetch_statuses = [PipelineStatus.IMPORTED, PipelineStatus.ERROR]
    total_stats = {"processed": 0, "qualified": 0, "disqualified": 0, "errors": 0, "batches": 0}

    # Count total leads
    all_leads = db.get_leads_by_status(campaign_id, fetch_statuses, limit=999999)
    total_count = len(all_leads)

    if total_count == 0:
        log.info("No leads to process.")
        return {"total": 0, **total_stats, "cost": 0.0}

    run = db.create_pipeline_run(campaign_id, total_count, {
        "steps": [s.name for s in steps],
        "concurrency": concurrency,
        "dry_run": dry_run,
    })

    if dry_run:
        log.info(f"[DRY RUN] Would process {total_count} leads through {len(steps)} steps")
        return {"total": total_count, **total_stats, "cost": 0.0}

    # Set up live dashboard
    progress = PipelineProgress(
        total_leads=total_count,
        total_batches=math.ceil(total_count / batch_size),
    )

    with LiveDashboard(progress) as dashboard:
        # Process in batches
        while True:
            leads = db.get_leads_by_status(campaign_id, fetch_statuses, limit=batch_size, offset=0)
            if not leads:
                break

            total_stats["batches"] += 1
            progress.batch_num = total_stats["batches"]

            batch_stats = await process_batch(
                leads, steps, campaign_config, cost_tracker, concurrency,
                dry_run=False, progress=progress, dashboard=dashboard,
            )

            total_stats["processed"] += batch_stats["processed"]
            total_stats["qualified"] += batch_stats["qualified"]
            total_stats["disqualified"] += batch_stats["disqualified"]
            total_stats["errors"] += batch_stats["errors"]

            # Sync progress object
            progress.processed = total_stats["processed"]
            progress.qualified = total_stats["qualified"]
            progress.disqualified = total_stats["disqualified"]
            progress.errors = total_stats["errors"]
            progress.total_cost = cost_tracker.total_cost
            dashboard.update()

            if batch_stats["processed"] == 0:
                break

    # Update pipeline run
    db.update_pipeline_run(run["id"], {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "processed_leads": total_stats["processed"],
        "qualified_leads": total_stats["qualified"],
        "disqualified_leads": total_stats["disqualified"],
        "error_leads": total_stats["errors"],
        "total_cost": cost_tracker.total_cost,
    })

    # Print final cost summary
    cost_tracker.print_summary()

    total_stats["cost"] = cost_tracker.total_cost
    total_stats["total"] = total_count

    log.info(
        f"Pipeline complete: {total_stats['processed']}/{total_count} leads, "
        f"${cost_tracker.total_cost:.4f} total cost"
    )

    return total_stats
