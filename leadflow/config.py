"""Configuration loader — .env + YAML campaign configs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    supabase_url: str = ""
    supabase_key: str = ""
    openai_api_key: str = ""
    smartlead_api_key: str = ""
    prospeo_api_key: str = ""
    trykitt_api_key: str = ""
    bettercontact_api_key: str = ""
    reoon_api_key: str = ""
    bounceban_api_key: str = ""
    log_level: str = "INFO"
    default_concurrency: int = 20

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_key=os.getenv("SUPABASE_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            smartlead_api_key=os.getenv("SMARTLEAD_API_KEY", ""),
            prospeo_api_key=os.getenv("PROSPEO_API_KEY", ""),
            trykitt_api_key=os.getenv("TRYKITT_API_KEY", ""),
            bettercontact_api_key=os.getenv("BETTERCONTACT_API_KEY", ""),
            reoon_api_key=os.getenv("REOON_API_KEY", ""),
            bounceban_api_key=os.getenv("BOUNCEBAN_API_KEY", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            default_concurrency=int(os.getenv("DEFAULT_CONCURRENCY", "20")),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.supabase_url:
            errors.append("SUPABASE_URL is required")
        if not self.supabase_key:
            errors.append("SUPABASE_KEY is required")
        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY is required")
        return errors


@dataclass
class CampaignConfig:
    """Per-campaign YAML configuration."""

    client_name: str = ""
    campaign_slug: str = ""
    icp_description: str = ""
    target_titles: list[str] = field(default_factory=list)
    target_industries: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    email_tone: str = "professional"
    email_cta: str = ""
    sender_name: str = ""
    sender_company: str = ""
    sender_value_prop: str = ""
    steps: list[str] = field(default_factory=lambda: ["all"])
    concurrency: int = 20
    smartlead_campaign_id: int | None = None
    use_deepline: bool = False
    deepline_before_step: str = "company_research"  # Insert deepline enrichment before this step
    custom_ai_steps: list[dict] = field(default_factory=list)
    custom_ai_after_step: str = "signal_detection"  # Insert custom steps after this step

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CampaignConfig":
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Singleton
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
