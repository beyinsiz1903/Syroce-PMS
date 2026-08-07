"""Offline contract and lifecycle regressions for Exely PMSConnect."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lxml import etree
from pymongo.errors import DuplicateKeyError

from bootstrap.migrations.versions.v010_exely_reservation_lifecycle import (
    ExelyReservationLifecycleMigration,
)
from bootstrap.migrations.versions.v011_exely_reservation_fencing import (
    ExelyReservationFencingMigration,
)
from domains.channel_manager.providers import common_ingest
from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely.errors import ExelyTemporaryError
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.response_parser import parse_notif_report_rs, parse_read_rs
from domains.channel_manager.providers.exely.soap_builder import build_notif_report_rq

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, branch) for branch in expected):
                return False
            continue
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$exists" in expected and (key in document) is not expected["$exists"]:
                return False
            if "$type" in expected and expected["$type"] == "string" and not isinstance(actual, str):
                return False
            if "$lt" in expected and (actual is None or actual >= expected["$lt"]):
                return False
            if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                return False
            if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                return False
        elif actual != expected:
            return False
    return True


def _project(document, projection):
    if not projection:
        return deepcopy(document)
    included = [key for key, value in projection.items() if value and key != "_id"]
    if included:
        return {key: deepcopy(document[key]) for key in included if key in document}
    result = deepcopy(document)
    for key, value in projection.items():
        if not value:
            result.pop(key, None)
    return result


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    async def to_list(self, length):
        return deepcopy(self.documents[:length] if length is not None else self.documents)


class _Collection:
    def __init__(self):
        self.documents = []

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if _matches(document, query):
                return _project(document, projection)
        return None

    def find(self, query, projection=None):
        return _Cursor([_project(row, projection) for row in self.documents if _matches(row, query)])

    async def insert_one(self, document):
        if any(
            (document.get("id") and row.get("id") == document.get("id")) or (document.get("version_identity") and row.get("version_identity") == document.get("version_identity"))
            for row in self.documents
        ):
            raise DuplicateKeyError("duplicate")
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("id"))

    async def update_one(self, query, update, upsert=False):
        target = next((row for row in self.documents if _matches(row, query)), None)
        inserted = False
        if target is None and upsert:
            target = {key: value for key, value in query.items() if not isinstance(value, dict)}
            self.documents.append(target)
            inserted = True
        if target is None:
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)
        if inserted:
            target.update(deepcopy(update.get("$setOnInsert", {})))
        target.update(deepcopy(update.get("$set", {})))
        for key in update.get("$unset", {}):
            target.pop(key, None)
        for key, value in update.get("$inc", {}).items():
            target[key] = target.get(key, 0) + value
        return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=target.get("id") if inserted else None)


class _DB:
    def __init__(self):
        self.exely_reservation_versions = _Collection()
        self.exely_reservations = _Collection()
        self.exely_room_mappings = _Collection()
        self.bookings = _Collection()
        self.guests = _Collection()


@pytest.fixture
def fake_db(monkeypatch):
    database = _DB()
    monkeypatch.setattr(lifecycle, "db", database)
    monkeypatch.setattr(pms_lifecycle, "db", database)

    async def _create_booking_atomic(*, tenant_id, booking_doc):
        assert booking_doc["tenant_id"] == tenant_id
        await database.bookings.insert_one(booking_doc)
        return booking_doc

    monkeypatch.setattr("core.atomic_booking.create_booking_atomic", _create_booking_atomic)
    monkeypatch.setattr("core.atomic_booking.release_booking_nights", AsyncMock(return_value=0))
    monkeypatch.setattr("security.guest_write.encrypt_guest_insert", lambda document: document)
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.release_unmatched_reservation_hold",
        AsyncMock(return_value={"released": True, "deleted": True}),
    )
    return database


def _room(index="1", room="STD", rate="BAR", amount=100.0):
    return {
        "index_number": index,
        "room_type_code": room,
        "rate_plan_code": rate,
        "room_name": room,
        "adults": 2,
        "children": 0,
        "amount": amount,
        "daily_rates": [],
        "check_in": "2030-01-01T12:00:00",
        "check_out": "2030-01-03T12:00:00",
        "guest_name": "Test Guest",
    }


def _canonical(version="2030-01-01T10:00:00Z", rooms=None, status="confirmed"):
    rooms = rooms if rooms is not None else [_room()]
    return {
        "external_id": "provider-reservation",
        "provider_reservation_id": "provider-reservation",
        "provider_reservation_id_context": "context",
        "property_id": "property",
        "provider_last_modified_at": version,
        "provider_created_at": "2030-01-01T09:00:00Z",
        "channel": "channel",
        "channel_display": "Channel",
        "status": status,
        "guest": {
            "name": "Test Guest",
            "first_name": "Test",
            "last_name": "Guest",
            "email": "",
            "phone": "",
            "country": "",
        },
        "stay": {"check_in": "2030-01-01", "check_out": "2030-01-03", "nights": 2},
        "financial": {
            "total_amount": sum(float(room.get("amount") or 0) for room in rooms),
            "currency": "USD",
            "payment_method": "",
        },
        "rooms": rooms,
        "total_rooms": len(rooms),
        "total_guests": sum(int(room.get("adults") or 0) + int(room.get("children") or 0) for room in rooms),
        "notes": "",
        "ingested_via": "pull",
        "message_uid": "provider-reservation",
    }


async def _add_mapping(database, room="STD", rate="BAR", pms="Standard"):
    await database.exely_room_mappings.insert_one(
        {
            "id": f"{room}-{rate}",
            "tenant_id": "tenant",
            "exely_room_code": room,
            "exely_rate_plan_code": rate,
            "pms_room_type": pms,
        }
    )


async def _persist(database, canonical, payload_hash="hash", event_type="reservation"):
    result = await lifecycle.persist_exely_event("tenant", canonical, event_type, "event", payload_hash)
    current = await database.exely_reservations.find_one(
        {"tenant_id": "tenant", "property_id": "property", "external_id": "provider-reservation"},
        {"_id": 0},
    )
    return result, current


def test_notif_report_contract_uses_exact_version_context_and_roomstay_indexes():
    xml = build_notif_report_rq(
        "user",
        "password",
        "property",
        "provider-reservation",
        "pms-1",
        create_datetime="2030-01-01T09:00:00Z",
        last_modify_datetime="2030-01-01T10:00:00+03:00",
        provider_id_context="context",
        confirmations=[
            {
                "pms_booking_id": "pms-1",
                "room_stay_indexes": ["11"],
                "pms_created_at": "2030-01-01T09:01:00Z",
            },
            {
                "pms_booking_id": "pms-2",
                "room_stay_indexes": ["22"],
                "pms_created_at": "2030-01-01T09:02:00Z",
            },
        ],
    )
    tree = etree.fromstring(xml.encode())
    namespace = {"soap": SOAP_NS, "ota": OTA_NS}
    request = tree.find("soap:Body/ota:OTA_NotifReportRQ", namespace)
    assert request is not None and request.get("Version") == "1.17"
    reservations = request.findall(".//ota:HotelReservation", namespace)
    assert len(reservations) == 2
    assert {row.get("LastModifyDateTime") for row in reservations} == {"2030-01-01T10:00:00+03:00"}
    assert [row.get("CreateDateTime") for row in reservations] == [
        "2030-01-01T09:01:00Z",
        "2030-01-01T09:02:00Z",
    ]
    assert {row.find("ota:UniqueID", namespace).get("ID_Context") for row in reservations} == {"context"}
    assert [row.find(".//ota:RoomStay", namespace).get("IndexNumber") for row in reservations] == ["11", "22"]


def test_notif_report_requires_exact_provider_timestamps():
    with pytest.raises(ValueError, match="Exact provider"):
        build_notif_report_rq("user", "password", "property", "reservation", "pms")


def test_ack_parser_requires_explicit_success():
    response = f'<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body><OTA_NotifReportRS xmlns="{OTA_NS}"/></soap:Body></soap:Envelope>'
    assert parse_notif_report_rs(response.encode())["result_class"] == "MALFORMED"


def test_read_parser_preserves_provider_context_and_roomstay_index():
    response = f'''<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body>
    <OTA_ResRetrieveRS xmlns="{OTA_NS}"><Success/><ReservationsList><HotelReservation
    CreateDateTime="2030-01-01T09:00:00Z" LastModifyDateTime="2030-01-01T10:00:00Z" ResStatus="Commit">
    <UniqueID Type="14" ID="provider-reservation" ID_Context="context"/>
    <RoomStays><RoomStay IndexNumber="17"><RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
    <RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans><TimeSpan Start="2030-01-01" End="2030-01-02"/>
    </RoomStay></RoomStays></HotelReservation></ReservationsList></OTA_ResRetrieveRS>
    </soap:Body></soap:Envelope>'''
    parsed = parse_read_rs(response.encode())
    reservation = parsed["reservations"][0]
    assert reservation["reservation_id_context"] == "context"
    assert reservation["rooms"][0]["index_number"] == "17"


@pytest.mark.asyncio
async def test_stale_and_conflicting_versions_fail_closed(fake_db):
    await _add_mapping(fake_db)
    first, _ = await _persist(fake_db, _canonical(), payload_hash="one")
    stale, _ = await _persist(fake_db, _canonical("2029-12-31T23:00:00Z"), payload_hash="old")
    conflict, _ = await _persist(fake_db, _canonical(), payload_hash="different")
    assert first["action"] == "created"
    assert stale["reason"] == "stale_event"
    assert conflict["reason"] == "VERSION_PAYLOAD_CONFLICT"


@pytest.mark.asyncio
async def test_mapping_failure_requires_hold_and_alarm_and_never_acks(fake_db, monkeypatch):
    hold = AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True})
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )
    result, current = await _persist(fake_db, _canonical())
    assert result["action"] == "hold"
    assert current["pms_status"] == "pending_mapping"
    hold.assert_awaited_once()
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    ack = await lifecycle.acknowledge_durable_version(provider, current)
    assert ack["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_rate_mapping_is_a_hold_not_a_default_room(fake_db, monkeypatch):
    await _add_mapping(fake_db, "STD", "OTHER")
    hold = AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True})
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )
    result, current = await _persist(fake_db, _canonical())
    assert result["reason"] == "ROOM_RATE_MAPPING_MISSING"
    assert current["pms_status"] == "pending_mapping"
    assert fake_db.bookings.documents == []


@pytest.mark.asyncio
async def test_duplicate_roomstay_indexes_are_held_fail_closed(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    hold = AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True})
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )
    result, _ = await _persist(fake_db, _canonical(rooms=[_room("11"), _room("11")]))
    assert result["reason"] == "ROOM_STAY_INDEX_DUPLICATE"
    assert fake_db.bookings.documents == []


@pytest.mark.asyncio
async def test_multiroom_create_modify_partial_cancel_and_full_cancel_are_idempotent(fake_db):
    await _add_mapping(fake_db, "STD", "BAR", "Standard")
    await _add_mapping(fake_db, "DLX", "FLEX", "Deluxe")

    _, current = await _persist(fake_db, _canonical(rooms=[_room("11"), _room("22", "DLX", "FLEX", 200)]))
    created = await pms_lifecycle.process_reservation_version("tenant", current)
    assert created["success"] is True and created["created"] == 2
    original_ids = created["pms_booking_ids"]
    assert len(set(original_ids)) == 2

    _, modified_current = await _persist(
        fake_db,
        _canonical("2030-01-01T11:00:00Z", [_room("111"), _room("222", "DLX", "FLEX", 250)], "modified"),
        payload_hash="modify",
        event_type="modification",
    )
    modified = await pms_lifecycle.process_reservation_version("tenant", modified_current)
    assert modified["success"] is True
    assert modified["pms_booking_ids"] == original_ids

    _, partial_current = await _persist(
        fake_db,
        _canonical("2030-01-01T12:00:00Z", [_room("333")], "modified"),
        payload_hash="partial",
        event_type="modification",
    )
    partial = await pms_lifecycle.process_reservation_version("tenant", partial_current)
    assert partial["success"] is True and partial["cancelled"] == 1
    active = await fake_db.bookings.find_one({"id": original_ids[0]}, {"_id": 0})
    removed = await fake_db.bookings.find_one({"id": original_ids[1]}, {"_id": 0})
    assert active["status"] == "confirmed"
    assert removed["status"] == "cancelled"
    partial_version = await fake_db.exely_reservation_versions.find_one({"version_identity": partial_current["provider_version_identity"]}, {"_id": 0})
    assert len(partial_version["ack_confirmations"]) == 1
    assert partial_version["ack_confirmations"][0]["pms_booking_id"] == original_ids[0]
    assert partial_version["ack_confirmations"][0]["room_stay_indexes"] == ["333"]
    assert partial_version["ack_confirmations"][0]["pms_created_at"]

    _, cancelled_current = await _persist(
        fake_db,
        _canonical("2030-01-01T13:00:00Z", [_room("444")], "cancelled"),
        payload_hash="cancel",
        event_type="cancellation",
    )
    cancelled = await pms_lifecycle.process_reservation_version("tenant", cancelled_current)
    assert cancelled["success"] is True and cancelled["cancelled"] == 1
    active = await fake_db.bookings.find_one({"id": original_ids[0]}, {"_id": 0})
    assert active["status"] == "cancelled"

    duplicate = await pms_lifecycle.process_reservation_version("tenant", cancelled_current)
    assert duplicate["success"] is True
    assert len(fake_db.bookings.documents) == 2


@pytest.mark.asyncio
async def test_mapping_replay_creates_one_booking_after_mapping_is_fixed(fake_db, monkeypatch):
    hold = AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True})
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )
    _, current = await _persist(fake_db, _canonical())
    await _add_mapping(fake_db)
    replay = await pms_lifecycle.process_reservation_version("tenant", current)
    assert replay["success"] is True
    duplicate = await pms_lifecycle.process_reservation_version("tenant", current)
    assert duplicate["success"] is True
    assert len(fake_db.bookings.documents) == 1


@pytest.mark.asyncio
async def test_pms_readback_failure_never_enables_ack(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    monkeypatch.setattr(pms_lifecycle, "_readback_expectations", AsyncMock(return_value=False))
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"] is False
    version = await fake_db.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]}, {"_id": 0})
    assert version["ack_state"] == lifecycle.ACK_NOT_READY


@pytest.mark.asyncio
async def test_durable_multiroom_ack_is_exact_and_sent_once(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"] is True
    current = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    ack = await lifecycle.acknowledge_durable_version(provider, current)
    assert ack == {"success": True, "provider_write_count": 1, "reason": "ACKED"}
    provider.confirm_delivery.assert_awaited_once()
    kwargs = provider.confirm_delivery.await_args.kwargs
    version = await fake_db.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]}, {"_id": 0})
    assert kwargs["create_datetime"] == version["ack_confirmations"][0]["pms_created_at"]
    assert kwargs["last_modify_datetime"] == "2030-01-01T10:00:00Z"
    assert kwargs["provider_id_context"] == "context"
    second = await lifecycle.acknowledge_durable_version(provider, current)
    assert second["provider_write_count"] == 0
    provider.confirm_delivery.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_modification_after_ack_gets_a_new_pending_ack(fake_db):
    await _add_mapping(fake_db)
    _, first_current = await _persist(fake_db, _canonical(), payload_hash="create")
    await pms_lifecycle.process_reservation_version("tenant", first_current)
    first_current = await fake_db.exely_reservations.find_one({"provider_version_identity": first_current["provider_version_identity"]}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    assert (await lifecycle.acknowledge_durable_version(provider, first_current))["success"] is True

    _, modified = await _persist(
        fake_db,
        _canonical("2030-01-01T11:00:00Z", status="modified"),
        payload_hash="modify",
        event_type="modification",
    )
    assert modified["delivery_confirmed"] is False
    assert modified["delivery_state"] == lifecycle.ACK_NOT_READY
    result = await pms_lifecycle.process_reservation_version("tenant", modified)
    assert result["success"] is True
    modified_version = await fake_db.exely_reservation_versions.find_one({"version_identity": modified["provider_version_identity"]}, {"_id": 0})
    assert modified_version["ack_state"] == lifecycle.ACK_PENDING
    assert provider.confirm_delivery.await_count == 1


@pytest.mark.asyncio
async def test_wrong_or_older_version_ack_is_rejected_without_write(fake_db):
    await _add_mapping(fake_db)
    _, old_current = await _persist(fake_db, _canonical(), payload_hash="create")
    await pms_lifecycle.process_reservation_version("tenant", old_current)
    _, new_current = await _persist(
        fake_db,
        _canonical("2030-01-01T11:00:00Z", status="modified"),
        payload_hash="modify",
        event_type="modification",
    )
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    result = await lifecycle.acknowledge_durable_version(provider, old_current)
    assert result["reason"] == "STALE_VERSION"
    assert result["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()

    stale_cancel, current_after = await _persist(
        fake_db,
        _canonical("2030-01-01T10:30:00Z", status="cancelled"),
        payload_hash="stale-cancel",
        event_type="cancellation",
    )
    assert stale_cancel["reason"] == "stale_event"
    assert current_after["provider_version_identity"] == new_current["provider_version_identity"]


@pytest.mark.asyncio
async def test_crash_safe_replay_after_pms_write_does_not_create_second_booking(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    first = await pms_lifecycle.process_reservation_version("tenant", current)
    assert first["success"] is True
    version = fake_db.exely_reservation_versions.documents[0]
    version["processing_state"] = lifecycle.PMS_FAILED
    version["ack_state"] = lifecycle.ACK_NOT_READY
    replay = await pms_lifecycle.process_reservation_version("tenant", current)
    assert replay["success"] is True
    assert len(fake_db.bookings.documents) == 1


@pytest.mark.asyncio
async def test_cancellation_lock_release_failure_blocks_ack_and_retries_cleanup(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical(), payload_hash="create")
    await pms_lifecycle.process_reservation_version("tenant", current)
    release = AsyncMock(side_effect=[RuntimeError("lock store unavailable"), 0])
    monkeypatch.setattr("core.atomic_booking.release_booking_nights", release)

    _, cancelled_current = await _persist(
        fake_db,
        _canonical("2030-01-01T11:00:00Z", status="cancelled"),
        payload_hash="cancel",
        event_type="cancellation",
    )
    first = await pms_lifecycle.process_reservation_version("tenant", cancelled_current)
    assert first["success"] is False
    version = await fake_db.exely_reservation_versions.find_one({"version_identity": cancelled_current["provider_version_identity"]}, {"_id": 0})
    assert version["ack_state"] == lifecycle.ACK_NOT_READY

    second = await pms_lifecycle.process_reservation_version("tenant", cancelled_current)
    assert second["success"] is True
    assert release.await_count == 2


@pytest.mark.asyncio
async def test_ack_timeout_is_ambiguous_and_never_retried(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    await pms_lifecycle.process_reservation_version("tenant", current)
    current = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock(side_effect=TimeoutError("timeout")))
    first = await lifecycle.acknowledge_durable_version(provider, current)
    second = await lifecycle.acknowledge_durable_version(provider, current)
    assert first["reason"] == "ACK_AMBIGUOUS"
    assert second["provider_write_count"] == 0
    provider.confirm_delivery.assert_awaited_once()


@pytest.mark.asyncio
async def test_ack_rejects_roomstay_mapping_mismatch_before_provider_write(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    await pms_lifecycle.process_reservation_version("tenant", current)
    version = fake_db.exely_reservation_versions.documents[0]
    version["ack_confirmations"][0]["room_stay_indexes"] = ["wrong-index"]
    current = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    result = await lifecycle.acknowledge_durable_version(provider, current)
    assert result["reason"] == "ACK_CONFIRMATION_MAPPING_INVALID"
    assert result["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_ack_rejects_pending_inventory_cleanup_before_provider_write(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    booking = next(row for row in fake_db.bookings.documents if row["id"] == result["pms_booking_id"])
    booking["inventory_release_pending"] = True
    current = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    ack = await lifecycle.acknowledge_durable_version(provider, current)
    assert ack["reason"] == "PMS_READBACK_FAILED"
    assert ack["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_confirm_delivery_does_not_use_retry_on_temporary_failure():
    provider = ExelyProvider(username="user", password="password", hotel_code="property", max_retries=9)
    provider._transport.send_soap = AsyncMock(side_effect=ExelyTemporaryError())
    result = await provider.confirm_delivery(
        "provider-reservation",
        "pms-booking",
        create_datetime="2030-01-01T09:00:00Z",
        last_modify_datetime="2030-01-01T10:00:00Z",
    )
    assert result.success is False
    assert result.error_type == "AMBIGUOUS"
    assert result.metadata["provider_write_count"] == 1
    provider._transport.send_soap.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifecycle_migration_requires_unique_identity_indexes():
    version_collection = SimpleNamespace(create_indexes=AsyncMock())
    current_collection = SimpleNamespace(create_indexes=AsyncMock())
    database = SimpleNamespace(
        exely_reservation_versions=version_collection,
        exely_reservations=current_collection,
    )
    await ExelyReservationLifecycleMigration().up(database)
    version_indexes = version_collection.create_indexes.await_args.args[0]
    current_indexes = current_collection.create_indexes.await_args.args[0]
    assert version_indexes[0].document["unique"] is True
    assert current_indexes[0].document["unique"] is True


@pytest.mark.asyncio
async def test_lifecycle_migration_index_failure_is_fail_closed():
    database = SimpleNamespace(
        exely_reservation_versions=SimpleNamespace(create_indexes=AsyncMock(side_effect=RuntimeError("index unavailable"))),
        exely_reservations=SimpleNamespace(create_indexes=AsyncMock()),
    )
    with pytest.raises(RuntimeError, match="index unavailable"):
        await ExelyReservationLifecycleMigration().up(database)


@pytest.mark.asyncio
async def test_ten_concurrent_workers_produce_one_pms_booking(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())

    results = await asyncio.gather(*(pms_lifecycle.process_reservation_version("tenant", current) for _ in range(10)))

    assert sum(result.get("created", 0) for result in results) == 1
    assert len(fake_db.bookings.documents) == 1
    version = await fake_db.exely_reservation_versions.find_one(
        {"version_identity": current["provider_version_identity"]},
        {"_id": 0},
    )
    assert version["processing_state"] == lifecycle.PMS_DURABLE
    assert version["ack_state"] == lifecycle.ACK_PENDING
    assert "processing_owner_token" not in version


@pytest.mark.asyncio
async def test_expired_lease_is_taken_over_and_old_owner_is_fenced(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    identity = current["provider_version_identity"]

    old_claim = await pms_lifecycle._acquire_processing_claim(identity)
    assert old_claim is not None
    assert await pms_lifecycle._acquire_processing_claim(identity) is None
    version = fake_db.exely_reservation_versions.documents[0]
    version["processing_lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    new_claim = await pms_lifecycle._acquire_processing_claim(identity)
    assert new_claim is not None
    assert new_claim.generation == old_claim.generation + 1
    assert (
        await pms_lifecycle._finish_processing_claim(
            old_claim,
            processing_state=lifecycle.PMS_FAILED,
        )
        is False
    )
    assert version["processing_owner_token"] == new_claim.owner_token


@pytest.mark.asyncio
async def test_heartbeat_renews_only_the_current_owner_lease(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    claim = await pms_lifecycle._acquire_processing_claim(current["provider_version_identity"])
    assert claim is not None
    version = fake_db.exely_reservation_versions.documents[0]
    original_expiry = version["processing_lease_expires_at"]

    assert await pms_lifecycle._renew_processing_claim(claim) is True
    assert version["processing_lease_expires_at"] >= original_expiry
    wrong_owner = pms_lifecycle.ProcessingClaim(
        claim.version_identity,
        "wrong-owner",
        claim.generation,
    )
    assert await pms_lifecycle._renew_processing_claim(wrong_owner) is False
    assert version["processing_owner_token"] == claim.owner_token


@pytest.mark.asyncio
async def test_process_crash_lease_expiry_allows_single_safe_replay(fake_db):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())
    identity = current["provider_version_identity"]
    abandoned = await pms_lifecycle._acquire_processing_claim(identity)
    assert abandoned is not None
    fake_db.exely_reservation_versions.documents[0]["processing_lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    replay = await pms_lifecycle.process_reservation_version("tenant", current)

    assert replay["success"] is True
    assert replay["created"] == 1
    assert len(fake_db.bookings.documents) == 1


@pytest.mark.asyncio
async def test_old_worker_cannot_overwrite_new_generation_booking(fake_db):
    old_claim = pms_lifecycle.ProcessingClaim("identity", "old-owner", 1)
    booking = {
        "id": "booking",
        "tenant_id": "tenant",
        "provider_version_key": "2030-01-01T10:00:00Z",
        "exely_processing_generation": 2,
        "room_type": "Standard",
        "check_in": "2030-01-01",
        "check_out": "2030-01-02",
        "status": "confirmed",
    }
    await fake_db.bookings.insert_one(booking)
    stale_update = {
        **booking,
        "room_type": "Stale",
        "exely_processing_generation": 1,
    }

    with pytest.raises(pms_lifecycle.ProcessingClaimLostError):
        await pms_lifecycle._upsert_booking("tenant", stale_update, old_claim)
    stored = await fake_db.bookings.find_one({"id": "booking"}, {"_id": 0})
    assert stored["room_type"] == "Standard"
    assert stored["exely_processing_generation"] == 2


@pytest.mark.asyncio
async def test_heartbeat_loss_fails_closed_without_ack(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    _, current = await _persist(fake_db, _canonical())

    async def _lose_claim(_claim, claim_lost):
        claim_lost.set()

    monkeypatch.setattr(pms_lifecycle, "_processing_claim_heartbeat", _lose_claim)
    result = await pms_lifecycle.process_reservation_version("tenant", current)

    assert result == {
        "success": False,
        "reason": "PROCESSING_CLAIM_LOST",
        "provider_write_count": 0,
    }
    version = await fake_db.exely_reservation_versions.find_one(
        {"version_identity": current["provider_version_identity"]},
        {"_id": 0},
    )
    assert version["ack_state"] == lifecycle.ACK_NOT_READY
    assert len(fake_db.bookings.documents) == 0


@pytest.mark.asyncio
async def test_mapping_replay_race_produces_one_booking(fake_db, monkeypatch):
    hold = AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True})
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )
    _, current = await _persist(fake_db, _canonical())
    await _add_mapping(fake_db)

    results = await asyncio.gather(*(pms_lifecycle.process_reservation_version("tenant", current) for _ in range(10)))

    assert sum(result.get("created", 0) for result in results) == 1
    assert len(fake_db.bookings.documents) == 1


@pytest.mark.asyncio
async def test_concurrent_raw_event_duplicate_is_resolved_by_unique_claim(monkeypatch):
    monkeypatch.setattr(
        common_ingest,
        "_check_provider_event_recorded",
        AsyncMock(side_effect=[None, {"id": "existing-event"}]),
    )
    monkeypatch.setattr(
        common_ingest,
        "store_raw_event",
        AsyncMock(side_effect=DuplicateKeyError("duplicate event")),
    )

    result = await common_ingest.ingest_reservation(
        "exely",
        "tenant",
        {
            "external_id": "provider-reservation",
            "last_modify": "2030-01-01T10:00:00Z",
        },
        lambda _payload, _source: pytest.fail("duplicate must stop before normalize"),
    )

    assert result["success"] is True
    assert result["action"] == "duplicate"
    assert result["reason"] == "concurrent_event_claimed"


@pytest.mark.asyncio
async def test_fencing_migration_requires_all_critical_unique_indexes():
    versions = SimpleNamespace(create_indexes=AsyncMock())
    raw_events = SimpleNamespace(create_indexes=AsyncMock())
    bookings = SimpleNamespace(create_indexes=AsyncMock())
    database = SimpleNamespace(
        exely_reservation_versions=versions,
        exely_raw_events=raw_events,
        bookings=bookings,
    )

    await ExelyReservationFencingMigration().up(database)

    version_indexes = versions.create_indexes.await_args.args[0]
    raw_indexes = raw_events.create_indexes.await_args.args[0]
    booking_indexes = bookings.create_indexes.await_args.args[0]
    assert version_indexes[0].document["unique"] is True
    assert raw_indexes[0].document["unique"] is True
    assert booking_indexes[0].document["unique"] is True


@pytest.mark.asyncio
async def test_fencing_migration_unique_index_failure_is_fail_closed():
    database = SimpleNamespace(
        exely_reservation_versions=SimpleNamespace(create_indexes=AsyncMock(side_effect=RuntimeError("index unavailable"))),
        exely_raw_events=SimpleNamespace(create_indexes=AsyncMock()),
        bookings=SimpleNamespace(create_indexes=AsyncMock()),
    )
    with pytest.raises(RuntimeError, match="index unavailable"):
        await ExelyReservationFencingMigration().up(database)
