"""Supabase client singleton."""

from __future__ import annotations

from supabase import Client, create_client

from leadflow.config import get_config

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        cfg = get_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_key)
    return _client
