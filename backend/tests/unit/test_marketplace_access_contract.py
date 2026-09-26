import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import marketplace_b2b
from routers.marketplace_b2b import (
    MarketplacePortalSettingsUpdate,
    MarketplaceReservationCreate,
    _last_occupied_date,
    _marketplace_financials,
    _require_hotel_admin,
    _reservation_agency_snapshot,
    _reservation_room_snapshot,
    _syroce_b2b_fee,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)


class _LoginCollection:
    def __init__(self, row=None):
        self.row = row
        self.inserted = []
        self.deleted = []

    async def count_documents(self, *_args, **_kwargs):
        return 0

    async def find_one(self, *_args, **_kwargs):
        return self.row

    async def insert_one(self, document):
        self.inserted.append(document)

    async def delete_many(self, query):
        self.deleted.append(query)


class _SettingsCollection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.updated = []
        self.inserted = []

    @staticmethod
    def _project(row, projection):
        if not row or not projection:
            return row
        included = {key for key, value in projection.items() if value and key != "_id"}
        if not included:
            excluded = {key for key, value in projection.items() if not value}
            return {key: value for key, value in row.items() if key not in excluded}
        return {key: value for key, value in row.items() if key in included}

    async def find_one(self, query, projection=None, *_args, **_kwargs):
        row = next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)
        return self._project(row, projection)

    def find(self, query, projection=None, *_args, **_kwargs):
        rows = [row for row in self.rows if row.get("agency_id") == query.get("agency_id")]
        return _Cursor([self._project(row, projection) for row in rows])

    async def update_one(self, query, update):
        self.updated.append((query, update))
        match = next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)
        if match:
            match.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1 if match else 0)

    async def insert_one(self, document):
        self.inserted.append(document)


def test_marketplace_listing_management_rejects_guest_and_staff_roles():
    for role in ("guest", "staff", "front_desk", "agency_admin"):
        with pytest.raises(HTTPException) as error:
            _require_hotel_admin(SimpleNamespace(role=role, tenant_id="hotel-1"))
        assert error.value.status_code == 403


def test_marketplace_listing_management_allows_hotel_management():
    assert _require_hotel_admin(SimpleNamespace(role="admin", tenant_id="hotel-1")) == "hotel-1"
    assert _require_hotel_admin(SimpleNamespace(role="supervisor", tenant_id="hotel-1")) == "hotel-1"


def test_marketplace_stay_authorization_uses_final_occupied_night():
    assert _last_occupied_date("2026-09-25", "2026-09-26") == "2026-09-25"
    assert _last_occupied_date("2026-09-25", "2026-09-29") == "2026-09-28"


def test_marketplace_service_fee_is_defined_for_both_sales_channels():
    assert _syroce_b2b_fee(5000, "extranet_ui") == (2.0, 100.0)
    assert _syroce_b2b_fee(5000, "syroce_agency_app") == (1.0, 50.0)
    assert _syroce_b2b_fee(5000, "extranet_ui", 1.5) == (1.5, 75.0)


def test_marketplace_financials_reconcile_after_price_change():
    assert _marketplace_financials(7500, 15, 2) == {
        "commission_amount": 1125.0,
        "syroce_b2b_fee_amount": 150.0,
        "net_to_hotel": 6225.0,
    }


def test_marketplace_room_snapshot_keeps_ledger_and_pms_fields_consistent():
    assert _reservation_room_snapshot({"room_type": "Stone Deluxe", "room_number": "101"}) == {
        "room_type": "Stone Deluxe",
        "room_number": "101",
    }


def test_marketplace_agency_snapshot_identifies_the_exact_seller():
    snapshot = _reservation_agency_snapshot({"agency_id": "agency-1", "agency_name": "Cengizhan Travel"})
    assert snapshot["agency_name"] == "Cengizhan Travel"
    assert snapshot["source_channel"] == "marketplace"
    assert snapshot["origin"] == "syroce_marketplace"


def test_marketplace_booking_payload_rejects_invalid_capacity_and_identity():
    with pytest.raises(ValidationError):
        MarketplaceReservationCreate(
            tenant_id="hotel-1",
            room_type="Standard",
            check_in="2026-09-25",
            check_out="2026-09-26",
            guest_name="X",
            adults=0,
            children=99,
        )


@pytest.mark.asyncio
async def test_marketplace_extranet_login_uses_core_password_verifier(monkeypatch):
    attempts = _LoginCollection()
    users = _LoginCollection(
        {
            "id": "user-1",
            "name": "Test Agent",
            "email": "agent@example.com",
            "hashed_password": "stored-hash",
            "role": "marketplace_agent",
            "agency_id": "agency-1",
            "is_active": True,
        }
    )
    agencies = _LoginCollection({"id": "agency-1", "name": "Test Travel", "status": "active"})
    fake_system_db = SimpleNamespace(
        marketplace_login_attempts=attempts,
        users=users,
        marketplace_agencies=agencies,
    )

    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: fake_system_db)
    monkeypatch.setattr(marketplace_b2b, "verify_password", lambda password, hashed: (password, hashed) == ("secret", "stored-hash"))
    security_module = importlib.import_module("core.security")
    monkeypatch.setattr(security_module, "create_token", lambda user_id, tenant_id: f"token:{user_id}:{tenant_id}")

    result = await marketplace_b2b.marketplace_extranet_login(
        marketplace_b2b.MarketplaceLoginRequest(email=" AGENT@EXAMPLE.COM ", password="secret"),
        SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
    )

    assert result["token"] == "token:user-1:None"
    assert result["agency"] == {"id": "agency-1", "name": "Test Travel"}
    assert attempts.deleted


@pytest.mark.asyncio
async def test_marketplace_extranet_profile_preserves_signed_in_user_identity(monkeypatch):
    async def fake_hotels(_agency):
        return {"hotels": [{"tenant_id": "hotel-1", "name": "Hotel One"}]}

    monkeypatch.setattr(
        marketplace_b2b,
        "marketplace_my_hotels",
        fake_hotels,
    )
    agency = {
        "agency_id": "agency-1",
        "agency_name": "Cengizhan Travel",
        "contact_email": "agency@example.com",
        "user": {
            "id": "user-1",
            "name": "Cengizhan Travel Marketplace Admin",
            "email": "marketplace+cengizhan-travel@syroce.com",
            "role": "marketplace_agent",
        },
    }

    result = await marketplace_b2b.marketplace_extranet_profile(agency)

    assert result["user"]["email"] == "marketplace+cengizhan-travel@syroce.com"
    assert result["agency"]["name"] == "Cengizhan Travel"
    assert result["hotels"][0]["tenant_id"] == "hotel-1"


@pytest.mark.asyncio
async def test_marketplace_settings_are_scoped_and_never_expose_secrets(monkeypatch):
    agencies = _SettingsCollection([{"id": "agency-1", "name": "Test Travel", "status": "active", "contact_email": "a@example.com"}])
    users = _SettingsCollection([
        {"id": "u1", "agency_id": "agency-1", "email": "agent@example.com", "role": "marketplace_agent", "hashed_password": "secret"},
        {"id": "u2", "agency_id": "agency-2", "email": "other@example.com", "role": "marketplace_agent"},
    ])
    keys = _SettingsCollection([{"id": "k1", "agency_id": "agency-1", "key_prefix": "syroce_mkt_abc...", "key_hash": "secret-hash", "is_active": True}])
    fake_db = SimpleNamespace(marketplace_agencies=agencies, users=users, marketplace_api_keys=keys)
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: fake_db)

    result = await marketplace_b2b.marketplace_extranet_settings({"agency_id": "agency-1"})

    assert [user["id"] for user in result["users"]] == ["u1"]
    assert "hashed_password" not in result["users"][0]
    assert "key_hash" not in result["api_keys"][0]


@pytest.mark.asyncio
async def test_marketplace_settings_update_targets_only_signed_in_agency(monkeypatch):
    agencies = _SettingsCollection([{"id": "agency-1", "name": "Old", "status": "active"}])
    audits = _SettingsCollection()
    fake_db = SimpleNamespace(marketplace_agencies=agencies, marketplace_audit_logs=audits)
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: fake_db)
    payload = MarketplacePortalSettingsUpdate(
        name="New Travel",
        contact_email="INFO@EXAMPLE.COM",
        allowed_widget_origins=["https://agency.example.com/"],
    )

    result = await marketplace_b2b.update_marketplace_extranet_settings(
        payload, {"agency_id": "agency-1", "user": {"id": "u1"}}
    )

    assert result["ok"] is True
    query, update = agencies.updated[0]
    assert query == {"id": "agency-1", "status": "active"}
    assert update["$set"]["contact_email"] == "info@example.com"
    assert update["$set"]["allowed_widget_origins"] == ["https://agency.example.com"]
    assert audits.inserted[0]["actor_user_id"] == "u1"


@pytest.mark.asyncio
async def test_marketplace_price_prefers_shared_agency_calendar(monkeypatch):
    fake_db = SimpleNamespace(
        agency_rate_calendar=_Collection([
            {"date": "2026-09-25", "rate": 900},
            {"date": "2026-09-26", "rate": 1100},
        ]),
        hr_rate_calendar=_Collection([{"date": "2026-09-25", "rate": 1500}]),
        rate_calendar=_Collection([]),
    )
    monkeypatch.setattr(marketplace_b2b, "db", fake_db)

    result = await marketplace_b2b._marketplace_stay_price(
        tenant_id="hotel-1",
        agency_id="agency-1",
        room_type="Standard",
        check_in="2026-09-25",
        check_out="2026-09-27",
        fallback_rate=2000,
    )

    assert result["sellable"] is True
    assert result["total_price"] == 2000
    assert result["nightly_rates"] == [
        {"date": "2026-09-25", "rate": 900.0},
        {"date": "2026-09-26", "rate": 1100.0},
    ]


@pytest.mark.asyncio
async def test_marketplace_price_honors_agency_stop_sell(monkeypatch):
    fake_db = SimpleNamespace(
        agency_rate_calendar=_Collection([{"date": "2026-09-25", "rate": 900, "stop_sell": True}]),
        hr_rate_calendar=_Collection([]),
        rate_calendar=_Collection([]),
    )
    monkeypatch.setattr(marketplace_b2b, "db", fake_db)

    result = await marketplace_b2b._marketplace_stay_price(
        tenant_id="hotel-1",
        agency_id="agency-1",
        room_type="Standard",
        check_in="2026-09-25",
        check_out="2026-09-26",
        fallback_rate=2000,
    )

    assert result == {"sellable": False, "nightly_rates": [], "total_price": 0.0}


@pytest.mark.asyncio
async def test_marketplace_price_exposes_lowest_shared_allotment(monkeypatch):
    fake_db = SimpleNamespace(
        agency_rate_calendar=_Collection([
            {"date": "2026-10-15", "rate": 5432, "availability": 4},
            {"date": "2026-10-16", "rate": 5432, "availability": 3},
        ]),
        hr_rate_calendar=_Collection([]),
        rate_calendar=_Collection([]),
    )
    monkeypatch.setattr(marketplace_b2b, "db", fake_db)

    result = await marketplace_b2b._marketplace_stay_price(
        tenant_id="hotel-1",
        agency_id="agency-1",
        room_type="Cave Suite",
        check_in="2026-10-15",
        check_out="2026-10-17",
        fallback_rate=5500,
    )

    assert result["shared_availability"] == 3
    assert result["total_price"] == 10864
