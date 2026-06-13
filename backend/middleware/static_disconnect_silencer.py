"""StaticDisconnectSilencerMiddleware — swallow benign client-disconnect noise.

Why:
  uvicorn raises ``RuntimeError("Response content shorter than Content-Length")``
  when a client disconnects mid-download of a static asset: StaticFiles stamped
  ``Content-Length`` from the file size, then the socket closed before all bytes
  were flushed. Mobile browsers cancel
  asset requests aggressively (prefetch / fast navigation), so this is benign
  client backpressure — there is nothing to send to a client that has already
  left.

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
  Only a ``RuntimeError`` whose message is exactly "Response content shorter
  than Content-Length", only for GET/HEAD, and only for static-asset paths is
  swallowed. We deliberately do NOT swallow the "...longer than..." variant: a
  response with MORE bytes than its declared Content-Length is a server-side
  bug, not a client disconnect, and must still page. Anything else (a genuine
  API truncation, any other exception) is re-raised unchanged. If the static-
  path classifier cannot be imported we fail safe by re-raising (prefer paging
  over silencing).

  Registered just INSIDE CORSMiddleware (CORS stays the outermost layer) but
  OUTSIDE every other app middleware, so it intercepts the exception before it
  reaches uvicorn / the Sentry ASGI integration.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Only the "shorter than" variant is a benign client-disconnect signature. The
# "longer than" variant means the app emitted MORE bytes than it declared — a
# server bug — so it is intentionally NOT listed and will keep paging.
_BENIGN_DISCONNECT_MSG = "Response content shorter than Content-Length"

# Cumulative count of swallowed disconnects in this process (resets on restart).
_STATIC_DISCONNECT_SWALLOW_COUNT = 0


def get_static_disconnect_swallow_count() -> int:
    """Number of benign static client-disconnects swallowed since process start."""
    return _STATIC_DISCONNECT_SWALLOW_COUNT


class StaticDisconnectSilencerMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except RuntimeError as exc:
            if not _is_benign_static_disconnect(scope, exc):
                raise
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


def _is_benign_static_disconnect(scope: Scope, exc: BaseException) -> bool:
    if _BENIGN_DISCONNECT_MSG not in str(exc):
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
