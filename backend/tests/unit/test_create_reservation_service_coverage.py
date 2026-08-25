from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import core.database as database_module
import core.outbox_service as outbox_module
from core.atomic_booking import BookingConflictError
from models.schemas import BookingCreate
from modules.reservations.services import create_reservation_service as service_module


def _booking(**overrides):
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    values = {
        "guest_id": "guest-1",
        "room_id": "room-1",
        "check_in": f"{tomorrow.isoformat()}T14:00:00Z",
        "check_out": f"{(tomorrow + timedelta(days=2)).isoformat()}T12:00:00Z",
        "adults": 2,
        "children": 1,
        "children_ages": [8],
        "guests_count": 3,
        "total_amount": 1200.0,
        "special_requests": "Late arrival",
    }
    values.update(overrides)
    return BookingCreate(**values)


@pytest.fixture
def harness(monkeypatch):
    repository = SimpleNamespace(
        acquire_idempotency_lock=AsyncMock(
            return_value={"status": "acquired", "document": {}, "lock_id": "lock-1"}
        ),
        get_room_for_tenant=AsyncMock(return_value={"id": "room-1"}),
        get_guest_for_tenant=AsyncMock(return_value={"id": "guest-1"}),
        insert_rate_override_log=AsyncMock(),
        insert_booking=AsyncMock(),
        insert_folio=AsyncMock(),
        complete_idempotency_lock=AsyncMock(),
        fail_idempotency_lock=AsyncMock(),
    )
    tenant_settings = SimpleNamespace(find_one=AsyncMock(return_value=None))
    fake_database = SimpleNamespace(tenant_settings=tenant_settings)
    monkeypatch.setattr(database_module, "db", fake_database)

    generate_folio_number = AsyncMock(return_value="F-2026-0001")
    audit_log = AsyncMock()
    enqueue_outbox_event = AsyncMock()
    emit_event = AsyncMock()
    record_usage = AsyncMock()
    push_lifecycle = MagicMock(return_value="capx-event")
    fire_and_forget = MagicMock()
    sync_availability = MagicMock(return_value="availability-task")
    create_task = MagicMock(return_value="scheduled-task")

    monkeypatch.setattr(service_module, "generate_folio_number", generate_folio_number)
    monkeypatch.setattr(service_module, "generate_time_based_qr_token", lambda *_args, **_kwargs: "qr-token")
    monkeypatch.setattr(service_module, "generate_qr_code", lambda value: f"encoded:{value}")
    monkeypatch.setattr(service_module, "audit_log", audit_log)
    monkeypatch.setattr(outbox_module, "enqueue_outbox_event", enqueue_outbox_event)

    import asyncio

    import core.afsadakat_outbound as afsadakat_module
    import core.metering as metering_module
    import domains.channel_manager.availability_auto_sync as availability_module
    import integrations.capx as capx_module

    monkeypatch.setattr(afsadakat_module, "emit_event", emit_event)
    monkeypatch.setattr(metering_module, "record_usage", record_usage)
    monkeypatch.setattr(capx_module, "push_booking_lifecycle_event", push_lifecycle)
    monkeypatch.setattr(capx_module, "fire_and_forget", fire_and_forget)
    monkeypatch.setattr(availability_module, "sync_availability_after_booking", sync_availability)
    monkeypatch.setattr(asyncio, "create_task", create_task)

    return SimpleNamespace(
        service=service_module.CreateReservationService(repository),
        repository=repository,
        tenant_settings=tenant_settings,
        database=fake_database,
        booking=_booking(),
        user=SimpleNamespace(
            id="user-1",
            name="Ada Lovelace",
            tenant_id="tenant-1",
            property_id=None,
            selected_property_id=None,
        ),
        request=SimpleNamespace(
            headers={"Idempotency-Key": "idem-1", "x-correlation-id": "corr-1"}
        ),
        generate_folio_number=generate_folio_number,
        audit_log=audit_log,
        enqueue_outbox_event=enqueue_outbox_event,
        emit_event=emit_event,
        record_usage=record_usage,
        push_lifecycle=push_lifecycle,
        fire_and_forget=fire_and_forget,
        sync_availability=sync_availability,
        create_task=create_task,
    )


@pytest.mark.asyncio
async def test_create_persists_booking_folio_outbox_audit_and_optional_commercial_fields(harness):
    booking = _booking(
        base_rate=1400.0,
        total_amount=1200.0,
        override_reason="Manager discount",
        channel="expedia",
        rate_plan="BAR",
        source_channel="expedia",
        origin="api",
        hold_status="hold",
        allocation_source="channel",
        company_id="company-1",
        contracted_rate="corp_pref",
        rate_type="corporate",
        market_segment="corporate",
        cancellation_policy="h24",
        billing_address="Istanbul",
        billing_tax_number="1234567890",
        billing_contact_person="Grace Hopper",
        ota_channel="expedia",
        ota_confirmation="EXP-42",
        ota_reference_id="OTA-42",
        commission_pct=18.5,
    )

    result = await harness.service.create(booking, harness.user, harness.request)

    assert result["tenant_id"] == "tenant-1"
    assert result["channel"] == "expedia"
    assert result["contracted_rate"] == "corp_pref"
    assert result["rate_type"] == "corporate"
    assert result["market_segment"] == "corporate"
    assert result["cancellation_policy"] == "h24"
    assert result["ota_channel"] == "expedia"
    assert result["qr_code_data"] == "qr-token"
    assert result["qr_code"].startswith("encoded:booking:")
    assert result["paid_amount"] == 0.0
    assert result["_version"] == 1

    override = harness.repository.insert_rate_override_log.await_args.args[0]
    assert override["booking_id"] == result["id"]
    assert override["base_rate"] == 1400.0
    assert override["new_rate"] == 1200.0
    assert override["override_reason"] == "Manager discount"
    assert isinstance(override["timestamp"], str)

    inserted_booking = harness.repository.insert_booking.await_args.args[1]
    assert inserted_booking == result
    folio = harness.repository.insert_folio.await_args.args[0]
    assert folio["booking_id"] == result["id"]
    assert folio["folio_number"] == "F-2026-0001"
    assert folio["guest_id"] == "guest-1"
    assert isinstance(folio["created_at"], str)

    outbox = harness.enqueue_outbox_event.await_args
    assert outbox.args[0] is harness.database
    assert outbox.kwargs["tenant_id"] == "tenant-1"
    assert outbox.kwargs["entity_id"] == result["id"]
    assert outbox.kwargs["property_id"] == "tenant-1"
    assert outbox.kwargs["payload"]["source_channel"] == "expedia"
    assert outbox.kwargs["payload"]["origin"] == "api"

    harness.emit_event.assert_awaited_once()
    harness.fire_and_forget.assert_called_once_with("capx-event")
    harness.audit_log.assert_awaited_once()
    assert harness.audit_log.await_args.kwargs["correlation_id"] == "corr-1"
    harness.record_usage.assert_awaited_once()
    harness.sync_availability.assert_called_once()
    harness.create_task.assert_called_once_with("availability-task")
    harness.repository.complete_idempotency_lock.assert_awaited_once_with(
        "lock-1", result["id"], result
    )


@pytest.mark.asyncio
async def test_create_uses_defaults_without_writing_rate_override(harness):
    result = await harness.service.create(harness.booking, harness.user, harness.request)

    assert result["status"] == "confirmed"
    assert result["channel"] == "direct"
    assert result["rate_plan"] == "Standard"
    assert result["source_channel"] == "direct"
    assert result["origin"] == "ui"
    assert result["hold_status"] == "none"
    assert result["allocation_source"] == "manual"
    assert result["company_id"] is None
    assert result["ota_channel"] is None
    harness.repository.insert_rate_override_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_idempotent_request_replays_the_original_response(harness):
    request_hash = harness.service._build_request_hash("tenant-1", harness.booking)
    original = {"id": "booking-existing", "status": "confirmed"}
    harness.repository.acquire_idempotency_lock.return_value = {
        "status": "existing",
        "document": {
            "request_hash": request_hash,
            "status": "completed",
            "response_body": original,
        },
        "lock_id": "lock-existing",
    }

    result = await harness.service.create(harness.booking, harness.user, harness.request)

    assert result is original
    harness.repository.get_room_for_tenant.assert_not_awaited()


@pytest.mark.parametrize(
    ("document", "detail"),
    [
        ({"request_hash": "different", "status": "completed"}, "different payload"),
        ({"request_hash": "SAME", "status": "processing"}, "already in progress"),
    ],
)
@pytest.mark.asyncio
async def test_existing_idempotency_conflicts_are_rejected(harness, document, detail):
    if document["request_hash"] == "SAME":
        document["request_hash"] = harness.service._build_request_hash(
            "tenant-1", harness.booking
        )
    harness.repository.acquire_idempotency_lock.return_value = {
        "status": "existing",
        "document": document,
        "lock_id": "lock-existing",
    }

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(harness.booking, harness.user, harness.request)

    assert caught.value.status_code == 409
    assert detail in caught.value.detail
    harness.repository.fail_idempotency_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected_before_repository_access(harness):
    harness.request.headers = {}

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(harness.booking, harness.user, harness.request)

    assert caught.value.status_code == 400
    assert "Idempotency-Key" in caught.value.detail
    harness.repository.acquire_idempotency_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_property_scope_mismatch_is_rejected_before_lock(harness):
    harness.request.headers["x-property-id"] = "property-2"

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(harness.booking, harness.user, harness.request)

    assert caught.value.status_code == 403
    assert caught.value.detail == "Property scope mismatch"
    harness.repository.acquire_idempotency_lock.assert_not_awaited()


@pytest.mark.parametrize(
    ("missing", "detail"), [("room", "Room not found"), ("guest", "Guest not found")]
)
@pytest.mark.asyncio
async def test_missing_tenant_entities_fail_and_record_the_idempotency_error(
    harness, missing, detail
):
    if missing == "room":
        harness.repository.get_room_for_tenant.return_value = None
    else:
        harness.repository.get_guest_for_tenant.return_value = None

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(harness.booking, harness.user, harness.request)

    assert caught.value.status_code == 404
    assert caught.value.detail == detail
    harness.repository.fail_idempotency_lock.assert_awaited_once_with("lock-1", detail)


@pytest.mark.parametrize(
    "bad_value", ["not-a-date", "2026-99-99T14:00:00Z", None]
)
@pytest.mark.asyncio
async def test_invalid_dates_return_a_structured_bad_request(harness, bad_value):
    booking = harness.booking.model_copy(update={"check_in": bad_value})

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(booking, harness.user, harness.request)

    assert caught.value.status_code == 400
    assert caught.value.detail.startswith("Gecersiz tarih formati:")
    harness.repository.fail_idempotency_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_dates_before_the_earlier_business_or_calendar_date_are_rejected(harness):
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    two_days_ago = yesterday - timedelta(days=1)
    harness.tenant_settings.find_one.return_value = {
        "business_date": yesterday.isoformat()
    }
    booking = _booking(
        check_in=f"{two_days_ago.isoformat()}T14:00:00Z",
        check_out=f"{yesterday.isoformat()}T12:00:00Z",
    )

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(booking, harness.user, harness.request)

    assert caught.value.status_code == 400
    assert yesterday.isoformat() in caught.value.detail
    harness.repository.fail_idempotency_lock.assert_awaited_once_with(
        "lock-1", caught.value.detail
    )


@pytest.mark.asyncio
async def test_business_date_behind_calendar_allows_late_arrival_booking(harness):
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    harness.tenant_settings.find_one.return_value = {
        "business_date": yesterday.isoformat()
    }
    booking = _booking(
        check_in=f"{yesterday.isoformat()}T23:00:00Z",
        check_out=f"{datetime.now(UTC).date().isoformat()}T12:00:00Z",
    )

    result = await harness.service.create(booking, harness.user, harness.request)

    assert result["check_in"].startswith(yesterday.isoformat())


@pytest.mark.asyncio
async def test_atomic_booking_conflict_becomes_actionable_http_409(harness):
    harness.repository.insert_booking.side_effect = BookingConflictError(
        "Room already occupied",
        conflicting_booking_id="booking-2",
        conflict_type="room_night",
    )

    with pytest.raises(HTTPException) as caught:
        await harness.service.create(harness.booking, harness.user, harness.request)

    assert caught.value.status_code == 409
    assert caught.value.detail == {
        "message": "Room already occupied",
        "conflicting_booking_id": "booking-2",
        "conflict_type": "room_night",
        "conflict_window": {
            "room_id": "room-1",
            "check_in": harness.booking.check_in,
            "check_out": harness.booking.check_out,
        },
    }
    harness.repository.fail_idempotency_lock.assert_awaited_once_with(
        "lock-1", "Room already occupied"
    )


@pytest.mark.asyncio
async def test_unexpected_repository_failure_is_recorded_and_reraised(harness):
    failure = RuntimeError("database unavailable")
    harness.repository.insert_folio.side_effect = failure

    with pytest.raises(RuntimeError, match="database unavailable"):
        await harness.service.create(harness.booking, harness.user, harness.request)

    harness.repository.fail_idempotency_lock.assert_awaited_once_with(
        "lock-1", "database unavailable"
    )
    harness.repository.complete_idempotency_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_best_effort_integrations_do_not_break_reservation_creation(harness):
    harness.emit_event.side_effect = RuntimeError("loyalty unavailable")
    harness.fire_and_forget.side_effect = RuntimeError("capx unavailable")
    harness.record_usage.side_effect = RuntimeError("metering unavailable")
    harness.create_task.side_effect = RuntimeError("scheduler unavailable")

    result = await harness.service.create(harness.booking, harness.user, harness.request)

    assert result["status"] == "confirmed"
    harness.repository.complete_idempotency_lock.assert_awaited_once()


def test_request_hash_is_stable_and_tenant_and_payload_sensitive(harness):
    first = harness.service._build_request_hash("tenant-1", harness.booking)
    same = harness.service._build_request_hash("tenant-1", harness.booking)
    other_tenant = harness.service._build_request_hash("tenant-2", harness.booking)
    other_payload = harness.service._build_request_hash(
        "tenant-1", harness.booking.model_copy(update={"total_amount": 999.0})
    )

    assert first == same
    assert first != other_tenant
    assert first != other_payload
