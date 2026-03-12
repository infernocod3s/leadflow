"""FastAPI health and monitoring endpoints for the worker."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from worker.config import BATCH_SIZE, CONCURRENCY, WORKER_ID
from worker.db import get_active_campaigns, get_worker_stats
from worker.stats import stats

app = FastAPI(title="LeadFlow Worker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "leadflow-worker",
        "worker_id": WORKER_ID,
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "worker_id": WORKER_ID,
        "uptime_seconds": round(stats.uptime_seconds, 1),
    }


@app.get("/stats")
def worker_stats():
    """Current worker instance stats."""
    return {
        "worker_id": WORKER_ID,
        "config": {
            "batch_size": BATCH_SIZE,
            "concurrency": CONCURRENCY,
        },
        **stats.to_dict(),
    }


@app.get("/queue")
def queue_stats():
    """Global queue stats across all campaigns."""
    return get_worker_stats()


@app.get("/campaigns")
def active_campaigns():
    """Campaigns with pending leads."""
    campaigns = get_active_campaigns()
    return {
        "count": len(campaigns),
        "campaigns": [
            {
                "id": str(c["id"]),
                "slug": c["slug"],
                "pending_count": c["pending_count"],
            }
            for c in campaigns
        ],
    }
