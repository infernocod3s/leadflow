"""Abstract base class for enrichment steps + batch log buffer."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from growthpal.config import CampaignConfig
from growthpal.db import queries as db
from growthpal.utils.cost_tracker import CostTracker
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


class EnrichmentLogBuffer:
    """Accumulates enrichment log entries and flushes in batch.

    Usage:
        buf = EnrichmentLogBuffer(flush_size=200)
        buf.add({...})
        buf.add({...})
        # Auto-flushes at 200 entries, or call buf.flush() at end
    """

    def __init__(self, flush_size: int = 200):
        self._buffer: list[dict] = []
        self._flush_size = flush_size
        self._total_flushed = 0

    def add(self, entry: dict) -> None:
        """Add a log entry. Auto-flushes when buffer is full."""
        self._buffer.append(entry)
        if len(self._buffer) >= self._flush_size:
            self.flush()

    def flush(self) -> int:
        """Flush all buffered entries to DB. Returns count inserted."""
        if not self._buffer:
            return 0
        count = db.batch_log_enrichments(self._buffer)
        self._total_flushed += count
        self._buffer.clear()
        return count

    @property
    def total_flushed(self) -> int:
        return self._total_flushed

    @property
    def pending(self) -> int:
        return len(self._buffer)


class EnrichmentStep(ABC):
    """Base class for all enrichment steps.

    Subclasses must implement:
        - name: step identifier
        - process(lead, campaign_config) -> dict of fields to update
    """

    name: str = ""
    is_gate: bool = False  # If True, can disqualify leads

    @abstractmethod
    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        """Process a single lead and return fields to update.

        Returns:
            Dict of lead fields to update. For gate steps, must include
            a boolean field indicating qualification.
        """
        ...

    async def run(
        self,
        lead: dict,
        campaign_config: CampaignConfig,
        cost_tracker: CostTracker | None = None,
    ) -> dict[str, Any]:
        """Execute the step with logging and error handling."""
        start = time.monotonic()
        try:
            result = await self.process(lead, campaign_config)
            duration_ms = int((time.monotonic() - start) * 1000)

            # Log enrichment to DB
            research_layer = result.pop("_research_layer", None)
            db.log_enrichment(
                lead_id=lead["id"],
                campaign_id=lead["campaign_id"],
                step_name=self.name,
                model=result.pop("_model", None),
                input_tokens=result.pop("_input_tokens", 0),
                output_tokens=result.pop("_output_tokens", 0),
                cost=result.pop("_cost", 0.0),
                duration_ms=duration_ms,
                success=True,
                research_layer=research_layer,
            )

            # Track cost if tracker provided
            if cost_tracker and "_model" not in result:
                pass  # cost already popped and logged

            return result

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error(f"[{self.name}] Error processing lead {lead.get('id', '?')}: {e}")
            db.log_enrichment(
                lead_id=lead["id"],
                campaign_id=lead["campaign_id"],
                step_name=self.name,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e),
            )
            raise
