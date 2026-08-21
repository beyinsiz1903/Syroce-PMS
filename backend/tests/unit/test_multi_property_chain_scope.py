from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.enterprise_router import _chain_scope, _safe_decimal


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
        return self.own if query.get("id") == self.own.get("id") else None

    def find(self, query, _projection):
        assert query == {"chain_id": self.own["chain_id"]}
        return _Cursor(self.members)


@pytest.mark.asyncio
async def test_chain_scope_uses_explicit_chain_id(monkeypatch):
    own = {"id": "hotel-a", "property_name": "A", "chain_id": "chain-1"}
    members = [own, {"id": "hotel-b", "property_name": "B", "chain_id": "chain-1"}]
    database = SimpleNamespace(tenants=_Tenants(own, members))
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: database)

    resolved_own, resolved_members = await _chain_scope(SimpleNamespace(role="manager", tenant_id="hotel-a"))

    assert resolved_own == own
    assert [member["id"] for member in resolved_members] == ["hotel-a", "hotel-b"]


@pytest.mark.asyncio
async def test_unchained_manager_sees_only_own_hotel(monkeypatch):
    own = {"id": "hotel-a", "property_name": "A", "chain_id": None}
    database = SimpleNamespace(tenants=_Tenants(own, []))
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: database)

    _, members = await _chain_scope(SimpleNamespace(role="manager", tenant_id="hotel-a"))

    assert members == [own]


@pytest.mark.asyncio
async def test_chain_scope_rejects_non_management_role():
    with pytest.raises(HTTPException) as exc:
        await _chain_scope(SimpleNamespace(role="housekeeping", tenant_id="hotel-a"))
    assert exc.value.status_code == 403


def test_safe_decimal_does_not_propagate_invalid_stored_values():
    assert _safe_decimal("12.50") == Decimal("12.50")
    assert _safe_decimal("not-a-number") == Decimal("0")
