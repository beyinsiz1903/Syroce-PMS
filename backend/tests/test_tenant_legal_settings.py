from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from domains.admin.router import hotel as hotel_router
from domains.admin.schemas import UpdateHotelInfoRequest
from models.enums import UserRole
from models.schemas import GuestCreate
from modules.pms_core.guest_identity import deduplicate_guest_records, find_existing_guest_by_identity
from routers import pms_bookings, pms_guests
from routers.hotel_services_pkg import invoices as invoices_router
from routers.hotel_services_pkg.invoices import _format_document_date, _format_document_money, _merge_hotel_document_branding
from routers.pms_bookings import QuickBookingCreate
from routers.regulatory import _normalize_tenant_legal_profile


class _TenantCollection:
    def __init__(self, tenant: dict):
        self.tenant = dict(tenant)

    async def find_one(self, query, _projection=None):
        if query.get("id") != self.tenant.get("id"):
            return None
        return dict(self.tenant)

    async def update_one(self, query, update):
        if query.get("id") != self.tenant.get("id"):
            return SimpleNamespace(matched_count=0, modified_count=0)
        self.tenant.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)


@pytest.mark.asyncio
async def test_hotel_admin_can_update_legal_fields_and_aliases(monkeypatch):
    tenants = _TenantCollection({"id": "tenant-1", "subscription_tier": "enterprise"})
    monkeypatch.setattr(hotel_router, "db", SimpleNamespace(tenants=tenants))
    monkeypatch.setattr(hotel_router, "_cache_mgr", None)

    result = await hotel_router.update_hotel_info(
        UpdateHotelInfoRequest(
            property_name="The Canyon Kartepe",
            tax_number="1234567890",
            license_number="TGA-2026-001",
            license_expires_at="2027-08-29",
            star_rating=4,
        ),
        SimpleNamespace(tenant_id="tenant-1", role=UserRole.ADMIN),
    )

    tenant = result["tenant"]
    assert tenant["property_name"] == "The Canyon Kartepe"
    assert tenant["hotel_name"] == "The Canyon Kartepe"
    assert tenant["tax_number"] == "1234567890"
    assert tenant["tax_no"] == "1234567890"
    assert tenant["license_number"] == "TGA-2026-001"
    assert tenant["license_expires_at"] == "2027-08-29"
    assert tenant["star_rating"] == 4


@pytest.mark.asyncio
async def test_legal_update_rejects_invalid_tax_number(monkeypatch):
    tenants = _TenantCollection({"id": "tenant-1", "subscription_tier": "enterprise"})
    monkeypatch.setattr(hotel_router, "db", SimpleNamespace(tenants=tenants))
    monkeypatch.setattr(hotel_router, "_cache_mgr", None)

    with pytest.raises(HTTPException) as exc:
        await hotel_router.update_hotel_info(
            UpdateHotelInfoRequest(tax_number="12345"),
            SimpleNamespace(tenant_id="tenant-1", role=UserRole.ADMIN),
        )

    assert exc.value.status_code == 422
    assert "VKN" in exc.value.detail


def test_regulatory_profile_accepts_current_tenant_field_names():
    normalized = _normalize_tenant_legal_profile(
        {
            "property_name": "The Canyon Kartepe",
            "tax_number": "1234567890",
            "contact_phone": "+905551112233",
        }
    )

    assert normalized["hotel_name"] == "The Canyon Kartepe"
    assert normalized["tax_no"] == "1234567890"
    assert normalized["phone"] == "+905551112233"


def test_voucher_branding_prefers_real_tenant_name_and_keeps_uploaded_logo():
    branding = _merge_hotel_document_branding(
        {"hotel_name": "Hotel", "logo_data": "data:image/png;base64,AAAA", "hotel_email": "info@example.com"},
        {"property_name": "The Canyon Kartepe", "address": "Kartepe", "phone": "+905551112233"},
    )

    assert branding["hotel_name"] == "The Canyon Kartepe"
    assert branding["logo_data"] == "data:image/png;base64,AAAA"
    assert branding["hotel_address"] == "Kartepe"
    assert branding["hotel_phone"] == "+905551112233"
    assert _format_document_date("2026-08-29T14:00:00Z") == "29.08.2026"


def test_voucher_money_uses_turkish_number_format_and_currency_label():
    assert _format_document_money(4510, "TRY") == "4.510,00 TL"
    assert _format_document_money("1250.5", "EUR") == "1.250,50 EUR"
    assert _format_document_money(None, "TRY") == "0,00 TL"


class _VoucherCollection:
    def __init__(self, rows: list[dict]):
        self.rows = [dict(row) for row in rows]

    async def find_one(self, query, _projection=None):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None


@pytest.mark.asyncio
async def test_voucher_includes_total_paid_and_balance(monkeypatch):
    tenant_id = "tenant-1"
    booking_id = "booking-12345678"
    monkeypatch.setattr(
        invoices_router,
        "db",
        SimpleNamespace(
            bookings=_VoucherCollection(
                [
                    {
                        "id": booking_id,
                        "tenant_id": tenant_id,
                        "guest_name": "Süleyman Çakıroğlu",
                        "room_id": "room-201",
                        "room_number": "201",
                        "check_in": "2026-08-29",
                        "check_out": "2026-08-30",
                        "total_amount": 4510,
                        "paid_amount": 1000,
                        "currency": "TRY",
                    }
                ]
            ),
            guests=_VoucherCollection([]),
            rooms=_VoucherCollection(
                [{"id": "room-201", "tenant_id": tenant_id, "room_number": "201", "room_type": "standart"}]
            ),
            hotel_settings=_VoucherCollection([{"tenant_id": tenant_id, "hotel_name": "Hotel"}]),
            tenants=_VoucherCollection([{"id": tenant_id, "property_name": "The Canyon Kartepe"}]),
        ),
    )

    result = await invoices_router.generate_voucher(booking_id, SimpleNamespace(tenant_id=tenant_id))

    assert result["total_amount"] == 4510
    assert result["paid_amount"] == 1000
    assert result["balance"] == 3510
    assert "4.510,00 TL" in result["voucher_html"]
    assert "1.000,00 TL" in result["voucher_html"]
    assert "3.510,00 TL" in result["voucher_html"]


class _GuestCursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def limit(self, _limit):
        return self

    async def to_list(self, limit):
        return [dict(row) for row in self.rows[:limit]]


class _GuestCollection:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.inserted: list[dict] = []

    def find(self, _query, _projection=None):
        return _GuestCursor(self.rows)

    async def insert_one(self, doc):
        self.inserted.append(doc)


def test_guest_search_duplicates_collapse_to_strongest_profile():
    rows = [
        {"id": "old", "name": "Salih Bey", "id_number": "12345678901", "total_stays": 1},
        {"id": "canonical", "name": "salih  bey", "id_number": "123 456 789 01", "total_stays": 4},
        {"id": "other", "name": "Salih Bey", "id_number": "99999999999", "total_stays": 2},
    ]

    deduplicated = deduplicate_guest_records(rows)

    assert [guest["id"] for guest in deduplicated] == ["canonical", "other"]


def test_name_only_duplicate_is_collapsed_only_for_search_suggestions():
    rows = [
        {"id": "first", "name": "Salih Bey"},
        {"id": "second", "name": " salih  bey ", "total_stays": 2},
    ]

    assert [guest["id"] for guest in deduplicate_guest_records(rows)] == ["second"]


@pytest.mark.asyncio
async def test_identity_lookup_reuses_same_document_number():
    guests = _GuestCollection(
        [{"id": "existing", "tenant_id": "tenant-1", "name": "Salih Bey", "id_number": "12345678901"}]
    )

    match = await find_existing_guest_by_identity(
        guests,
        "tenant-1",
        {"name": "Salih Bey", "id_number": "123 456 789 01"},
    )

    assert match["id"] == "existing"


@pytest.mark.asyncio
async def test_guest_create_returns_existing_identity_without_insert(monkeypatch):
    guests = _GuestCollection(
        [{"id": "existing", "tenant_id": "tenant-1", "name": "Salih Bey", "id_number": "12345678901"}]
    )
    monkeypatch.setattr(pms_guests, "db", SimpleNamespace(guests=guests))
    request = Request({"type": "http", "headers": []})

    result = await pms_guests.create_guest(
        GuestCreate(name="Salih Bey", id_number="12345678901"),
        request,
        SimpleNamespace(tenant_id="tenant-1", id="user-1"),
        None,
    )

    assert result["id"] == "existing"
    assert guests.inserted == []


@pytest.mark.asyncio
async def test_quick_booking_reuses_existing_guest_identity(monkeypatch):
    guests = _GuestCollection(
        [{"id": "existing", "tenant_id": "tenant-1", "name": "Salih Bey", "id_number": "12345678901"}]
    )
    rooms = SimpleNamespace(find_one=AsyncMock(return_value={"id": "room-1", "room_number": "103"}))
    create_service = SimpleNamespace(create=AsyncMock(return_value={"id": "booking-1"}))
    monkeypatch.setattr(pms_bookings, "db", SimpleNamespace(guests=guests, rooms=rooms))
    monkeypatch.setattr(pms_bookings, "create_reservation_service", create_service)

    result = await pms_bookings.create_quick_booking(
        QuickBookingCreate(
            guest_name="Salih Bey",
            guest_id_number="12345678901",
            room_id="room-1",
            check_in="2026-08-29T14:00:00+00:00",
            check_out="2026-08-30T11:00:00+00:00",
            total_amount=6000,
        ),
        Request({"type": "http", "headers": [(b"idempotency-key", b"identity-test")]}),
        SimpleNamespace(tenant_id="tenant-1"),
        None,
    )

    booking_data = create_service.create.await_args.args[0]
    assert booking_data.guest_id == "existing"
    assert guests.inserted == []
    assert result["guest_name"] == "Salih Bey"
