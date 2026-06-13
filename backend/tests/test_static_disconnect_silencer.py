"""Tests for StaticDisconnectSilencerMiddleware.

The middleware must swallow ONLY the benign uvicorn client-disconnect
RuntimeError ("Response content shorter/longer than Content-Length") for
static-asset GET/HEAD requests, and re-raise everything else so real bugs page.
"""

import asyncio

import pytest

from middleware.static_disconnect_silencer import (
    StaticDisconnectSilencerMiddleware,
    get_static_disconnect_swallow_count,
)

_SHORT = "Response content shorter than Content-Length"
_LONG = "Response content longer than Content-Length"


def _scope(method: str, path: str, typ: str = "http") -> dict:
    return {"type": typ, "method": method, "path": path, "headers": []}


def _raising_app(exc: BaseException):
    async def app(scope, receive, send):
        raise exc

    return app


async def _noop_receive():  # pragma: no cover - never invoked in these tests
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(message):  # pragma: no cover - never invoked
    return None


def _run(mw: StaticDisconnectSilencerMiddleware, scope: dict):
    return asyncio.run(mw(scope, _noop_receive, _noop_send))


def test_swallows_benign_short_on_static_js():
    before = get_static_disconnect_swallow_count()
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_SHORT)))
    _run(mw, _scope("GET", "/js/index-abc123.js"))  # must NOT raise
    assert get_static_disconnect_swallow_count() == before + 1


def test_swallows_benign_short_on_static_asset_css_head():
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_SHORT)))
    _run(mw, _scope("HEAD", "/assets/index-xyz.css"))  # must NOT raise


def test_reraises_longer_than_variant_even_on_static_path():
    # "longer than Content-Length" = server emitted MORE bytes than declared,
    # a server bug, NOT a benign client disconnect → must still page.
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_LONG)))
    with pytest.raises(RuntimeError, match="longer than Content-Length"):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_swallows_on_uploaded_image_by_extension():
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_SHORT)))
    _run(mw, _scope("GET", "/api/uploads/photo.png"))  # static by extension


def test_reraises_benign_message_on_api_path():
    # Same benign message but a NON-static API path → must page, not swallow.
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_SHORT)))
    with pytest.raises(RuntimeError, match="shorter than Content-Length"):
        _run(mw, _scope("GET", "/api/pms/bookings"))


def test_reraises_benign_message_on_non_get_method():
    # _is_static_asset_target only treats GET/HEAD as static.
    mw = StaticDisconnectSilencerMiddleware(_raising_app(RuntimeError(_SHORT)))
    with pytest.raises(RuntimeError):
        _run(mw, _scope("POST", "/js/index-abc123.js"))


def test_reraises_other_runtime_error_on_static_path():
    mw = StaticDisconnectSilencerMiddleware(
        _raising_app(RuntimeError("some other failure"))
    )
    with pytest.raises(RuntimeError, match="some other failure"):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_reraises_non_runtime_error():
    mw = StaticDisconnectSilencerMiddleware(_raising_app(ValueError("boom")))
    with pytest.raises(ValueError, match="boom"):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_passes_through_non_http_scope():
    # websocket / lifespan scopes must be forwarded untouched.
    seen = {}

    async def app(scope, receive, send):
        seen["called"] = True

    mw = StaticDisconnectSilencerMiddleware(app)
    asyncio.run(mw({"type": "websocket"}, _noop_receive, _noop_send))
    assert seen.get("called") is True
