"""Real Mongo acceptance; only the explicitly selected LOCAL test replica."""
# ruff: noqa: F811
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from domains.pms import operations_router as ops
from routers import pms_services as services
from tests.test_frontdesk_control_integrity import CONTRACT, USER, booking
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest.mark.asyncio
async def test_allotment_source_usage_release_reload_and_tenant_boundary(db, monkeypatch):
    monkeypatch.setattr(services, "db", db)
    await db.rooms.insert_many([
        {"id": "r1", "tenant_id": USER.tenant_id, "room_type": "Junior Suite"},
        {"id": "virtual", "tenant_id": USER.tenant_id, "room_type": "Junior Suite", "is_virtual": True},
        {"id": "other", "tenant_id": "elsewhere", "room_type": "Junior Suite"},
    ])
    created = await services.create_allotment_contract(CONTRACT, current_user=USER)
    cid = created["id"]
    assert created["currency"] == "TRY" and created["release_days"] == 0
    await db.bookings.insert_many([
        {**booking("b1", datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC)), "tenant_id": USER.tenant_id, "room_id": "r1", "allotment_contract_id": cid},
        {**booking("b2", "2026-11-12", "2026-11-14", currency="USD"), "tenant_id": USER.tenant_id, "room_id": "r1", "allotment_contract_id": cid},
        {**booking("virtual"), "tenant_id": USER.tenant_id, "room_id": "virtual", "allotment_contract_id": cid},
        {**booking("cross"), "tenant_id": "elsewhere", "room_id": "r1", "allotment_contract_id": cid},
    ])
    before = (await services.get_allotment_contracts(current_user=USER))["contracts"][0]
    assert before["used_rooms"] == 1 and before["bookings_count"] == 2
    assert before["total_revenue"] is None and before["total_revenue_by_currency"] == {"TRY": 200, "USD": 200}
    assert (await services.release_allotment_rooms(cid, current_user=USER))["released_rooms"] == 2
    assert (await services.release_allotment_rooms(cid, current_user=USER))["released_rooms"] == 0
    after = (await services.get_allotment_contracts(current_user=USER))["contracts"][0]
    assert after["available_rooms"] == 0 and after["released_by"] == USER.id
    with pytest.raises(HTTPException) as exc:
        await services.create_allotment_contract({**CONTRACT, "room_type": "King"}, current_user=USER)
    assert exc.value.status_code == 400
    assert await db.allotment_contracts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_unassigned_contract_booking_is_not_silently_released(db, monkeypatch):
    monkeypatch.setattr(services, "db", db)
    await db.rooms.insert_one({"id": "r1", "tenant_id": USER.tenant_id, "room_type": "Junior Suite"})
    created = await services.create_allotment_contract(CONTRACT, current_user=USER)
    await db.bookings.insert_one({**booking("unassigned"), "tenant_id": USER.tenant_id, "room_id": None,
                                 "room_type": "Junior Suite", "allotment_contract_id": created["id"]})
    assert (await services.get_allotment_contracts(current_user=USER))["contracts"][0]["used_rooms"] == 1
    await db.bookings.update_one({"id": "unassigned"}, {"$unset": {"room_type": ""}})
    with pytest.raises(HTTPException) as exc:
        await services.release_allotment_rooms(created["id"], current_user=USER)
    assert exc.value.status_code == 409
    assert not (await db.allotment_contracts.find_one({"id": created["id"]})).get("released_rooms")


@pytest.mark.asyncio
async def test_kvkk_source_and_audit_survive_reload_export_and_retry(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    created = await ops.create_kvkk_request({"guest_name": "Synthetic QA", "type": "access"}, current_user=USER)
    await ops.update_kvkk_request(created["id"], {"status": "completed"}, current_user=USER)
    assert (await ops.update_kvkk_request(created["id"], {"status": "completed"}, current_user=USER))["already_applied"]
    source = (await ops.get_kvkk_requests(current_user=USER))["requests"][0]
    assert source["status"] == "completed" and len(source["audit_events"]) == 2
    audit = (await ops.get_kvkk_audit_log(current_user=USER))["logs"]
    assert len(audit) == 2 and all(row["user"] == USER.email and row["target"] == created["id"] for row in audit)
    exported = await ops.export_kvkk_data(guest_name="Synthetic QA", current_user=USER)
    assert exported["counts"]["audit_log"] == 2
    await db.kvkk_audit_log.insert_one({"_id": "other-event", "tenant_id": "other", "timestamp": datetime.now(UTC).isoformat()})
    assert len((await ops.get_kvkk_audit_log(current_user=USER))["logs"]) == 2
    with pytest.raises(HTTPException) as exc:
        await ops.update_kvkk_request("foreign-id", {"status": "completed"}, current_user=USER)
    assert exc.value.status_code == 404
