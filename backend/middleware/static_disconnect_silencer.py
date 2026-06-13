"""StaticDisconnectSilencerMiddleware — swallow benign client-disconnect noise.

Why:
  uvicorn raises ``RuntimeError("Response content shorter than Content-Length")``
  when a client disconnects mid-download of a static asset: StaticFiles stamped
  ``Content-Length`` from the file size, then the socket closed before all bytes
  were flushed. Mobile browsers cancel
  asset requests aggressively (prefetch / fast navigation), so this is benign
  client backpressure — there is nothing to send to a client that has already
  left.

  The SAME root cause also surfaces as an ``OSError`` when the socket write
  itself fails after the peer has gone — typically ``Errno 32`` (EPIPE / broken
  pipe), ``Errno 104`` (ECONNRESET) or, behind the deploy reverse-proxy, ``Errno
  5`` (EIO / Input/output error) when the upstream connection was closed
  mid-flush. That ``OSError`` is the same benign disconnect, just a different
  exception class, so it is swallowed under the identical static-path scope.

  The exception otherwise propagates all the way to uvicorn's ``run_asgi``,
  which logs ``ERROR: Exception in ASGI application``. That single disconnect
  produces TWO Sentry events:
    1. the Sentry ASGI/Starlette integration capture (HAS request context — the
       ``before_send`` static-disconnect filter drops it), and
    2. the uvicorn ``uvicorn.error`` log captured by the LoggingIntegration —
       emitted AFTER the request scope is torn down, so ``event["request"]`` is
       absent, the path is empty, and the path-anchored ``before_send`` filter
       cannot confirm it is static → it slips through to Sentry as noise.

  Filtering after the fact (``before_send``) therefore only catches half of it
  and still leaves the workflow-console ERROR spam. This middleware fixes it at
  the SOURCE: it catches the benign RuntimeError as it unwinds and suppresses it
  for static GET/HEAD requests, so uvicorn never logs it and neither Sentry
  capture fires. The ``before_send`` filter in ``infra/cloud_observability`` is
  kept as a defense-in-depth backstop.

Safety:
  Only two disconnect signatures are swallowed, and only for GET/HEAD requests
  to static-asset paths:
    1. a ``RuntimeError`` whose message contains "Response content shorter
       than Content-Length"; and
    2. an ``OSError`` whose ``errno`` is a peer-gone code (EPIPE / ECONNRESET /
       ESHUTDOWN / EIO) AND that was raised AFTER the response had already
       started (``http.response.start`` was sent). The response-started gate is
       what keeps an ambiguous ``EIO`` honest: a socket-write failure to a gone
       peer can only happen once we have begun flushing the body, whereas a disk
       / read ``EIO`` raised before any bytes leave (failed open / first read)
       has ``response_started == False`` and is re-raised so a broken asset still
       pages instead of silently white-screening the client.
  We deliberately do NOT swallow the "...longer than..." RuntimeError variant: a
  response with MORE bytes than its declared Content-Length is a server-side
  bug, not a client disconnect, and must still page. An ``OSError`` with any
  other ``errno`` (or none), or any ``OSError`` before the response started, is
  also re-raised. Anything else (a genuine API truncation, any other exception,
  any non-static path) is re-raised unchanged. If the static-path classifier
  cannot be imported we fail safe by re-raising (prefer paging over silencing).

  When (and only when) a disconnect IS swallowed we also flip a per-request
  ContextVar. uvicorn still logs ``ASGI callable returned without completing
  response.`` afterwards (the response never completed and no middleware can stop
  that log — the request scope is gone). The ``before_send`` backstop in
  ``infra/cloud_observability`` reads this ContextVar to drop ONLY that follow-on
  log, and only for a request we ourselves just classified as a benign static
  disconnect — so a real streaming/export handler that returns mid-response (no
  swallow, ContextVar unset) still pages.

  Registered just INSIDE CORSMiddleware (CORS stays the outermost layer) but
  OUTSIDE every other app middleware, so it intercepts the exception before it
  reaches uvicorn / the Sentry ASGI integration.
"""

from __future__ import annotations

import errno as _errno
import logging
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Only the "shorter than" variant is a benign client-disconnect signature. The
# "longer than" variant means the app emitted MORE bytes than it declared — a
# server bug — so it is intentionally NOT listed and will keep paging.
_BENIGN_DISCONNECT_MSG = "Response content shorter than Content-Length"

# OSError ``errno`` values that unambiguously mean "the peer went away while we
# were writing the response". EIO(5) is included because behind the deploy
# reverse-proxy a closed upstream socket surfaces as Input/output error; the
# static-path scope (below) keeps a genuine disk/IO fault on a non-asset route
# from ever being silenced.
_BENIGN_DISCONNECT_ERRNOS = frozenset({
    _errno.EPIPE,       # 32  broken pipe
    _errno.ECONNRESET,  # 104 connection reset by peer
    _errno.ESHUTDOWN,   # 108 cannot send after transport endpoint shutdown
    _errno.EIO,         # 5   input/output error (proxied upstream closed)
})

# Cumulative count of swallowed disconnects in this process (resets on restart).
_STATIC_DISCONNECT_SWALLOW_COUNT = 0

# Per-request flag, flipped True ONLY when this request's exception was just
# classified as a benign static client-disconnect and swallowed. uvicorn logs
# the follow-on "ASGI callable returned without completing response." in the SAME
# asyncio task/context right after ``app`` returns, so the ``before_send``
# backstop can read this to drop that one log without suppressing a real
# mid-response handler bug (which never swallows → flag stays False). Default
# False; a fresh request runs in a fresh task context, so there is no staleness.
_benign_static_disconnect_in_flight: ContextVar[bool] = ContextVar(
    "benign_static_disconnect_in_flight", default=False
)


def get_static_disconnect_swallow_count() -> int:
    """Number of benign static client-disconnects swallowed since process start."""
    return _STATIC_DISCONNECT_SWALLOW_COUNT


def benign_static_disconnect_in_flight() -> bool:
    """True iff THIS request/context just swallowed a benign static disconnect."""
    try:
        return _benign_static_disconnect_in_flight.get()
    except Exception:
        return False


class StaticDisconnectSilencerMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Track whether the response actually started (``http.response.start``
        # was sent). A peer-gone OSError can only happen once we have begun
        # flushing bytes; an OSError before that is a different (real) fault.
        response_started = False

        async def _tracking_send(message) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _tracking_send)
        except (RuntimeError, OSError) as exc:
            if not _is_benign_static_disconnect(scope, exc, response_started):
                raise
            # Mark THIS request so the before_send backstop drops only the
            # uvicorn follow-on log that this swallow is about to produce.
            _benign_static_disconnect_in_flight.set(True)
            global _STATIC_DISCONNECT_SWALLOW_COUNT
            _STATIC_DISCONNECT_SWALLOW_COUNT += 1
            method = str(scope.get("method", "GET")).upper()
            path = scope.get("path", "") or ""
            logger.info(
                "swallowed benign static client-disconnect %s %s (cumulative=%d)",
                method,
                path,
                _STATIC_DISCONNECT_SWALLOW_COUNT,
            )


def _is_benign_static_disconnect(
    scope: Scope, exc: BaseException, response_started: bool
) -> bool:
    # Classify the disconnect signature first. An OSError qualifies only when its
    # ``errno`` is a peer-gone code AND the response had already started (a
    # socket-write failure); an OSError with any other/absent errno, or before
    # the response started, is a real I/O fault and must keep paging. A
    # RuntimeError qualifies only when its message contains "shorter than
    # Content-Length" ("longer than" is a server bug and is not matched).
    if isinstance(exc, OSError):
        if exc.errno not in _BENIGN_DISCONNECT_ERRNOS:
            return False
        if not response_started:
            return False
    elif _BENIGN_DISCONNECT_MSG not in str(exc):
        return False
    # Reuse the single source of truth for "what counts as a static asset path"
    # so this source-side silencer and the before_send backstop never drift.
    try:
        from infra.cloud_observability import _is_static_asset_target
    except Exception:
        # Without the classifier we cannot prove the path is static → fail safe
        # by NOT swallowing (the error still pages, current behaviour preserved).
        return False
    method = str(scope.get("method", "GET")).upper()
    path = scope.get("path", "") or ""
    return _is_static_asset_target(method, path)
