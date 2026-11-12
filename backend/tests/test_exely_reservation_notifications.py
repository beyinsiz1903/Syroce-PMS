"""Bell delivery must follow durable imports without depending on provider ACK."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely import reservation_notifications as notices
from tests.test_exely_connection_controls import local_mongo as local_mongo
from tests.test_exely_reservation_lifecycle import _add_mapping, _canonical, _Collection, _persist, _room
from tests.test_exely_reservation_lifecycle import fake_db as fake_db

pytestmark = pytest.mark.exely_failure_stress


@pytest.fixture(autouse=True)
def _notification_collection(fake_db):
    fake_db.notifications = _Collection()


async def _import(database, *, version="2030-01-01T10:00:00Z", rooms=None, status="confirmed"):
    if not database.exely_room_mappings.documents:
        await _add_mapping(database)
    _, current = await _persist(database, _canonical(version, rooms=rooms, status=status), payload_hash=version)
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"]
    return current, result


async def test_multiroom_import_creates_one_actionable_tenant_notification(fake_db):
    current, result = await _import(fake_db, rooms=[_room("1"), _room("2")])
    assert len(fake_db.notifications.documents) == 1
    notice = fake_db.notifications.documents[0]
    assert notice["tenant_id"] == "tenant" and notice["read"] is False
    assert notice["type"] == "reservation" and notice["title"] == "Yeni Exely rezervasyonu"
    assert notice["related_entity"] == "booking" and notice["related_id"] == result["pms_booking_id"]
    assert notice["metadata"]["booking_ids"] == result["pms_booking_ids"]
    assert "2 oda" in notice["message"] and "2030-01-01 – 2030-01-03" in notice["message"]
    assert notice["metadata"]["external_reservation_id"] == current["external_id"]
    assert "email" not in str(notice) and "phone" not in str(notice)


async def test_replay_and_duplicate_pull_do_not_repeat_or_unread_a_notice(fake_db):
    current, _ = await _import(fake_db)
    fake_db.notifications.documents[0]["read"] = True
    await pms_lifecycle.process_reservation_version("tenant", current)
    result, _ = await _persist(fake_db, _canonical(), payload_hash="2030-01-01T10:00:00Z")
    assert result["reason"] == "duplicate_payload"
    await notices.deliver_pending_notifications(fake_db, "tenant")
    assert len(fake_db.notifications.documents) == 1 and fake_db.notifications.documents[0]["read"] is True


async def test_modification_and_cancellation_are_distinct_single_version_notices(fake_db):
    await _import(fake_db)
    await _import(fake_db, version="2030-01-01T11:00:00Z", rooms=[_room(amount=125)])
    await _import(fake_db, version="2030-01-01T12:00:00Z", status="cancelled")
    assert [row["type"] for row in fake_db.notifications.documents] == ["reservation", "reservation_modified", "reservation_cancelled"]
    assert len({row["id"] for row in fake_db.notifications.documents}) == 3
    assert len({row["related_id"] for row in fake_db.notifications.documents}) == 1


async def test_incomplete_pms_import_never_announces_a_new_booking(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    monkeypatch.setattr(pms_lifecycle, "_readback_expectations", AsyncMock(return_value=False))
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert not result["success"] and fake_db.notifications.documents == []
    assert fake_db.exely_reservation_versions.documents[0]["processing_state"] == lifecycle.PMS_FAILED


async def test_notification_failure_does_not_block_ack_and_is_retried_after_ack(fake_db, monkeypatch):
    update = fake_db.notifications.update_one
    monkeypatch.setattr(fake_db.notifications, "update_one", AsyncMock(side_effect=TimeoutError("synthetic-private-error")))
    current, _ = await _import(fake_db)
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    current = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]})
    assert (await lifecycle.acknowledge_durable_version(provider, current))["success"]
    assert fake_db.exely_reservation_versions.documents[0]["reservation_notification_state"] == "PENDING"
    monkeypatch.setattr(fake_db.notifications, "update_one", update)
    result = await pms_lifecycle.process_pending_reservations("tenant", provider=provider)
    assert result["total"] == 0 and len(fake_db.notifications.documents) == 1
    assert fake_db.exely_reservation_versions.documents[0]["reservation_notification_state"] == "SENT"
    provider.confirm_delivery.assert_awaited_once()


async def test_lost_notification_insert_response_does_not_duplicate_or_reset_read(fake_db, monkeypatch):
    real_update = fake_db.notifications.update_one

    async def lost_response(*args, **kwargs):
        await real_update(*args, **kwargs)
        raise TimeoutError("synthetic lost response")

    monkeypatch.setattr(fake_db.notifications, "update_one", lost_response)
    await _import(fake_db)
    fake_db.notifications.documents[0]["read"] = True
    monkeypatch.setattr(fake_db.notifications, "update_one", real_update)
    await notices.deliver_pending_notifications(fake_db, "tenant")
    assert len(fake_db.notifications.documents) == 1 and fake_db.notifications.documents[0]["read"] is True
    assert fake_db.exely_reservation_versions.documents[0]["reservation_notification_state"] == "SENT"


async def test_one_failed_notification_does_not_block_the_next_booking(fake_db, monkeypatch):
    first, _ = await _import(fake_db)
    await _import(fake_db, version="2030-01-01T11:00:00Z")
    for version in fake_db.exely_reservation_versions.documents:
        version["reservation_notification_state"] = "PENDING"
    fake_db.notifications.documents.clear()
    real_update = fake_db.notifications.update_one

    async def fail_first(query, update, **kwargs):
        if update["$setOnInsert"]["metadata"]["version_identity"] == first["provider_version_identity"]:
            raise TimeoutError("synthetic failure")
        return await real_update(query, update, **kwargs)

    monkeypatch.setattr(fake_db.notifications, "update_one", fail_first)
    await notices.deliver_pending_notifications(fake_db, "tenant")
    assert len(fake_db.notifications.documents) == 1
    assert fake_db.notifications.documents[0]["type"] == "reservation_modified"


async def test_other_tenant_and_historical_versions_are_not_backfilled(fake_db):
    await _import(fake_db)
    fake_db.notifications.documents.clear()
    version = fake_db.exely_reservation_versions.documents[0]
    version["reservation_notification_state"] = "PENDING"
    await notices.deliver_pending_notifications(fake_db, "foreign-tenant")
    assert fake_db.notifications.documents == []
    version.pop("reservation_notification_state")
    await notices.deliver_pending_notifications(fake_db, "tenant")
    assert fake_db.notifications.documents == []


@pytest.mark.parametrize("drift", ["tenant", "property", "version", "booking", "id"])
async def test_mismatched_intent_is_not_published(fake_db, drift):
    await _import(fake_db)
    fake_db.notifications.documents.clear()
    version = fake_db.exely_reservation_versions.documents[0]
    version["reservation_notification_state"] = "PENDING"
    notice = version["reservation_notification_v1"]
    if drift == "tenant":
        notice["tenant_id"] = "foreign-tenant"
    elif drift in {"property", "version"}:
        notice["metadata"]["property_id" if drift == "property" else "version_identity"] = "foreign"
    elif drift == "booking":
        notice["metadata"]["booking_ids"] = ["foreign-booking"]
    else:
        notice["id"] = notice["_id"] = "foreign"
    await notices.deliver_pending_notifications(fake_db, "tenant")
    assert fake_db.notifications.documents == [] and version["reservation_notification_state"] == "PENDING"


@pytest.mark.live_mongo
async def test_concurrent_real_mongo_delivery_is_one_notification_and_preserves_read(local_mongo, fake_db):
    await _import(fake_db)
    version = deepcopy(fake_db.exely_reservation_versions.documents[0])
    version["reservation_notification_state"] = "PENDING"
    await local_mongo.exely_reservation_versions.insert_one(version)
    await asyncio.gather(*(notices.deliver_notification(local_mongo, "tenant", version["version_identity"]) for _ in range(25)))
    assert await local_mongo.notifications.count_documents({"tenant_id": "tenant"}) == 1
    await local_mongo.notifications.update_one({"tenant_id": "tenant"}, {"$set": {"read": True}})
    await local_mongo.exely_reservation_versions.update_one({"tenant_id": "tenant"}, {"$set": {"reservation_notification_state": "PENDING"}})
    await notices.deliver_notification(local_mongo, "tenant", version["version_identity"])
    assert (await local_mongo.notifications.find_one({"tenant_id": "tenant"}))["read"] is True
    assert (await local_mongo.exely_reservation_versions.find_one({"tenant_id": "tenant"}))["reservation_notification_state"] == "SENT"
