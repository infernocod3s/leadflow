"""Worker entry point — starts the processing loop and API server."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from worker.api import app
from worker.config import API_PORT, SUPABASE_KEY, SUPABASE_URL, WORKER_ID
from worker.processor import worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("worker")


def start_api_server():
    """Run the FastAPI server in a separate thread."""
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="warning")


async def _run_worker():
    """Run worker loop with graceful shutdown cleanup."""
    try:
        await worker_loop()
    finally:
        log.info("Shutting down — closing shared HTTP client...")
        from growthpal.http import close_http_client
        await close_http_client()
        log.info("Shutdown complete.")


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL and SUPABASE_KEY are required.")
        raise SystemExit(1)

    log.info(f"GrowthPal Worker {WORKER_ID} starting")
    log.info(f"API server on port {API_PORT}")

    # Start API in background thread
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()

    # Run worker loop with graceful shutdown
    asyncio.run(_run_worker())


if __name__ == "__main__":
    main()
