import asyncio
from typing import Callable, TypeVar

import httpx
from fastapi import HTTPException

from config import MAX_RETRIES, logger

T = TypeVar("T")


async def retry_async(coro_fn: Callable[..., T], max_retries: int = MAX_RETRIES) -> T:
    """Execute async call with exponential backoff retries."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except HTTPException:
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
            if attempt < max_retries:
                delay = 2**attempt
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
                await asyncio.sleep(delay)
    raise last_err
