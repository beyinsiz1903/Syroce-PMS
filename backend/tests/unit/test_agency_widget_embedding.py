from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.security import JWT_ALGORITHM, JWT_SECRET
from routers import marketplace_b2b as market


@pytest.fixture
def agency(monkeypatch):
    document = {
        "id": "agency-widget-test",
        "name": "Test Travel",
        "status": "active",
        "widget_token_version": 1,
        "allowed_widget_origins": ["https://Agency.Example:443/", "https://booking.example"],
    }
    collection = SimpleNamespace(find_one=AsyncMock(return_value=document))
    monkeypatch.setattr(market, "get_system_db", lambda: SimpleNamespace(marketplace_agencies=collection))
    return document, collection


@pytest.mark.parametrize(("value", "expected"), [
    ("https://Agency.Example:443/", "https://agency.example"),
    (" https://agency.example:8443/ ", "https://agency.example:8443"),
    ("http://localhost:3000/", "http://localhost:3000"),
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("https://[::1]:443", "https://[::1]"),
])
def test_widget_origin_is_canonical(value, expected):
    assert market._widget_origin(value) == expected


@pytest.mark.parametrize("value", [
    "https://agency.example/path", "https://agency.example?query=1",
    "https://agency.example#fragment", "https://agency.example?", "https://agency.example#",
    "https://user:pass@agency.example", "https://*.example", "https://agency.example;",
    "https://agency.example\r\nX-Frame-Options: DENY",
    "https://agency.example; frame-ancestors *", "http://agency.example",
    "http://localhost.evil.example", "https://agency.example:99999",
    "https://agency.example:0", "https://agency.example\\evil", "",
])
def test_widget_settings_reject_non_origins_and_policy_injection(value):
    # Blank lines are deliberately ignored in settings, but not in API headers.
    if not value:
        with pytest.raises(ValueError):
            market._widget_origin(value)
        return
    with pytest.raises(ValidationError):
        market.MarketplacePortalSettingsUpdate(
            name="Test Travel", contact_email="info@example.com", allowed_widget_origins=[value],
        )


@pytest.mark.asyncio
async def test_frame_policy_uses_live_allowlist_and_never_contains_the_token(agency):
    document, collection = agency
    token = market._marketplace_widget_token(document)
    response = await market.marketplace_widget_frame_policy(token)
    assert response.status_code == 204
    assert response.headers["x-widget-frame-policy"] == (
        "frame-ancestors https://agency.example https://booking.example;"
    )
    assert response.headers["cache-control"] == "no-store"
    assert token not in str(response.headers)
    assert response.body == b""
    collection.find_one.assert_awaited_with({"id": document["id"], "status": "active"}, {"_id": 0})

    document["allowed_widget_origins"] = ["https://new.example"]
    response = await market.marketplace_widget_frame_policy(token)
    assert response.headers["x-widget-frame-policy"] == "frame-ancestors https://new.example;"


@pytest.mark.asyncio
@pytest.mark.parametrize("token_kind", ["missing", "bad", "access", "old_version", "bad_version"])
async def test_frame_policy_fails_closed_for_invalid_tokens(agency, token_kind):
    document, _ = agency
    claims = {"type": "marketplace_widget", "agency_id": document["id"], "version": 1}
    if token_kind == "access":
        claims["type"] = "access"
    if token_kind == "old_version":
        claims["version"] = 0
    if token_kind == "bad_version":
        claims["version"] = "not-a-version"
    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    if token_kind == "missing":
        token = None
    if token_kind == "bad":
        token = "invalid-token"
    with pytest.raises(HTTPException) as error:
        await market.marketplace_widget_frame_policy(token)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_frame_policy_blocks_inactive_agency_and_invalid_stored_origins(agency):
    document, collection = agency
    token = market._marketplace_widget_token(document)
    collection.find_one.return_value = None
    with pytest.raises(HTTPException) as error:
        await market.marketplace_widget_frame_policy(token)
    assert error.value.status_code == 403
    collection.find_one.return_value = document
    for origins in ([], ["https://agency.example; frame-ancestors *"]):
        document["allowed_widget_origins"] = origins
        with pytest.raises(HTTPException) as error:
            await market.marketplace_widget_frame_policy(token)
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_api_origin_and_frame_policy_share_canonical_allowlist(agency):
    document, _ = agency
    token = market._marketplace_widget_token(document)
    result = await market.get_marketplace_widget_agency(token, "https://AGENCY.EXAMPLE:443/")
    assert result["widget_origin"] == "https://agency.example"
    for origin in (None, "https://attacker.example", "https://agency.example/path"):
        with pytest.raises(HTTPException) as error:
            await market.get_marketplace_widget_agency(token, origin)
        assert error.value.status_code == 403


def test_frame_policy_http_contract(agency):
    document, _ = agency
    app = FastAPI()
    app.include_router(market.router)
    with TestClient(app) as client:
        path = "/api/marketplace/v1/widget/frame-policy"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"X-Widget-Token": market._marketplace_widget_token(document)})
        assert response.status_code == 204
        assert response.content == b""
        assert response.headers["x-widget-frame-policy"].startswith("frame-ancestors https://agency.example")


@pytest.mark.parametrize("email", [None, "", "   ", "guest@example.com", " guest@example.com "])
def test_reservation_optional_email(email):
    data = market.MarketplaceReservationCreate(
        tenant_id="hotel-1", room_type="Standard", check_in="2026-11-01",
        check_out="2026-11-02", guest_name="Test Guest", guest_email=email,
    )
    assert data.guest_email == (email.strip() or None if isinstance(email, str) else None)


def test_reservation_still_rejects_malformed_nonblank_email():
    with pytest.raises(ValidationError):
        market.MarketplaceReservationCreate(
            tenant_id="hotel-1", room_type="Standard", check_in="2026-11-01",
            check_out="2026-11-02", guest_name="Test Guest", guest_email="not-an-email",
        )
