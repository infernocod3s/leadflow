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
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    serper_api_key: str = ""
    tavily_api_key: str = ""
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
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            serper_api_key=os.getenv("SERPER_API_KEY", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
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
        # At least one AI provider required
        if not any([self.openai_api_key, self.gemini_api_key, self.deepseek_api_key]):
            errors.append("At least one AI API key required (OPENAI, GEMINI, or DEEPSEEK)")
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
    deepline_before_step: str = "company_research"
    custom_ai_steps: list[dict] = field(default_factory=list)
    custom_ai_after_step: str = "signal_detection"

    # Strategy-based routing (signal → angle, fallback → random/optimized)
    strategy_routing: dict = field(default_factory=dict)

    # Multi-model configuration
    research_model: str = "gpt-4o-mini"
    email_generation_model: str = "gpt-4o-mini"
    classification_model: str = "gpt-4o-mini"

    # Search provider: "serper" or "tavily"
    search_provider: str = "serper"

    # Research cascade settings
    min_data_quality_score: float = 0.6
    research_layers_enabled: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    cache_ttl_hours: int = 168  # 7 days
    signals_cache_ttl_hours: int = 72  # 3 days

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CampaignConfig":
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignConfig":
        """Create from a dictionary (e.g. campaigns.config JSONB)."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Singleton
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
