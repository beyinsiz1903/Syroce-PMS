"""Handle transient DNS resolver failures emitted by asyncio background futures.

Motor/PyMongo retries a temporary Atlas DNS failure on its next server-selection
attempt.  Python's event loop can nevertheless report the intermediate resolver
future as ``Future exception was never retrieved``.  That is operational noise
for an isolated retry, but an uninterrupted burst must remain an error.

Only the exact resolver condition (``EAI_AGAIN``) is intercepted here.  Every
other asyncio exception is delegated to the previous/default event-loop handler
unchanged, preserving normal Sentry reporting for application bugs.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from typing import Any

from core.transient_db_guard import TransientFailureTracker

_LOGGER = logging.getLogger("asyncio.transient_dns")
_UNRETRIEVED_FUTURE_MESSAGE = "future exception was never retrieved"


def is_transient_unretrieved_dns_failure(context: dict[str, Any]) -> bool:
    """Return whether an asyncio context is the retryable DNS condition only."""
    exc = context.get("exception")
    message = str(context.get("message") or "").lower()
    retry_errno = getattr(socket, "EAI_AGAIN", -3)
    return (
        isinstance(exc, socket.gaierror)
        and exc.errno == retry_errno
        and _UNRETRIEVED_FUTURE_MESSAGE in message
    )


class TransientAsyncioDnsGuard:
    """Demote one-off resolver hiccups while escalating a persistent outage."""

    def __init__(self, *, threshold: int = 5) -> None:
        self._failures = TransientFailureTracker("asyncio-dns", threshold=threshold)

    def install(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Install once for *loop*, preserving its prior exception handler."""
        running_loop = loop or asyncio.get_running_loop()
        if getattr(running_loop, "_syroce_transient_dns_guard", None):
            return

        previous: Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None] | None = (
            running_loop.get_exception_handler()
        )

        def handler(active_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            if is_transient_unretrieved_dns_failure(context):
                exc = context["exception"]
                self._failures.log_exception(
                    _LOGGER,
                    exc,
                    TransientFailureTracker.OUTER_LOOP_KEY,
                    context="unretrieved resolver future; driver will retry",
                )
                return
            if previous is not None:
                previous(active_loop, context)
            else:
                active_loop.default_exception_handler(context)

        running_loop.set_exception_handler(handler)
        setattr(running_loop, "_syroce_transient_dns_guard", self)
