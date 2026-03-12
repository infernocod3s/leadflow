"""Async batch processor — runs enrichment steps on leads with concurrency control."""

from __future__ import annotations

import asyncio
from typing import Any

from leadflow.config import CampaignConfig
from leadflow.constants import PipelineStatus
from leadflow.db import queries as db
from leadflow.enrichments.base import EnrichmentStep
from leadflow.utils.cost_tracker import CostTracker
from leadflow.utils.logger import get_logger
from leadflow.utils.progress import LiveDashboard, PipelineProgress

log = get_logger(__name__)


async def process_lead_through_steps(
    lead: dict,
    steps: list[EnrichmentStep],
    campaign_config: CampaignConfig,
    cost_tracker: CostTracker,
    dry_run: bool = False,
    progress: PipelineProgress | None = None,
    dashboard: LiveDashboard | None = None,
) -> dict[str, Any]:
    """Process a single lead through all steps sequentially."""
    lead_id = lead["id"]
    lead_email = lead.get("email") or lead.get("raw_email") or lead_id[:8]
    accumulated_updates: dict[str, Any] = {}

    for step in steps:
        if dry_run:
            log.info(f"[dry-run] Would run {step.name} on lead {lead_id}")
            continue

        try:
            # Update dashboard
            if progress:
                progress.current_step = step.name
                progress.current_lead_email = lead_email
                progress.step_active[step.name] = progress.step_active.get(step.name, 0) + 1
                if dashboard:
                    dashboard.update()

            # Update current step in DB
            db.update_lead(lead_id, {"current_step": step.name})

            result = await step.run(lead, campaign_config, cost_tracker)
            accumulated_updates.update(result)

            # Merge result into lead dict for subsequent steps
            lead.update(result)

            # Update dashboard with step completion
            if progress:
                cost = result.get("_cost", 0.0)
                progress.record_step(step.name, cost)
                progress.step_active[step.name] = max(0, progress.step_active.get(step.name, 1) - 1)

                # Track email finding results
                if step.name == "email_finding" and result.get("email"):
                    progress.emails_found += 1
                    provider = result.get("_email_provider", "unknown")
                    progress.record_provider(provider, True)
                elif step.name == "email_finding" and not result.get("email"):
                    progress.record_provider("all", False)

                if step.name == "email_verification" and result.get("_email_verified"):
                    progress.emails_verified += 1

                if dashboard:
                    dashboard.update()

            # Check gate steps
            if step.is_gate:
                qualified = _check_gate(step.name, result)
                if not qualified:
                    accumulated_updates["pipeline_status"] = PipelineStatus.DISQUALIFIED.value
                    db.update_lead(lead_id, accumulated_updates)
                    return accumulated_updates

        except Exception as e:
            log.error(f"[{step.name}] Lead {lead_id} error: {e}")
            if progress:
                progress.step_active[step.name] = max(0, progress.step_active.get(step.name, 1) - 1)
            db.update_lead_status(lead_id, PipelineStatus.ERROR, error_message=str(e))
            return accumulated_updates

    # All steps completed
    if not dry_run:
        final_status = PipelineStatus.EMAIL_GENERATED if "email_body" in accumulated_updates else PipelineStatus.ENRICHED
        accumulated_updates["pipeline_status"] = final_status.value
        db.update_lead(lead_id, accumulated_updates)

    return accumulated_updates


def _check_gate(step_name: str, result: dict) -> bool:
    """Check if a gate step passed or failed."""
    if step_name == "icp_qualification":
        return bool(result.get("icp_qualified"))
    if step_name == "job_title_icp":
        return bool(result.get("title_relevant"))
    if step_name == "email_verification":
        return bool(result.get("_email_verified", True))
    # Custom AI gate steps
    for key, value in result.items():
        if key.startswith("_custom_gate_"):
            return bool(value)
    return True


async def process_batch(
    leads: list[dict],
    steps: list[EnrichmentStep],
    campaign_config: CampaignConfig,
    cost_tracker: CostTracker,
    concurrency: int = 20,
    dry_run: bool = False,
    progress: PipelineProgress | None = None,
    dashboard: LiveDashboard | None = None,
) -> dict[str, int]:
    """Process a batch of leads with concurrency control."""
    semaphore = asyncio.Semaphore(concurrency)
    stats = {"processed": 0, "qualified": 0, "disqualified": 0, "errors": 0}

    async def process_one(lead: dict) -> None:
        async with semaphore:
            try:
                if not dry_run:
                    db.update_lead_status(lead["id"], PipelineStatus.IN_PROGRESS)

                result = await process_lead_through_steps(
                    lead, steps, campaign_config, cost_tracker, dry_run,
                    progress, dashboard,
                )

                stats["processed"] += 1
                status = result.get("pipeline_status", "")
                if status == PipelineStatus.DISQUALIFIED.value:
                    stats["disqualified"] += 1
                elif status in (PipelineStatus.ENRICHED.value, PipelineStatus.EMAIL_GENERATED.value):
                    stats["qualified"] += 1

                # Update progress
                if progress:
                    progress.processed = (progress.processed or 0) - stats["processed"] + stats["processed"]

            except Exception as e:
                stats["errors"] += 1
                log.error(f"Unexpected error processing lead {lead.get('id')}: {e}")

    tasks = [asyncio.create_task(process_one(lead)) for lead in leads]
    await asyncio.gather(*tasks)

    return stats
