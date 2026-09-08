from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import pos_core


class _Tables:
    def __init__(self, matched=1):
        self.matched = matched
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=self.matched)


@pytest.mark.asyncio
async def test_table_status_update_is_tenant_scoped(monkeypatch):
    tables = _Tables()
    monkeypatch.setattr(pos_core.db, "table_layouts", tables, raising=False)

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
