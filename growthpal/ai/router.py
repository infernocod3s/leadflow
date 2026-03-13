"""Multi-model AI router — dispatches to the correct provider based on model."""

from __future__ import annotations

from typing import Any

from growthpal.constants import MODEL_PROVIDER, Model
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


def _get_provider(model: str) -> str:
    """Get the provider for a model, defaulting to openai."""
    return MODEL_PROVIDER.get(model, "openai")


async def chat_completion(
    messages: list[dict[str, str]],
    model: str = Model.GPT4O_MINI,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    response_format: dict | None = None,
) -> dict[str, Any]:
    """Route chat completion to the correct provider.

    Returns dict with: content, input_tokens, output_tokens, model, cost
    """
    provider = _get_provider(model)

    if provider == "gemini":
        from growthpal.ai.gemini_client import gemini_chat_completion

        return await gemini_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=bool(response_format),
        )
    elif provider == "deepseek":
        from growthpal.ai.deepseek_client import deepseek_chat_completion

        return await deepseek_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
    else:
        from growthpal.ai.openai_client import chat_completion as openai_chat_completion

        return await openai_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )


async def chat_json(
    messages: list[dict[str, str]],
    model: str = Model.GPT4O_MINI,
    temperature: float = 0.1,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    """Route JSON chat completion to the correct provider.

    Returns dict with: data, input_tokens, output_tokens, model, cost
    """
    provider = _get_provider(model)

    if provider == "gemini":
        from growthpal.ai.gemini_client import gemini_chat_json

        return await gemini_chat_json(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "deepseek":
        from growthpal.ai.deepseek_client import deepseek_chat_json

        return await deepseek_chat_json(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        from growthpal.ai.openai_client import chat_json as openai_chat_json

        return await openai_chat_json(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
