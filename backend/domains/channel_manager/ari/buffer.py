"""
ARI Event Buffer with debounce.

In-memory buffer that collects ARI events and flushes them
after a debounce window per event type. Each flush triggers coalescing.
"""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Callable, Coroutine

from .events import ARIChangeEvent
from .models import DEBOUNCE_WINDOWS

logger = logging.getLogger(__name__)


def _coalescing_key(event: ARIChangeEvent) -> str:
    """Build the coalescing key for grouping events."""
    return (
        f"{event.tenant_id}|{event.property_id}|"
        f"{event.room_type_code}|{event.rate_plan_code or ''}|"
        f"{event.date_from}:{event.date_to}|{event.event_type}"
    )


class ARIEventBuffer:
    """
    In-memory event buffer with per-type debounce windows.

    Events accumulate in buckets keyed by coalescing_key.
    After the debounce window elapses with no new events for that key,
    the bucket is flushed to the on_flush callback.
    """

    def __init__(self, on_flush: Callable[[str, list[ARIChangeEvent]], Coroutine]):
        self._buckets: dict[str, list[ARIChangeEvent]] = defaultdict(list)
        self._timers: dict[str, float] = {}
        self._on_flush = on_flush
        self._lock = asyncio.Lock()
        self._running = False
        self._flush_task: asyncio.Task | None = None

    async def start(self):
        """Start the background flush checker."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("ARI event buffer started")

    async def stop(self):
        """Stop the background flush checker."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Flush remaining
        await self._flush_all()
        logger.info("ARI event buffer stopped")

    async def push(self, event: ARIChangeEvent) -> str:
        """Push an event into the buffer. Returns the coalescing key."""
        key = _coalescing_key(event)
        async with self._lock:
            self._buckets[key].append(event)
            self._timers[key] = time.monotonic()
        logger.debug(f"ARI buffer: pushed event {event.id} → key={key}")
        return key

    async def _flush_loop(self):
        """Periodically check for expired debounce windows and flush."""
        while self._running:
            try:
                await asyncio.sleep(0.5)  # check every 500ms
                now = time.monotonic()
                keys_to_flush = []

                async with self._lock:
                    for key, last_time in list(self._timers.items()):
                        events = self._buckets.get(key, [])
                        if not events:
                            continue
                        event_type = events[0].event_type
                        window = DEBOUNCE_WINDOWS.get(event_type, 3)
                        if now - last_time >= window:
                            keys_to_flush.append(key)

                for key in keys_to_flush:
                    await self._flush_key(key)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ARI buffer flush loop error: {e}")

    async def _flush_key(self, key: str):
        """Flush a single coalescing key bucket."""
        async with self._lock:
            events = self._buckets.pop(key, [])
            self._timers.pop(key, None)

        if events:
            try:
                await self._on_flush(key, events)
                logger.info(f"ARI buffer: flushed key={key}, {len(events)} events")
            except Exception as e:
                logger.error(f"ARI buffer flush error for key={key}: {e}")

    async def _flush_all(self):
        """Flush all remaining buckets."""
        async with self._lock:
            keys = list(self._buckets.keys())
        for key in keys:
            await self._flush_key(key)

    def get_buffer_stats(self) -> dict:
        """Return current buffer state for monitoring."""
        return {
            "active_keys": len(self._buckets),
            "total_buffered_events": sum(len(v) for v in self._buckets.values()),
            "running": self._running,
        }
