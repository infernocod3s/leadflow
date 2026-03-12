"""Worker configuration — loaded from environment variables."""

from __future__ import annotations

import os
import uuid


WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "20"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds
STALE_CLAIM_TIMEOUT = int(os.getenv("STALE_CLAIM_TIMEOUT", "30"))  # minutes
API_PORT = int(os.getenv("PORT", "8000"))  # Railway sets PORT
CAMPAIGN_SLUGS = os.getenv("CAMPAIGN_SLUGS", "")  # comma-separated, empty = all
