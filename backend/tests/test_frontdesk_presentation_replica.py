"""Normal guest/booking search remains usable for presentation names; LOCAL DB."""
# ruff: noqa: F811
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from core.security import get_current_user
from modules.pms_core.frontdesk_presentation import REGISTRY, TENANT
from routers import pms_bookings, pms_guests
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["guests", "bookings"])
async def test_alias_search_keeps_original_source_and_tenant_filters(db, monkeypatch, kind):
    guest = next(row for row in REGISTRY["guests"] if row["original"] == "Ada AcceptanceTest")
    source = {"id": guest["id"], "name": guest["original"], "first_name": "Ada", "last_name": "AcceptanceTest", "tenant_id": TENANT, "email": "synthetic@example.invalid"}
    await db.guests.insert_one(deepcopy(source))
    await db.guests.insert_one({"id": "foreign", "name": guest["original"], "tenant_id": "other"})
    await db.bookings.insert_many([
        {"id": "booking", "guest_id": guest["id"], "guest_name": guest["original"], "tenant_id": TENANT, "status": "confirmed", "created_at": "2026-10-31", "currency": "USD", "total_amount": 100},
        {"id": "foreign-booking", "guest_id": "foreign", "guest_name": guest["original"], "tenant_id": "other", "status": "confirmed"},
    ])
    monkeypatch.setattr(pms_guests, "db", db)
    monkeypatch.setattr(pms_guests, "_fenc", None)
    monkeypatch.setattr(pms_bookings, "db", db)
    user = SimpleNamespace(id="qa-operator", tenant_id=TENANT, role="super_admin", name="Synthetic QA", email="qa@example.invalid", is_super_admin=True, granted_permissions=None)
    app = FastAPI()
    app.include_router(pms_guests.router)
    app.include_router(pms_bookings.router)
    app.dependency_overrides[get_current_user] = lambda: user
    path = "/api/pms/guests/search?q=Ada%20Erdem" if kind == "guests" else "/api/pms/bookings?search=Ada%20Erdem"
    def records(result):
        body = result.json()
        return body if kind == "guests" else body["bookings"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-presentation-qa") as client:
        result = await client.get(path)
        assert result.status_code == 200, result.text
        rows = records(result)
        assert len(rows) == 1 and rows[0]["id"] == (guest["id"] if kind == "guests" else "booking")
        # The API remains canonical; the reviewed UI adapter alone changes display.
        assert rows[0]["name" if kind == "guests" else "guest_name"] == guest["original"]
        user.tenant_id = "other"
        other = await client.get(path)
        assert other.status_code == 200 and records(other) == []
        user.tenant_id = TENANT
        await db.guests.update_one({"id": guest["id"], "tenant_id": TENANT}, {"$set": {"name": "İsim bağımsız olarak değiştirildi"}})
        renamed = await client.get(path)
        assert renamed.status_code == 200 and records(renamed) == []
        await db.guests.update_one({"id": guest["id"]}, {"$set": {"name": guest["original"], "archived": True}})
        archived = await client.get(path)
        assert archived.status_code == 200 and records(archived) == []
    saved = await db.bookings.find_one({"id": "booking"})
    assert saved["total_amount"] == 100 and saved["currency"] == "USD" and saved["guest_name"] == guest["original"]
    assert await db.payments.count_documents({}) == 0
    assert await db.folio_charges.count_documents({}) == 0
