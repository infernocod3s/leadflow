"""Gemini API client via REST (httpx). Supports Flash Lite for cheap classification/extraction."""

from __future__ import annotations

import json
from typing import Any

import httpx

from growthpal.config import get_config
from growthpal.constants import GEMINI_RPM, MODEL_COSTS, Model
from growthpal.utils.logger import get_logger
from growthpal.utils.rate_limiter import RateLimiter
from growthpal.utils.retry import async_retry

log = get_logger(__name__)

_http_client: httpx.AsyncClient | None = None
_rate_limiters: dict[str, RateLimiter] = {}

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _get_rate_limiter(model: str) -> RateLimiter:
    if model not in _rate_limiters:
        rpm = GEMINI_RPM.get(model, 2000)
        _rate_limiters[model] = RateLimiter(rate=rpm / 60, max_tokens=rpm // 6)
    return _rate_limiters[model]


def _convert_messages(messages: list[dict[str, str]]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-style messages to Gemini format.

    Returns (system_instruction, contents).
    """
    system_text = None
    contents = []

    for msg in messages:
        role = msg["role"]
        text = msg["content"]

        if role == "system":
            system_text = text
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})

    return system_text, contents


@async_retry(max_retries=3, exceptions=(httpx.HTTPError, httpx.TimeoutException, KeyError))
async def gemini_chat_completion(
    messages: list[dict[str, str]],
    model: str = Model.GEMINI_FLASH_LITE,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    json_mode: bool = False,
) -> dict[str, Any]:
    """Make a Gemini chat completion request.

    Returns dict with: content, input_tokens, output_tokens, model, cost
    """
    cfg = get_config()
    if not cfg.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    limiter = _get_rate_limiter(model)
    await limiter.acquire()

    system_text, contents = _convert_messages(messages)

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}

    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    client = _get_http_client()
    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={cfg.gemini_api_key}"

    response = await client.post(url, json=body)
    response.raise_for_status()
    data = response.json()

    # Extract response text
    candidate = data["candidates"][0]
    content = candidate["content"]["parts"][0]["text"]

    # Extract token usage
    usage = data.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)

    costs = MODEL_COSTS.get(model, MODEL_COSTS[Model.GEMINI_FLASH_LITE])
    cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "cost": cost,
    }


async def gemini_chat_json(
    messages: list[dict[str, str]],
    model: str = Model.GEMINI_FLASH_LITE,
    temperature: float = 0.1,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    """Gemini completion that returns parsed JSON.

    Returns dict with: data, input_tokens, output_tokens, model, cost
    """
    result = await gemini_chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )

    try:
        parsed = json.loads(result["content"])
    except json.JSONDecodeError:
        log.warning("Gemini: failed to parse JSON response, returning raw")
        parsed = {"raw": result["content"]}

    return {
        "data": parsed,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "cost": result["cost"],
    }
