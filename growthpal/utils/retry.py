"""Async retry with exponential backoff."""

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from growthpal.constants import MAX_RETRIES, RETRY_BASE_DELAY
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


def async_retry(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator for async functions with exponential backoff retry."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        log.error(f"[retry] {func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise
                    delay = base_delay * (2**attempt)
                    log.warning(f"[retry] {func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
