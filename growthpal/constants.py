"""Constants used across GrowthPal."""

from enum import Enum


class PipelineStatus(str, Enum):
    IMPORTED = "imported"
    IN_PROGRESS = "in_progress"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    EMAIL_GENERATED = "email_generated"
    PUSHED = "pushed"
    ERROR = "error"


class Model(str, Enum):
    GPT4O = "gpt-4o"
    GPT4O_MINI = "gpt-4o-mini"
    GEMINI_FLASH_LITE = "gemini-2.0-flash-lite"
    DEEPSEEK_V3 = "deepseek-chat"


# Default costs per 1M tokens (input/output)
MODEL_COSTS = {
    Model.GPT4O: {"input": 2.50, "output": 10.00},
    Model.GPT4O_MINI: {"input": 0.15, "output": 0.60},
    Model.GEMINI_FLASH_LITE: {"input": 0.075, "output": 0.30},
    Model.DEEPSEEK_V3: {"input": 0.28, "output": 0.42},
}

# Maps model enum to provider name for routing
MODEL_PROVIDER = {
    Model.GPT4O: "openai",
    Model.GPT4O_MINI: "openai",
    Model.GEMINI_FLASH_LITE: "gemini",
    Model.DEEPSEEK_V3: "deepseek",
}

DEFAULT_CONCURRENCY = 20
DEFAULT_BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# Rate limits (requests per minute)
OPENAI_RPM = {
    Model.GPT4O: 500,
    Model.GPT4O_MINI: 2000,
}

GEMINI_RPM = {
    Model.GEMINI_FLASH_LITE: 4000,
}

DEEPSEEK_RPM = {
    Model.DEEPSEEK_V3: 1000,
}
