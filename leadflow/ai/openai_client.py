"""OpenAI API wrapper with retry, rate limiting, and cost tracking."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from leadflow.config import get_config
from leadflow.constants import OPENAI_RPM, Model
from leadflow.utils.logger import get_logger
from leadflow.utils.rate_limiter import RateLimiter
from leadflow.utils.retry import async_retry

log = get_logger(__name__)

_client: AsyncOpenAI | None = None
_rate_limiters: dict[str, RateLimiter] = {}


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        cfg = get_config()
        _client = AsyncOpenAI(api_key=cfg.openai_api_key)
    return _client


def _get_rate_limiter(model: str) -> RateLimiter:
    if model not in _rate_limiters:
        rpm = OPENAI_RPM.get(model, 500)
        _rate_limiters[model] = RateLimiter(rate=rpm / 60, max_tokens=rpm // 6)
    return _rate_limiters[model]


@async_retry(max_retries=3, exceptions=(Exception,))
async def chat_completion(
    messages: list[dict[str, str]],
    model: str = Model.GPT4O,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    response_format: dict | None = None,
) -> dict[str, Any]:
    """Make a chat completion request with rate limiting and retry.

    Returns:
        Dict with keys: content, input_tokens, output_tokens, model, cost
    """
    client = get_openai_client()
    limiter = _get_rate_limiter(model)

    await limiter.acquire()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = await client.chat.completions.create(**kwargs)

    choice = response.choices[0]
    usage = response.usage

    from leadflow.constants import MODEL_COSTS

    costs = MODEL_COSTS.get(model, MODEL_COSTS[Model.GPT4O])
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    return {
        "content": choice.message.content or "",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "cost": cost,
    }


async def chat_json(
    messages: list[dict[str, str]],
    model: str = Model.GPT4O,
    temperature: float = 0.1,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    """Chat completion that returns parsed JSON.

    Returns:
        Dict with keys: data (parsed JSON), input_tokens, output_tokens, model, cost
    """
    result = await chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(result["content"])
    except json.JSONDecodeError:
        log.warning(f"Failed to parse JSON response, returning raw content")
        data = {"raw": result["content"]}

    return {
        "data": data,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "cost": result["cost"],
    }
