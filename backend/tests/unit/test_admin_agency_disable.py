"""Admin soft-disable of an agency: nothing is deleted, re-activation restores access."""

from types import SimpleNamespace

import pytest

from routers import agency_contracts
from routers import marketplace_b2b as marketplace


def _match(row, query):
    for key, cond in query.items():
        value = row.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$lte" in cond and not value <= cond["$lte"]:
                return False
            if "$gte" in cond and not value >= cond["$gte"]:
                return False
        elif value != cond:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _n):
        return [dict(r) for r in self.rows]

    def __aiter__(self):
        self._it = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_a, **_k):
        return _Cursor([r for r in self.rows if _match(r, query)])

    async def find_one(self, query, *_a, **_k):
        return next((dict(r) for r in self.rows if _match(r, query)), None)

    async def update_one(self, query, update):
        rows = [r for r in self.rows if _match(r, query)][:1]
        for row in rows:
            row.update(update["$set"])
        return SimpleNamespace(matched_count=len(rows), modified_count=len(rows))

    async def update_many(self, query, update):
        rows = [r for r in self.rows if _match(r, query)]
        for row in rows:
            row.update(update["$set"])
        return SimpleNamespace(matched_count=len(rows), modified_count=len(rows))

    async def insert_one(self, doc):
        self.rows.append(doc)


def _sysdb():
    return SimpleNamespace(
        marketplace_agencies=_Coll([{"id": "a1", "name": "Test Travel", "status": "active"},
                                    {"id": "a2", "name": "Other", "status": "active"}]),
        marketplace_api_keys=_Coll([{"agency_id": "a1", "is_active": True}]),
        agency_contracts=_Coll([
            {"id": "c1", "agency_id": "a1", "tenant_id": "t1", "status": "pending"},
            {"id": "c2", "agency_id": "a1", "tenant_id": "t1", "status": "approved", "valid_from": "2026-01-01", "valid_to": "2027-12-31"},
            {"id": "c3", "agency_id": "a2", "tenant_id": "t1", "status": "approved", "valid_from": "2026-01-01", "valid_to": "2027-12-31"},
        ]),
        marketplace_audit_log=_Coll([]),
    )


@pytest.mark.asyncio
async def test_disable_is_soft_and_reversible(monkeypatch):
    sysdb = _sysdb()
    monkeypatch.setattr(marketplace, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(agency_contracts, "get_system_db", lambda: sysdb)

    async def audit(*_a, **_k):
        return None

    monkeypatch.setattr(marketplace, "_record_marketplace_audit", audit)

    result = await marketplace.admin_disable_agency("a1", True)
    assert result["withdrawn_proposals"] == 1
    agency = await sysdb.marketplace_agencies.find_one({"id": "a1"})
    assert agency["status"] == "disabled" and agency["name"] == "Test Travel"
    assert sysdb.marketplace_api_keys.rows[0]["is_active"] is False
    statuses = {c["id"]: c["status"] for c in sysdb.agency_contracts.rows}
    assert statuses == {"c1": "withdrawn", "c2": "approved", "c3": "approved"}
    assert await agency_contracts.list_active_agencies_for_tenant("t1", "2026-10-14") == ["a2"]

    await marketplace.admin_update_agency("a1", marketplace.MarketplaceAgencyUpdate(status="active"), True)
    agency = await sysdb.marketplace_agencies.find_one({"id": "a1"})
    assert agency["status"] == "active" and agency["disabled_at"] is None
    assert await agency_contracts.list_active_agencies_for_tenant("t1", "2026-10-14") == ["a1", "a2"]


@pytest.mark.asyncio
async def test_patch_to_disabled_uses_the_same_soft_disable(monkeypatch):
    sysdb = _sysdb()
    monkeypatch.setattr(marketplace, "get_system_db", lambda: sysdb)

    async def audit(*_a, **_k):
        return None

    monkeypatch.setattr(marketplace, "_record_marketplace_audit", audit)
    await marketplace.admin_update_agency("a1", marketplace.MarketplaceAgencyUpdate(status="disabled"), True)
    assert sysdb.marketplace_api_keys.rows[0]["is_active"] is False
    assert sysdb.agency_contracts.rows[0]["status"] == "withdrawn"
