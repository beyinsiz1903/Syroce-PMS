"""Regression coverage for CSRF handling of native token authentication."""

from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from security.csrf_guard import csrf_guard_middleware


class _Request:
    def __init__(self, path: str, headers: dict[str, str] | None = None):
        self.method = "POST"
        self.headers = headers or {}
        self.url = SimpleNamespace(path=path)


async def _allowed_response(_request):
    return JSONResponse(status_code=200, content={"ok": True})


@pytest.mark.asyncio
async def test_native_login_without_origin_is_allowed():
    response = await csrf_guard_middleware(
        _Request("/api/auth/login", {"X-Syroce-Client": "mobile"}),
        _allowed_response,
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_originless_login_without_native_marker_is_blocked(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    response = await csrf_guard_middleware(_Request("/api/auth/login"), _allowed_response)

    assert response.status_code == 403
    assert b"Missing Origin" in response.body


@pytest.mark.asyncio
async def test_native_marker_does_not_bypass_other_writes(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    response = await csrf_guard_middleware(
        _Request("/api/reservations", {"X-Syroce-Client": "mobile"}),
        _allowed_response,
    )

    assert response.status_code == 403
