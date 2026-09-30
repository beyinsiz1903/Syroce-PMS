from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import reservations


class _Reservations:
    def __init__(self, status="confirmed"):
        self.doc = {"id": "reservation-1", "tenant_id": "tenant-1", "status": status}

    async def find_one(self, query, _projection=None):
        if query.get("id") == self.doc["id"] and query.get("tenant_id") == self.doc["tenant_id"]:
            return dict(self.doc)
        return None

    async def find_one_and_update(self, query, update, return_document=None):
        if query.get("status") != self.doc["status"]:
            return None
        self.doc.update(update["$set"])
        return dict(self.doc)


def _user():
    return SimpleNamespace(tenant_id="tenant-1", id="user-1")


@pytest.mark.asyncio
async def test_table_reservation_follows_service_lifecycle(monkeypatch):
    collection = _Reservations("confirmed")
    monkeypatch.setattr(reservations, "db", SimpleNamespace(pos_table_reservations=collection))

    result = await reservations.update_reservation_status("reservation-1", "seated", current_user=_user())

    assert result["status"] == "seated"
    assert result["updated_by"] == "user-1"


@pytest.mark.asyncio
async def test_table_reservation_terminal_state_cannot_reopen(monkeypatch):
    collection = _Reservations("completed")
    monkeypatch.setattr(reservations, "db", SimpleNamespace(pos_table_reservations=collection))

    with pytest.raises(HTTPException) as exc:
        await reservations.update_reservation_status("reservation-1", "confirmed", current_user=_user())

    assert exc.value.status_code == 409
