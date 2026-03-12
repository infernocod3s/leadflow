"""DeepSeek API client via OpenAI SDK (compatible API)."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from growthpal.config import get_config
from growthpal.constants import DEEPSEEK_RPM, MODEL_COSTS, Model
from growthpal.utils.logger import get_logger
from growthpal.utils.rate_limiter import RateLimiter
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_client: AsyncOpenAI | None = None
_rate_limiters: dict[str, RateLimiter] = {}


def _get_deepseek_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        cfg = get_config()
        if not cfg.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY not configured")
        _client = AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
    return _client


def _get_rate_limiter(model: str) -> RateLimiter:
    if model not in _rate_limiters:
        rpm = DEEPSEEK_RPM.get(model, 500)
        _rate_limiters[model] = RateLimiter(rate=rpm / 60, max_tokens=rpm // 6)
    return _rate_limiters[model]


@async_retry(max_retries=3, exceptions=(Exception,))
async def deepseek_chat_completion(
    messages: list[dict[str, str]],
    model: str = Model.DEEPSEEK_V3,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    response_format: dict | None = None,
) -> dict[str, Any]:
    """Make a DeepSeek chat completion (OpenAI-compatible).

    Returns dict with: content, input_tokens, output_tokens, model, cost
    """
    client = _get_deepseek_client()
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

    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    costs = MODEL_COSTS.get(model, MODEL_COSTS[Model.DEEPSEEK_V3])
    cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    return {
        "content": choice.message.content or "",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "cost": cost,
    }


async def deepseek_chat_json(
    messages: list[dict[str, str]],
    model: str = Model.DEEPSEEK_V3,
    temperature: float = 0.1,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    """DeepSeek completion that returns parsed JSON.

    Returns dict with: data, input_tokens, output_tokens, model, cost
    """
    result = await deepseek_chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(result["content"])
    except json.JSONDecodeError:
        log.warning("DeepSeek: failed to parse JSON response, returning raw")
        data = {"raw": result["content"]}

    return {
        "data": data,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "cost": result["cost"],
    }
