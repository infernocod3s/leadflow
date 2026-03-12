"""Worker entry point — starts the processing loop and API server."""

from __future__ import annotations

import asyncio
import logging
import threading

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from worker.api import app
from worker.config import API_PORT, DATABASE_URL, WORKER_ID
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


def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL is required. Set it in .env or environment variables.")
        log.error("Format: postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres")
        raise SystemExit(1)

    log.info(f"LeadFlow Worker {WORKER_ID} starting")
    log.info(f"API server on port {API_PORT}")

    # Start API in background thread
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()

    # Run worker loop
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
