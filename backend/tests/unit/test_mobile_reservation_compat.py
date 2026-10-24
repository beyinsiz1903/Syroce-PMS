"""Installed iOS clients share the canonical handler, auth and tenant boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from core.security import get_current_user
from routers import mobile_reservation_compat, reservation_detail

CANONICAL = "/api/pms/reservations/booking-a/full-detail"
COMPAT = "/api/reservations/booking-a/full-detail"


def app_for(user=None):
    app = FastAPI()
    app.include_router(reservation_detail.router)
    app.include_router(mobile_reservation_compat.router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()

    async def to_list(self, _limit):
        return self.rows


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CANONICAL, COMPAT])
async def test_both_routes_return_the_same_authorized_financial_account(monkeypatch, path):
    booking = {"id": "booking-a", "tenant_id": "tenant-a", "guest_name": "Örnek Misafir", "status": "confirmed", "currency": "TRY", "total_amount": 100, "check_in": "2026-10-27", "check_out": "2026-10-28"}
    rows = {
        "folios": [{"id": "folio-a", "booking_id": "booking-a", "tenant_id": "tenant-a", "currency": "TRY", "status": "open"}],
        "folio_charges": [{"id": "charge-a", "folio_id": "folio-a", "amount": 100, "total": 100, "currency": "TRY", "charge_category": "room"}],
        "payments": [{"id": "payment-a", "folio_id": "folio-a", "amount": 25, "currency": "TRY", "method": "cash", "status": "paid"}],
    }
    fields = ["folios", "folio_charges", "payments", "extra_charges", "reservation_notes", "reservation_activity_log", "audit_logs", "room_move_history", "daily_rates", "booking_guests", "communication_logs", "deposits"]
    collections = {field: SimpleNamespace(find=lambda *_args, field=field: Cursor(rows.get(field, []))) for field in fields}
    collections["bookings"] = SimpleNamespace(find_one=AsyncMock(return_value=booking))
    monkeypatch.setattr(reservation_detail, "db", SimpleNamespace(**collections))
    monkeypatch.setattr(reservation_detail, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-25"}))
    monkeypatch.setattr(reservation_detail, "get_accommodation_tax_rate", AsyncMock(return_value=0.02))
    monkeypatch.setattr(reservation_detail, "resolve_legacy_hotelrunner_note", AsyncMock(return_value=None))
    monkeypatch.setattr(reservation_detail, "_field_enc", SimpleNamespace(decrypt_document=lambda doc, **_kwargs: doc))
    user = SimpleNamespace(role="admin", tenant_id="tenant-a", hotel_id="100001")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(user)), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 200, response.text
    if path == COMPAT:
        assert response.headers["Cache-Control"] == "private, no-store"
    body = response.json()
    assert body["booking"]["id"] == "booking-a"
    assert body["folios"][0]["id"] == "folio-a"
    assert body["payments"][0]["amount"] == 25
    assert body["summary"]["gross_total"] == 100
    assert body["summary"]["reservation_total_due"] == 75
    collections["bookings"].find_one.assert_awaited_once_with({"id": "booking-a", "tenant_id": "tenant-a"}, {"_id": 0})


def test_compat_route_is_read_only_and_reuses_the_canonical_endpoint():
    routes = mobile_reservation_compat.router.routes
    assert len(routes) == 1
    route = routes[0]
    assert route.path == "/api/reservations/{booking_id}/full-detail"
    assert route.methods == {"GET"}
    assert route.endpoint is reservation_detail.get_reservation_full_detail
    assert route.include_in_schema is False
    assert any(dependency.call is get_current_user for dependency in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_legacy_path_cannot_bypass_canonical_resource_policy(monkeypatch):
    bookings = SimpleNamespace(find_one=AsyncMock(side_effect=AssertionError("No DB read after denied policy")))
    monkeypatch.setattr(reservation_detail, "db", SimpleNamespace(bookings=bookings))
    denied = Mock(side_effect=HTTPException(403, "PAGE_ACCESS_DENIED"))
    monkeypatch.setattr(mobile_reservation_compat, "enforce_request_access", denied)
    user = SimpleNamespace(role="admin", tenant_id="tenant-a", hotel_id="100001")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(user)), base_url="http://test") as client:
        response = await client.get(COMPAT)
    assert response.status_code == 403
    denied.assert_called_once_with(user, CANONICAL, "GET")
    bookings.find_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CANONICAL, COMPAT])
async def test_both_routes_require_authentication(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for()), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CANONICAL, COMPAT])
async def test_missing_booking_uses_authenticated_tenant_and_keeps_business_404(monkeypatch, path):
    bookings = SimpleNamespace(find_one=AsyncMock(return_value=None))
    monkeypatch.setattr(reservation_detail, "db", SimpleNamespace(bookings=bookings))
    user = SimpleNamespace(role="admin", tenant_id="tenant-a", hotel_id="100001")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(user)), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Rezervasyon bulunamadı"}
    bookings.find_one.assert_awaited_once_with({"id": "booking-a", "tenant_id": "tenant-a"}, {"_id": 0})


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CANONICAL, COMPAT])
async def test_non_superadmin_cannot_select_another_tenant(monkeypatch, path):
    bookings = SimpleNamespace(find_one=AsyncMock(side_effect=AssertionError("No cross-tenant DB read is allowed")))
    monkeypatch.setattr(reservation_detail, "db", SimpleNamespace(bookings=bookings))
    user = SimpleNamespace(role="admin", tenant_id="tenant-a", hotel_id="100001")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(user)), base_url="http://test") as client:
        response = await client.get(path, headers={"X-Tenant-ID": "tenant-b"})
    assert response.status_code == 404
    bookings.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_compat_path_does_not_create_a_payment_or_checkout_alias():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for()), base_url="http://test") as client:
        response = await client.post(COMPAT, json={"amount": 100})
    assert response.status_code == 405
