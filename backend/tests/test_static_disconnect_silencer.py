import errno

"""Tests for StaticDisconnectSilencerMiddleware.

The middleware must swallow ONLY the benign uvicorn client-disconnect
RuntimeError ("Response content shorter/longer than Content-Length") for
static-asset GET/HEAD requests, and re-raise everything else so real bugs page.
"""

import asyncio

import pytest

from middleware.static_disconnect_silencer import (
    StaticDisconnectSilencerMiddleware,
    benign_static_disconnect_in_flight,
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


def _app_start_then_raise(exc: BaseException):
    """App that STARTS the response (sends http.response.start) then raises.

    Models a peer-gone socket-write failure: bytes had begun flushing before the
    error, so the silencer's response-started gate is satisfied.
    """

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
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


def test_swallows_oserror_eio_on_static_js():
    # Behind the deploy proxy a closed upstream socket surfaces as EIO(5) AFTER
    # the response has started (bytes were flushing) → benign peer-gone.
    before = get_static_disconnect_swallow_count()
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(OSError(errno.EIO, "Input/output error"))
    )
    _run(mw, _scope("GET", "/js/vendor-radix-abc.js"))  # must NOT raise
    assert get_static_disconnect_swallow_count() == before + 1


def test_swallows_broken_pipe_on_static_asset():
    # BrokenPipeError (EPIPE/32) is an OSError subclass with errno set.
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(BrokenPipeError(32, "Broken pipe"))
    )
    _run(mw, _scope("HEAD", "/assets/index-xyz.css"))  # must NOT raise


def test_swallows_connection_reset_on_static_image():
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(ConnectionResetError(errno.ECONNRESET, "Connection reset by peer"))
    )
    _run(mw, _scope("GET", "/api/uploads/photo.png"))  # static by extension


def test_reraises_disconnect_oserror_before_response_started():
    # EIO BEFORE any bytes flush (failed open / first read) is a real disk/IO
    # fault, NOT a peer-gone write failure → must page even on a static path.
    mw = StaticDisconnectSilencerMiddleware(
        _raising_app(OSError(errno.EIO, "Input/output error"))
    )
    with pytest.raises(OSError):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_reraises_oserror_with_non_disconnect_errno_on_static_path():
    # ENOENT(2) reading the asset is a real I/O fault, not a disconnect → page,
    # even though the response had started.
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(OSError(2, "No such file or directory"))
    )
    with pytest.raises(OSError):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_reraises_oserror_without_errno_on_static_path():
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(OSError("opaque io"))
    )
    with pytest.raises(OSError):
        _run(mw, _scope("GET", "/js/index-abc123.js"))


def test_reraises_disconnect_oserror_on_api_path():
    # A peer-gone errno (response started) on a NON-static API path must page.
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(OSError(errno.EIO, "Input/output error"))
    )
    with pytest.raises(OSError):
        _run(mw, _scope("GET", "/api/pms/bookings"))


def test_reraises_disconnect_oserror_on_non_get_method():
    mw = StaticDisconnectSilencerMiddleware(
        _app_start_then_raise(OSError(104, "Connection reset by peer"))
    )
    with pytest.raises(OSError):
        _run(mw, _scope("POST", "/js/index-abc123.js"))


def test_contextvar_set_after_benign_swallow_in_same_context():
    # The before_send backstop relies on this flag being True in the SAME
    # task/context immediately after the swallow.
    async def scenario():
        mw = StaticDisconnectSilencerMiddleware(
            _app_start_then_raise(OSError(errno.EIO, "Input/output error"))
        )
        await mw(_scope("GET", "/js/a.js"), _noop_receive, _noop_send)
        return benign_static_disconnect_in_flight()

    assert asyncio.run(scenario()) is True


def test_contextvar_unset_when_exception_reraised():
    # A real (re-raised) error must NOT flip the flag, or before_send would
    # later drop an unrelated incomplete-response log.
    async def scenario():
        mw = StaticDisconnectSilencerMiddleware(_raising_app(ValueError("boom")))
        try:
            await mw(_scope("GET", "/js/a.js"), _noop_receive, _noop_send)
        except ValueError:
            pass
        return benign_static_disconnect_in_flight()

    assert asyncio.run(scenario()) is False


def test_passes_through_non_http_scope():
    # websocket / lifespan scopes must be forwarded untouched.
    seen = {}

    async def app(scope, receive, send):
        seen["called"] = True

    mw = StaticDisconnectSilencerMiddleware(app)
    asyncio.run(mw({"type": "websocket"}, _noop_receive, _noop_send))
    assert seen.get("called") is True
