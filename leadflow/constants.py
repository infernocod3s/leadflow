"""Constants used across LeadFlow."""

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


# Default costs per 1M tokens (input/output)
MODEL_COSTS = {
    Model.GPT4O: {"input": 2.50, "output": 10.00},
    Model.GPT4O_MINI: {"input": 0.15, "output": 0.60},
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
