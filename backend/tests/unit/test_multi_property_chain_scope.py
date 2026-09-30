from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.enterprise_router import _chain_property_metrics, _chain_scope, _safe_decimal
from modules.pms_core.chain_access import resolve_chain_properties


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, _limit):
        return self.docs


class _Tenants:
    def __init__(self, own, members):
        self.own = own
        self.members = members

    async def find_one(self, query, _projection):
        candidates = query.get("$or", [{"id": query.get("id")}])
        return self.own if any(value in {self.own.get("id"), self.own.get("tenant_id")} for item in candidates for value in item.values()) else None

    def find(self, query, _projection):
        assert query == {"chain_id": self.own["chain_id"], "subscription_status": {"$ne": "archived"}}
        return _Cursor(self.members)


@pytest.mark.asyncio
async def test_chain_scope_uses_explicit_chain_id(monkeypatch):
    own = {
        "id": "hotel-a",
        "property_name": "A",
        "chain_id": "chain-1",
        "is_chain_headquarters": True,
        "contact_email": "chain@example.com",
    }
    members = [own, {"id": "hotel-b", "property_name": "B", "chain_id": "chain-1"}]
    database = SimpleNamespace(tenants=_Tenants(own, members))
    monkeypatch.setattr("modules.pms_core.chain_access.get_system_db", lambda: database)

    resolved_own, resolved_members = await _chain_scope(
        SimpleNamespace(role="manager", tenant_id="hotel-a", email="chain@example.com")
    )

    assert resolved_own == own
    assert [member["id"] for member in resolved_members] == ["hotel-a", "hotel-b"]


@pytest.mark.asyncio
async def test_unchained_manager_sees_only_own_hotel(monkeypatch):
    own = {"id": "hotel-a", "property_name": "A", "chain_id": None}
    database = SimpleNamespace(tenants=_Tenants(own, []))
    monkeypatch.setattr("modules.pms_core.chain_access.get_system_db", lambda: database)

    _, members = await _chain_scope(SimpleNamespace(role="manager", tenant_id="hotel-a"))

    assert members == [own]


@pytest.mark.asyncio
async def test_chain_member_cannot_read_sibling_properties(monkeypatch):
    own = {"id": "hotel-b", "property_name": "B", "chain_id": "chain-1", "is_chain_headquarters": False}
    members = [
        {"id": "hotel-a", "property_name": "A", "chain_id": "chain-1", "is_chain_headquarters": True},
        own,
    ]
    database = SimpleNamespace(tenants=_Tenants(own, members))
    monkeypatch.setattr("modules.pms_core.chain_access.get_system_db", lambda: database)

    with pytest.raises(HTTPException) as exc:
        await resolve_chain_properties(SimpleNamespace(role="manager", tenant_id="hotel-b"), require_headquarters=True)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_headquarters_property_admin_is_not_implicitly_chain_admin(monkeypatch):
    own = {
        "id": "hotel-a",
        "property_name": "A",
        "chain_id": "chain-1",
        "is_chain_headquarters": True,
        "contact_email": "chain@example.com",
    }
    database = SimpleNamespace(tenants=_Tenants(own, [own]))
    monkeypatch.setattr("modules.pms_core.chain_access.get_system_db", lambda: database)

    with pytest.raises(HTTPException) as exc:
        await resolve_chain_properties(
            SimpleNamespace(role="admin", tenant_id="hotel-a", email="property-manager@example.com"),
            require_headquarters=True,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_chain_scope_rejects_non_management_role():
    with pytest.raises(HTTPException) as exc:
        await _chain_scope(SimpleNamespace(role="housekeeping", tenant_id="hotel-a"))
    assert exc.value.status_code == 403


def test_safe_decimal_does_not_propagate_invalid_stored_values():
    assert _safe_decimal("12.50") == Decimal("12.50")
    assert _safe_decimal("not-a-number") == Decimal("0")


class _MetricCollection:
    def __init__(self, docs=None, count=None, one=None):
        self.docs = docs or []
        self.count = count
        self.one = one

    async def count_documents(self, query):
        return self.count(query) if callable(self.count) else int(self.count or 0)

    def find(self, _query, _projection):
        return _Cursor(self.docs)

    async def find_one(self, _query, _projection):
        return self.one


@pytest.mark.asyncio
async def test_chain_property_metrics_preserve_currency_and_operational_sources():
    def booking_count(query):
        if "created_at" in query:
            return 3
        if "check_in" in query:
            return 2
        if "check_out" in query:
            return 1
        return 0

    def room_count(query):
        return 1 if any("status" in clause and isinstance(clause["status"], dict) for clause in query.get("$or", [])) else 4

    database = SimpleNamespace(
        rooms=_MetricCollection(count=room_count),
        guests=_MetricCollection(count=50),
        bookings=_MetricCollection(count=booking_count),
        housekeeping_tasks=_MetricCollection(count=2),
        folios=_MetricCollection(docs=[{"balance": 125, "currency": "EUR"}]),
        payments=_MetricCollection(docs=[{"amount": 500, "currency": "EUR"}]),
        folio_charges=_MetricCollection(docs=[{"total": 300, "currency": "EUR"}]),
        hotel_settings=_MetricCollection(one={"currency": "EUR"}),
        provider_connections=_MetricCollection(one=None),
        tenant_settings=_MetricCollection(one={"nilvera": {"enabled": True, "api_key_enc": "set"}}),
    )

    result = await _chain_property_metrics(
        database,
        {"id": "hotel-a", "property_name": "A", "total_rooms": 10},
        "2026-09-30T00:00:00+00:00",
        "2026-10-01T00:00:00+00:00",
    )

    assert result["occupancy_pct"] == 40.0
    assert result["arrivals_today"] == 2
    assert result["departures_today"] == 1
    assert result["pickup_7d"] == 3
    assert result["housekeeping_pending"] == 2
    assert result["out_of_order_rooms"] == 1
    assert result["outstanding_by_currency"] == {"EUR": 125.0}
    assert result["today_revenue_by_currency"] == {"EUR": 500.0}
    assert result["room_revenue_by_currency"] == {"EUR": 300.0}
    assert result["adr_by_currency"] == {"EUR": 75.0}
