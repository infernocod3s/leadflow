"""In-memory worker stats for the health API."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class WorkerStats:
    started_at: float = field(default_factory=time.time)
    leads_processed: int = 0
    leads_qualified: int = 0
    leads_disqualified: int = 0
    leads_errored: int = 0
    batches_processed: int = 0
    total_cost: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    @property
    def leads_per_second(self) -> float:
        if self.uptime_seconds < 1:
            return 0.0
        return self.leads_processed / self.uptime_seconds

    def to_dict(self) -> dict:
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "leads_processed": self.leads_processed,
            "leads_qualified": self.leads_qualified,
            "leads_disqualified": self.leads_disqualified,
            "leads_errored": self.leads_errored,
            "batches_processed": self.batches_processed,
            "leads_per_second": round(self.leads_per_second, 2),
            "total_cost": round(self.total_cost, 4),
            "recent_errors": self.errors[-10:],  # Last 10 errors
        }


# Singleton
stats = WorkerStats()
