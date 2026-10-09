"""Idempotent marketplace renewal worker with retry/dunning state."""
from __future__ import annotations

import asyncio
import importlib
import logging
import os

logger = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = int(os.environ.get("MARKETPLACE_RENEWAL_INTERVAL_SECONDS", "3600"))
_started = False


async def _loop(interval_seconds: int) -> None:
    from core.database import _raw_db

    # Keep the lightweight worker boot dependency graph separate from optional
    # payment-provider dependencies; load the renewal service at execution time.
    process_due_renewals = importlib.import_module("core.marketplace_renewal_service").process_due_renewals
    await asyncio.sleep(30)
    while True:
        try:
            outcome = await process_due_renewals(_raw_db)
            if outcome["processed"]:
                logger.info("marketplace renewals processed=%s renewed=%s failed=%s", outcome["processed"], outcome["renewed"], outcome["failed"])
        except Exception as exc:
            logger.exception("marketplace renewal tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    global _started
    if _started:
        return True
    if DEFAULT_INTERVAL_SECONDS <= 0:
        return False
    asyncio.create_task(_loop(DEFAULT_INTERVAL_SECONDS), name="marketplace-renewal-worker")
    _started = True
    return True
