"""
UploadSizeLimitMiddleware — fail-fast body-size guard for write requests.

Why (architect feedback D, v39 turu):
  Endpoint-level `await file.read(MAX+1)` is *too late* — multipart bodies are
  already received and spooled by Starlette/python-multipart by the time the
  endpoint coroutine runs. A determined attacker still consumes bandwidth,
  parser CPU, temp disk, and worker time.

The middleware rejects oversize bodies *before* parsing kicks in:
  - Fast path: when the client honestly advertises `Content-Length`, we reject
    by header inspection (zero body bytes consumed thanks to Expect/100-continue).
  - Chunked path (v43, Bug BI): when no `Content-Length` is present (chunked
    transfer-encoding), we wrap the ASGI `receive` callable and stream-count
    bytes; if the cumulative body exceeds the cap we send a 413 immediately
    and never invoke the downstream app. This closes the previously documented
    bypass where chunked POSTs let attackers ship arbitrary-size bodies.

Limits:
  - Multipart uploads: 12 MB (covers the 5 MB image cap + form-overhead headroom)
  - Other write methods (JSON / urlencoded): 4 MB
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_MAX_BYTES = 12 * 1024 * 1024
JSON_MAX_BYTES = 4 * 1024 * 1024

_WRITE_METHODS = {"POST", "PUT", "PATCH"}


def _too_large_response(cap: int) -> JSONResponse:
    mb = cap // (1024 * 1024)
    return JSONResponse(
        {"detail": f"Yuklenen icerik cok buyuk (en fazla {mb} MB)."},
        status_code=413,
    )


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method", "").upper() not in _WRITE_METHODS:
            await self.app(scope, receive, send)
            return

        # Headers come as list of (bytes, bytes) tuples.
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        cl_raw = headers.get("content-length")
        ct_raw = (headers.get("content-type") or "").lower()
        te_raw = (headers.get("transfer-encoding") or "").lower()

        is_multipart = ct_raw.startswith("multipart/")
        cap = MULTIPART_MAX_BYTES if is_multipart else JSON_MAX_BYTES

        # v43 hardening: if Transfer-Encoding is present (typically `chunked`),
        # RFC 7230 §3.3.3 says Content-Length MUST be ignored. Some upstream
        # proxy/app pairs disagree on which header wins → request-smuggling
        # / size-cap bypass surface. We force the streaming path whenever TE
        # is present, regardless of any (potentially attacker-supplied) CL.
        if te_raw:
            cl_raw = None

        # Fast path: honest Content-Length → header-only check, no body read.
        if cl_raw is not None:
            try:
                content_length = int(cl_raw)
            except ValueError:
                await self.app(scope, receive, send)
                return

            if content_length > cap:
                response = _too_large_response(cap)
                await response(scope, receive, send)
                return

            await self.app(scope, receive, send)
            return

        # Chunked path (no Content-Length). Drain the body up to `cap` bytes
        # *before* invoking the downstream app: if the cumulative size exceeds
        # the cap we send a 413 immediately; otherwise we replay the buffered
        # chunks downstream so handlers see the full body unchanged.
        buffered: list[Message] = []
        received = 0
        more = True
        while more:
            msg = await receive()
            mtype = msg.get("type")
            if mtype == "http.disconnect":
                buffered.append(msg)
                more = False
                break
            if mtype != "http.request":
                buffered.append(msg)
                continue
            body = msg.get("body", b"") or b""
            received += len(body)
            if received > cap:
                response = _too_large_response(cap)
                await response(scope, receive, send)
                return
            buffered.append(msg)
            more = bool(msg.get("more_body", False))

        # Body is within cap → replay buffered messages to downstream.
        iter_msgs = iter(buffered)

        async def replay_receive() -> Message:
            try:
                return next(iter_msgs)
            except StopIteration:
                return await receive()

        await self.app(scope, replay_receive, send)
