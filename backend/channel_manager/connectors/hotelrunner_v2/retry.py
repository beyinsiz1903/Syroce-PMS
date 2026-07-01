"""
HotelRunner v2 — Retry Policy (Exponential Backoff + Dead Letter Queue)
========================================================================

max_retries: 5
backoff: exponential (1s, 2s, 4s, 8s, 16s) with jitter
retryable: only errors with retryable=True
dead letter: after max retries, event goes to DLQ collection
"""

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine

from .errors import HRv2Error, HRv2RateLimitError

logger = logging.getLogger("hrv2.retry")


class HRv2RetryPolicy:
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute(self, fn: Callable[[], Coroutine], *, context: str = "") -> Any:
        """Execute fn with retry. Raises on final failure."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await fn()
            except HRv2RateLimitError as e:
                last_error = e
                wait = min(e.retry_after, self.max_delay)
                logger.warning("[HRv2 retry] rate-limited, waiting %ds (attempt %d/%d) %s", wait, attempt + 1, self.max_retries, context)
                await asyncio.sleep(wait)
            except HRv2Error as e:
                last_error = e
                if not e.retryable or attempt >= self.max_retries:
                    raise
                delay = min(self.base_delay * (2**attempt) + random.uniform(0, 1), self.max_delay)
                logger.warning("[HRv2 retry] %s, retrying in %.1fs (attempt %d/%d) %s", e.category, delay, attempt + 1, self.max_retries, context)
                await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]


async def send_to_dlq(
    tenant_id: str,
    operation: str,
    payload: dict[str, Any],
    error: str,
    retry_count: int,
    correlation_id: str = "",
) -> str:
    """Persist failed operation to dead letter queue for manual retry."""
    import uuid

    from core.database import db

    dlq_id = str(uuid.uuid4())
    doc = {
        "id": dlq_id,
        "tenant_id": tenant_id,
        "provider": "hotelrunner",
        "operation": operation,
        "payload": payload,
        "error": error,
        "retry_count": retry_count,
        "correlation_id": correlation_id,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db["connector_dlq"].insert_one(doc)
    logger.error("[HRv2 DLQ] %s → %s (retries=%d, corr=%s)", operation, dlq_id, retry_count, correlation_id)
    return dlq_id
