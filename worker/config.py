"""Worker configuration — loaded from environment variables."""

from __future__ import annotations

import os
import uuid


WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2000"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "500"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "2"))  # seconds
PREFETCH_SIZE = int(os.getenv("PREFETCH_SIZE", "2000"))
STALE_CLAIM_TIMEOUT = int(os.getenv("STALE_CLAIM_TIMEOUT", "30"))  # minutes
API_PORT = int(os.getenv("PORT", "8000"))  # Railway sets PORT
CAMPAIGN_SLUGS = os.getenv("CAMPAIGN_SLUGS", "")  # comma-separated, empty = all

# Multi-model AI keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
