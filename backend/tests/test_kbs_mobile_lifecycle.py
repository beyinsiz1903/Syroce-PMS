"""Real isolated Mongo; ALL authority calls mocked, no real guest data."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from core import kbs_auto_enqueue as enqueue
from core import kbs_cloud as cloud
from core.kbs_jandarma import JandarmaError
from core.kbs_operational_view import delivery_reason, operational_notifications, visible_stay
from core.kbs_readiness import booking_readiness
from tests.test_kbs_cloud_config import CREDS, config_db  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def ready(config_db, monkeypatch):  # noqa: F811 - imported pytest fixture
    db, tid = config_db
    monkeypatch.setattr(enqueue, "db", db)
    monkeypatch.setenv("KBS_AUTO_ENQUEUE", "1")
    await db.kbs_reports.create_index("_open_lock", unique=True, partialFilterExpression={"_open_lock": {"$exists": True}}, name="uniq_kbs_open_lock")
    await cloud.save_config(db, tid, CREDS, "admin")
    call = AsyncMock(return_value={"code": "Basarili", "method": "synthetic-reply"})
    monkeypatch.setattr(cloud, "call_jandarma", call)
    await cloud.verify_config(db, tid)
    await cloud.save_config(db, tid, {"enabled": True, "live_confirmed": True}, "admin")
    call.reset_mock()
    yield db, tid, call
    for name in ("bookings", "booking_guests", "guests", "rooms"):
        await db[name].delete_many({"tenant_id": tid})


async def seed(db, tid, *, status="checked_in", secondary=False, **changes):
    bid, gid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(UTC)
    booking = {
        "id": bid,
        "tenant_id": tid,
        "guest_id": gid,
        "guest_name": "Synthetic Primary",
        "room_number": "101",
        "status": status,
        "adults": 2 if secondary else 1,
        "children": 0,
        "check_in": (now - timedelta(days=1)).isoformat(),
        "checked_in_at": (now - timedelta(hours=1)).isoformat(),
        "check_out": (now + timedelta(days=1)).isoformat(),
        **({"checked_out_at": now.isoformat()} if status == "checked_out" else {}),
        **changes,
    }
    await db.bookings.insert_one(booking)
    await db.guests.insert_one({"tenant_id": tid, "id": gid, "name": "Synthetic Primary", "nationality": "TR", "id_number": "12345678901"})
    if secondary:
        other = str(uuid.uuid4())
        await db.guests.insert_one({"tenant_id": tid, "id": other, "name": "Synthetic Secondary", "nationality": "TR", "id_number": "98765432109"})
        await db.booking_guests.insert_one({"tenant_id": tid, "booking_id": bid, "guest_id": other})
    return bid, gid


async def test_checkout_waits_for_own_checkin_and_wakes_without_blocking_other_people(ready):
    db, tid, call = ready
    bid, gid = await seed(db, tid, status="checked_out", secondary=True)
    jobs = await enqueue.auto_enqueue_kbs(tid, bid, "checkout")
    assert len(jobs) == 2 and all(j["awaiting_checkin"] for j in jobs)
    result = await cloud.dispatch_cloud_jobs(db)
    assert result["sent"] == 0 and result["blocked"] == 2
    assert all(c.args == (CREDS,) for c in call.await_args_list)
    unrelated, _ = await seed(db, tid)
    await enqueue.auto_enqueue_kbs(tid, unrelated, "checkin")
    await enqueue.auto_enqueue_kbs(tid, bid, "checkin", target_guest_id=gid)
    result = await cloud.dispatch_cloud_jobs(db)
    assert result["sent"] == 3
    other_co = await db.kbs_reports.find_one({"tenant_id": tid, "booking_id": bid, "action": "checkout", "guest_id": {"$ne": gid}})
    assert other_co["status"] == "pending" and other_co["awaiting_checkin"]
    await enqueue.auto_enqueue_kbs(tid, bid, "checkin", target_guest_id=other_co["guest_id"])
    assert (await cloud.dispatch_cloud_jobs(db))["sent"] == 2
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job", "status": "done"}) == 5
    assert (await cloud.dispatch_cloud_jobs(db))["sent"] == 0


@pytest.mark.parametrize("failure", ["missing", "already_registered", "uncertain"])
async def test_bad_first_person_does_not_block_next_and_uncertainty_never_retries(ready, monkeypatch, failure):
    db, tid, _ = ready
    bad, bad_gid = await seed(db, tid)
    await enqueue.auto_enqueue_kbs(tid, bad)
    good, _ = await seed(db, tid)
    await enqueue.auto_enqueue_kbs(tid, good)
    if failure == "missing":
        await db.guests.update_one({"tenant_id": tid, "id": bad_gid}, {"$set": {"id_number": ""}})
    else:

        async def authority(_credentials, payload=None, action="checkin"):
            if payload and not getattr(authority, "failed", False):
                authority.failed = True
                raise JandarmaError("already_registered" if failure == "already_registered" else "delivery_unknown_check_authority", uncertain=failure == "uncertain")
            return {"code": "Basarili", "method": action}

        monkeypatch.setattr(cloud, "call_jandarma", AsyncMock(side_effect=authority))
    result = await cloud.dispatch_cloud_jobs(db)
    assert result["sent"] == 1 and result["blocked"] == 1
    bad_job = await db.kbs_reports.find_one({"tenant_id": tid, "_kind": "queue_job", "booking_id": bad})
    assert bad_job["status"] == "dead"
    if failure != "missing":
        await enqueue.auto_enqueue_kbs(tid, bad)
        assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job", "booking_id": bad}) == 1
    row = next(r for r in (await operational_notifications(db, tid))["items"] if r["booking_id"] == bad)
    assert row["status_reason"] == {"missing": "missing_data", "already_registered": "already_registered", "uncertain": "delivery_uncertain"}[failure]
    assert row["can_retry"] is False
    assert (await cloud.dispatch_cloud_jobs(db))["sent"] == 0


async def test_secondary_identity_is_never_replaced_with_primary(ready):
    db, tid, call = ready
    bid, _ = await seed(db, tid, secondary=True)
    await enqueue.auto_enqueue_kbs(tid, bid)
    assert (await cloud.dispatch_cloud_jobs(db))["sent"] == 2
    payloads = [c.args[1] for c in call.await_args_list if len(c.args) > 1]
    assert {p["id_number"] for p in payloads} == {"12345678901", "98765432109"}
    assert {p["guest_name"] for p in payloads} == {"Synthetic Primary", "Synthetic Secondary"}


async def test_expiry_hides_departed_people_in_both_views_but_keeps_queue_and_receipts(ready):
    db, tid, _ = ready
    now = datetime.now(UTC)
    old, _ = await seed(db, tid, status="checked_out", checked_out_at=(now - timedelta(hours=24)).isoformat())
    await enqueue.auto_enqueue_kbs(tid, old)
    await cloud.dispatch_cloud_jobs(db)
    await enqueue.auto_enqueue_kbs(tid, old, "checkout")
    recent, _ = await seed(db, tid, status="checked_out", checked_out_at=(now - timedelta(hours=23)).isoformat())
    await enqueue.auto_enqueue_kbs(tid, recent)
    overdue, _ = await seed(db, tid, check_out=(now - timedelta(days=30)).isoformat())
    before = await db.kbs_reports.count_documents({"tenant_id": tid})
    view = await operational_notifications(db, tid, now=now)
    assert old not in {r["booking_id"] for r in view["items"]}
    assert {recent, overdue} <= {r["booking_id"] for r in view["items"]}
    assert view["hidden_unresolved_count"] == 1
    assert await db.kbs_reports.count_documents({"tenant_id": tid}) == before
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "booking_id": old, "status": "done", "_kind": "queue_job"}) == 1


async def test_early_departed_secondary_expires_while_primary_remains(ready):
    db, tid, _ = ready
    bid, gid = await seed(db, tid, secondary=True)
    await db.booking_guests.update_one({"tenant_id": tid, "booking_id": bid}, {"$set": {"checkout_date": (datetime.now(UTC) - timedelta(days=2)).isoformat()}})
    view = await operational_notifications(db, tid)
    assert {r["guest_id"] for r in view["items"] if r.get("guest_id")} == {gid}


async def test_missing_identity_and_unregistered_occupants_visible_without_queue_jobs(ready):
    db, tid, _ = ready
    bid, gid = await seed(db, tid, adults=2)
    await db.guests.update_one({"tenant_id": tid, "id": gid}, {"$set": {"id_number": ""}})
    assert await enqueue.auto_enqueue_kbs(tid, bid) is None
    readiness = await booking_readiness(db, tid, bid)
    assert not readiness["ready"] and readiness["unregistered_occupants"] == 1
    view = await operational_notifications(db, tid)
    assert len(view["items"]) == 2 and all(r["status_reason"] == "missing_data" for r in view["items"])
    assert "12345678901" not in str(view)


async def test_concurrent_auto_enqueue_is_one_per_person_action(ready):
    db, tid, _ = ready
    bid, _ = await seed(db, tid, secondary=True)
    await asyncio.gather(*(enqueue.auto_enqueue_kbs(tid, bid) for _ in range(8)))
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job"}) == 2


async def test_nightly_sweep_never_reports_confirmed_non_arrival(ready):
    from core.kbs_nightly_sweep import sweep_tenant_kbs

    db, tid, _ = ready
    bid, _ = await seed(db, tid, status="confirmed")
    await db.bookings.update_one({"tenant_id": tid, "id": bid}, {"$unset": {"checked_in_at": ""}})
    await sweep_tenant_kbs(db, tid, datetime.now(UTC).date().isoformat())
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job"}) == 0


async def test_mobile_web_views_are_same_tenant_scoped_and_never_expose_identity(ready, monkeypatch):
    from core.security import get_current_user
    from routers import kbs

    db, tid, _ = ready
    await seed(db, tid)
    monkeypatch.setattr(kbs, "db", db)
    app = FastAPI()
    app.include_router(kbs.router)
    user = SimpleNamespace(id="staff", tenant_id=tid, name="Staff", role="front_desk", permissions=[], guest_data_visibility={"name": "hidden", "identity": "hidden"})
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline") as client:
        web = await client.get("/api/kbs/notifications?group=not_sent")
        mobile = await client.get("/api/kbs/mobile/notifications?group=not_sent")
        assert web.status_code == mobile.status_code == 200
        assert web.json() == mobile.json()
        assert web.json()["counts"] == {"sent": 0, "not_sent": 1}
        assert "12345678901" not in web.text and "Synthetic Primary" not in web.text
        user.tenant_id = tid + "-other"
        assert (await client.get("/api/kbs/notifications")).json()["items"] == []
        user.tenant_id = tid
        user.role = "housekeeping"
        assert (await client.get("/api/kbs/notifications")).status_code == 403


async def test_visibility_boundary_uses_actual_local_checkout_not_planned_date():
    now = datetime(2026, 11, 2, 20, tzinfo=UTC)
    assert visible_stay({"status": "checked_in", "check_out": "2020-01-01"}, now)
    assert visible_stay({"status": "checked_out", "checked_out_at": "2026-11-02T20:00:00+03:00", "check_out": "2020-01-01"}, now)
    assert not visible_stay({"status": "checked_out", "checked_out_at": "2026-11-01T23:00:00+03:00"}, now)
    assert not visible_stay({"status": "checked_out"}, now)
    assert delivery_reason({"last_error": "already_registered", "status": "dead"}, []) == "already_registered"


async def test_identity_update_is_tenant_person_and_visibility_scoped_and_requeues_missing_guest(ready, monkeypatch):
    from core.security import get_current_user
    from routers import kbs, pms_guests

    db, tid, _ = ready
    bid, gid = await seed(db, tid)
    await db.guests.update_one({"tenant_id": tid, "id": gid}, {"$set": {"id_number": ""}})
    monkeypatch.setattr(kbs, "db", db)
    monkeypatch.setattr(pms_guests, "db", db)
    monkeypatch.setattr(kbs, "log_audit_event", AsyncMock())
    app = FastAPI()
    app.include_router(kbs.router)
    user = SimpleNamespace(
        id="staff", tenant_id=tid, name="Staff", role="admin", permissions=[], guest_data_visibility={"name": "full", "identity": "full", "nationality": "full", "birth_date": "full"}
    )
    app.dependency_overrides[get_current_user] = lambda: user
    path = f"/api/kbs/booking/{bid}/guests/{gid}/identity"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline") as client:
        assert (await client.put(path, json={"id_number": "bad"})).status_code == 422
        assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job"}) == 0
        user.tenant_id = tid + "-other"
        assert (await client.put(path, json={"id_number": "12345678901"})).status_code == 404
        user.tenant_id = tid
        assert (await client.put(path.replace(gid, "unrelated"), json={"id_number": "12345678901"})).status_code == 404
        user.guest_data_visibility["identity"] = "hidden"
        assert (await client.put(path, json={"id_number": "12345678901"})).status_code == 403
        user.guest_data_visibility["identity"] = "full"
        result = await client.put(path, json={"id_number": "12345678901"})
        assert result.status_code == 200, result.text
        assert result.json()["ready"] and "12345678901" not in result.text
        assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job", "guest_id": gid}) == 1
        assert "12345678901" not in str(kbs.log_audit_event.call_args)


async def test_managed_checkin_rejects_missing_information_before_any_frontdesk_write(ready, monkeypatch):
    from common.context import OperationContext
    from core import atomic_checkin_checkout as atomic
    from domains.pms.frontdesk_service import FrontdeskService
    from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2

    db, tid, _ = ready
    bid, gid = await seed(db, tid, status="confirmed", adults=2)
    await db.bookings.update_one({"tenant_id": tid, "id": bid}, {"$set": {"room_id": "local-room"}})
    await db.rooms.insert_one({"tenant_id": tid, "id": "local-room", "room_number": "101", "status": "available"})
    booking_day = (await db.bookings.find_one({"tenant_id": tid, "id": bid}))["check_in"][:10]
    await db.tenant_settings.update_one({"tenant_id": tid}, {"$set": {"business_date": booking_day}}, upsert=True)
    monkeypatch.setattr(atomic, "db", db)
    await db.guests.update_one({"tenant_id": tid, "id": gid}, {"$set": {"id_number": ""}})
    before = await db.bookings.find_one({"tenant_id": tid, "id": bid})
    with pytest.raises(atomic.CheckInError, match="KBS"):
        await atomic.check_in_booking_atomic(bid, tid, "staff", "Staff")
    ctx = OperationContext(tenant_id=tid, actor_id="staff", actor_role="admin")
    for cls in (FrontdeskService, FrontdeskServiceV2):
        service = cls()
        service._db = db
        result = await service.checkin(ctx, bid)
        assert not result.ok and result.code == "KBS_DATA_REQUIRED"
    assert await db.bookings.find_one({"tenant_id": tid, "id": bid}) == before
    assert await db.folios.count_documents({"tenant_id": tid}) == 0
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job"}) == 0


async def test_nightly_actual_event_uses_hotel_day_across_utc_midnight(ready):
    from core.kbs_nightly_sweep import sweep_tenant_kbs

    db, tid, _ = ready
    bid, _ = await seed(db, tid, checked_in_at="2026-11-01T21:30:00+00:00", check_in="2026-10-26")
    await db.tenant_settings.update_one({"tenant_id": tid}, {"$set": {"timezone": "Europe/Istanbul"}}, upsert=True)
    await sweep_tenant_kbs(db, tid, "2026-11-02")
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_kind": "queue_job", "booking_id": bid}) == 1


async def test_startup_cleanup_keeps_uncertain_and_duplicate_identity_locks(ready):
    from core.kbs_readiness import closed_lock_cleanup_query
    db, tid, _ = ready
    for reason in ("delivery_unknown_check_authority", "already_registered", "source_guest_missing"):
        await db.kbs_reports.insert_one({"tenant_id": tid, "_kind": "queue_job", "id": reason,
            "status": "dead", "_open_lock": f"{tid}:{reason}", "last_error": reason,
            "delivery_uncertain": reason == "delivery_unknown_check_authority"})
    await db.kbs_reports.update_many({**closed_lock_cleanup_query(), "tenant_id": tid}, {"$unset": {"_open_lock": ""}})
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "_open_lock": {"$exists": True}}) == 2


async def test_two_manual_requeues_cannot_create_two_open_deliveries(ready, monkeypatch):
    from core.security import get_current_user
    from routers import kbs
    db, tid, _ = ready
    bid, gid = await seed(db, tid)
    for jid in ("rejected-a", "rejected-b"):
        await db.kbs_reports.insert_one({"tenant_id": tid, "_kind": "queue_job", "id": jid,
            "booking_id": bid, "guest_id": gid, "action": "checkin", "status": "dead"})
    monkeypatch.setattr(kbs, "db", db)
    monkeypatch.setattr(kbs.kbs_queue_pubsub, "publish", AsyncMock())
    app = FastAPI()
    app.include_router(kbs.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="staff", tenant_id=tid, name="Staff", role="admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline") as client:
        results = await asyncio.gather(*(client.post(f"/api/kbs/queue/{jid}/requeue") for jid in ("rejected-a", "rejected-b")))
        assert sorted(r.status_code for r in results) == [200, 409]
    assert await db.kbs_reports.count_documents({"tenant_id": tid, "status": "pending"}) == 1
