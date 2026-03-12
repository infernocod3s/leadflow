"""Async batch processor — two-phase: batch company research then concurrent remaining steps.

Phase 1: Batch company research (domain-deduplicated via batch_cascade)
Phase 2: Run remaining steps with high concurrency
Phase 3: Flush accumulated DB writes at end
"""

from __future__ import annotations

import asyncio
from typing import Any

from growthpal.config import CampaignConfig
from growthpal.constants import PipelineStatus
from growthpal.db import queries as db
from growthpal.enrichments.base import EnrichmentLogBuffer, EnrichmentStep
from growthpal.utils.cost_tracker import CostTracker
from growthpal.utils.logger import get_logger
from growthpal.utils.progress import LiveDashboard, PipelineProgress

log = get_logger(__name__)


async def process_lead_through_steps(
    lead: dict,
    steps: list[EnrichmentStep],
    campaign_config: CampaignConfig,
    cost_tracker: CostTracker,
    dry_run: bool = False,
    progress: PipelineProgress | None = None,
    dashboard: LiveDashboard | None = None,
    log_buffer: EnrichmentLogBuffer | None = None,
) -> dict[str, Any]:
    """Process a single lead through all steps sequentially.

    If log_buffer is provided, enrichment logs are deferred to the buffer
    instead of being written individually to the DB.
    """
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

            result = await step.run(lead, campaign_config, cost_tracker)
            accumulated_updates.update(result)

            # Merge result into lead dict for subsequent steps
            lead.update(result)

            # Update dashboard with step completion
            if progress:
                cost = result.get("_cost", 0.0)
                progress.record_step(step.name, cost)
                progress.step_active[step.name] = max(0, progress.step_active.get(step.name, 1) - 1)

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
                    return accumulated_updates

        except Exception as e:
            log.error(f"[{step.name}] Lead {lead_id} error: {e}")
            if progress:
                progress.step_active[step.name] = max(0, progress.step_active.get(step.name, 1) - 1)
            accumulated_updates["pipeline_status"] = PipelineStatus.ERROR.value
            accumulated_updates["error_message"] = str(e)
            return accumulated_updates

    # All steps completed
    if not dry_run:
        final_status = PipelineStatus.EMAIL_GENERATED if "email_body" in accumulated_updates else PipelineStatus.ENRICHED
        accumulated_updates["pipeline_status"] = final_status.value

    return accumulated_updates


def _check_gate(step_name: str, result: dict) -> bool:
    """Check if a gate step passed or failed."""
    if step_name == "icp_qualification":
        return bool(result.get("icp_qualified"))
    if step_name == "job_title_icp":
        return bool(result.get("title_relevant"))
    if step_name == "email_verification":
        return bool(result.get("_email_verified", True))
    for key, value in result.items():
        if key.startswith("_custom_gate_"):
            return bool(value)
    return True


async def process_batch(
    leads: list[dict],
    steps: list[EnrichmentStep],
    campaign_config: CampaignConfig,
    cost_tracker: CostTracker,
    concurrency: int = 500,
    dry_run: bool = False,
    progress: PipelineProgress | None = None,
    dashboard: LiveDashboard | None = None,
) -> dict[str, int]:
    """Process a batch of leads — two-phase for maximum throughput.

    Phase 1: Batch company research (domain-deduplicated)
    Phase 2: Remaining steps with concurrency semaphore
    Phase 3: Flush all DB writes
    """
    stats = {"processed": 0, "qualified": 0, "disqualified": 0, "errors": 0}
    log_buffer = EnrichmentLogBuffer(flush_size=200)

    # Split steps into batch-capable (company_research) and remaining
    batch_steps = [s for s in steps if getattr(s, "supports_batch", False)]
    remaining_steps = [s for s in steps if not getattr(s, "supports_batch", False)]

    # ── Phase 1: Batch company research ────────────────────────────────
    lead_results: dict[str, dict] = {}  # lead_id -> batch step results

    for step in batch_steps:
        if dry_run:
            log.info(f"[dry-run] Would batch-run {step.name} on {len(leads)} leads")
            continue

        try:
            import time
            start = time.monotonic()
            batch_result = await step.process_batch(leads, campaign_config)
            duration_ms = int((time.monotonic() - start) * 1000)

            for lead in leads:
                lead_id = lead["id"]
                result = batch_result.get(lead_id, {})
                lead_results[lead_id] = result
                # Merge into lead for subsequent steps
                lead.update(result)

                # Buffer the enrichment log
                log_buffer.add({
                    "lead_id": lead_id,
                    "campaign_id": lead["campaign_id"],
                    "step_name": step.name,
                    "model": result.pop("_model", None),
                    "input_tokens": result.pop("_input_tokens", 0),
                    "output_tokens": result.pop("_output_tokens", 0),
                    "cost": result.pop("_cost", 0.0),
                    "duration_ms": duration_ms // max(len(leads), 1),
                    "success": True,
                    "research_layer": result.pop("_research_layer", None),
                })

            log.info(f"[batch] {step.name}: {len(batch_result)} leads in {duration_ms}ms")

        except Exception as e:
            log.error(f"[batch] {step.name} batch failed: {e}")
            # Fall back to individual processing for this step
            remaining_steps = [step] + remaining_steps

    # ── Phase 2: Remaining steps with concurrency ──────────────────────
    if remaining_steps and not dry_run:
        semaphore = asyncio.Semaphore(concurrency)
        pending_updates: list[tuple[str, dict]] = []

        async def process_remaining(lead: dict) -> None:
            async with semaphore:
                try:
                    result = await process_lead_through_steps(
                        lead, remaining_steps, campaign_config, cost_tracker,
                        dry_run, progress, dashboard, log_buffer,
                    )

                    # Merge any batch step results
                    lead_id = lead["id"]
                    if lead_id in lead_results:
                        combined = {**lead_results[lead_id], **result}
                    else:
                        combined = result

                    status = combined.get("pipeline_status", "")
                    if status == PipelineStatus.DISQUALIFIED.value:
                        stats["disqualified"] += 1
                    elif status in (PipelineStatus.ENRICHED.value, PipelineStatus.EMAIL_GENERATED.value):
                        stats["qualified"] += 1
                    elif status == PipelineStatus.ERROR.value:
                        stats["errors"] += 1
                        db.update_lead_status(lead_id, PipelineStatus.ERROR,
                                              error_message=combined.get("error_message", ""))
                        return

                    stats["processed"] += 1
                    # Accumulate DB write
                    pending_updates.append((lead_id, combined))

                except Exception as e:
                    stats["errors"] += 1
                    log.error(f"Unexpected error processing lead {lead.get('id')}: {e}")

        tasks = [asyncio.create_task(process_remaining(lead)) for lead in leads]
        await asyncio.gather(*tasks)

        # ── Phase 3: Flush all DB writes ───────────────────────────────
        if pending_updates:
            db.batch_update_leads(pending_updates)

    elif not remaining_steps and not dry_run:
        # Only batch steps — still need to write results
        pending_updates = []
        for lead in leads:
            lead_id = lead["id"]
            result = lead_results.get(lead_id, {})
            final_status = PipelineStatus.EMAIL_GENERATED if "email_body" in result else PipelineStatus.ENRICHED
            result["pipeline_status"] = final_status.value
            pending_updates.append((lead_id, result))
            stats["processed"] += 1
            stats["qualified"] += 1

        if pending_updates:
            db.batch_update_leads(pending_updates)

    # Flush remaining logs
    log_buffer.flush()

    log.info(
        f"[batch] Done: {stats['processed']} processed, "
        f"{stats['qualified']} qualified, {stats['errors']} errors, "
        f"{log_buffer.total_flushed} log entries flushed"
    )
    return stats
