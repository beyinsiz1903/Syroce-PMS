from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import pos_core


class _Tables:
    def __init__(self, matched=1, doc=None):
        self.matched = matched
        self.doc = doc if doc is not None else ({"id": "table-1"} if matched else None)
        self.calls = []

    async def find_one(self, query, _projection=None):
        if not self.matched:
            return None
        return {
            "id": query["id"],
            "tenant_id": query["tenant_id"],
            "outlet_id": "outlet-1",
            "table_number": "1",
            **(self.doc or {}),
        }

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=self.matched)


class _Transactions:
    def __init__(self, open_check=None):
        self.open_check = open_check
        self.query = None

    async def find_one(self, query, _projection=None):
        self.query = query
        return self.open_check


@pytest.mark.asyncio
async def test_table_status_update_is_tenant_scoped(monkeypatch):
    tables = _Tables()
    monkeypatch.setattr(pos_core.db, "table_layouts", tables, raising=False)
    monkeypatch.setattr(pos_core.db, "pos_transactions", _Transactions(), raising=False)

    result = await pos_core.update_pos_table_status(
        "table-1",
        "reserved",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )

    assert result == {"success": True, "table_id": "table-1", "status": "reserved"}
    assert tables.calls[0][0] == {"id": "table-1", "tenant_id": "tenant-a"}
    assert tables.calls[0][1]["$set"]["status"] == "reserved"


@pytest.mark.asyncio
async def test_table_status_rejects_unknown_state(monkeypatch):
    monkeypatch.setattr(pos_core.db, "table_layouts", _Tables(), raising=False)

    with pytest.raises(HTTPException) as exc:
        await pos_core.update_pos_table_status(
            "table-1",
            "deleted",
            current_user=SimpleNamespace(tenant_id="tenant-a"),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_table_status_returns_404_for_other_tenant(monkeypatch):
    monkeypatch.setattr(pos_core.db, "table_layouts", _Tables(matched=0), raising=False)

    with pytest.raises(HTTPException) as exc:
        await pos_core.update_pos_table_status(
            "table-1",
            "available",
            current_user=SimpleNamespace(tenant_id="tenant-b"),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_table_with_open_check_cannot_be_marked_available(monkeypatch):
    tables = _Tables()
    transactions = _Transactions({"id": "check-1"})
    monkeypatch.setattr(pos_core.db, "table_layouts", tables, raising=False)
    monkeypatch.setattr(pos_core.db, "pos_transactions", transactions, raising=False)

    with pytest.raises(HTTPException) as exc:
        await pos_core.update_pos_table_status(
            "table-1",
            "available",
            current_user=SimpleNamespace(tenant_id="tenant-a"),
        )

    assert exc.value.status_code == 409
    assert "Açık adisyon" in exc.value.detail
    assert transactions.query["tenant_id"] == "tenant-a"
