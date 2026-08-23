"""Direct regressions for HotelRunner ACK, mapping hold, and safe replay."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers import sync_engine


class _Provider:
    def __init__(self, reservations):
        self.get_reservations = AsyncMock(
            return_value={
                "success": True,
                "data": {"reservations": reservations, "pages": 1},
            }
        )
        self.confirm_delivery = AsyncMock(return_value=SimpleNamespace(success=True, error=None))


def _reservation(*, state="confirmed", uid="opaque-message"):
    return {
        "hr_number": "opaque-reservation",
        "message_uid": uid,
        "state": state,
        "updated_at": "2030-01-01T12:00:00Z",
    }


def _patch_phase_a(monkeypatch, *, durability, pipeline_status="processed"):
    monkeypatch.setattr(
        sync_engine,
        "explode_multi_room_reservation",
        lambda reservation: [reservation],
    )
    monkeypatch.setattr(sync_engine, "_resolve_property_id", lambda _: "property")
    persist = AsyncMock(return_value=SimpleNamespace(status=pipeline_status, decision="create"))
    ensure = AsyncMock(return_value=durability)
    monkeypatch.setattr(sync_engine, "_persist_and_process", persist)
    monkeypatch.setattr(sync_engine, "_ensure_durable_pms_result", ensure)
    monkeypatch.setattr(
        sync_engine,
        "_read_durable_pms_number",
        AsyncMock(return_value="pms-booking"),
    )
    monkeypatch.setattr(sync_engine, "log_pull", AsyncMock())
    return persist, ensure


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_event_type"),
    [
        ("confirmed", "reservation_pull"),
        ("modified", "reservation_pull"),
        ("cancelled", "reservation_cancel_pull"),
    ],
    ids=["successful-create", "successful-modification", "successful-cancellation"],
)
async def test_durable_lifecycle_result_sends_one_ack(
    monkeypatch,
    state,
    expected_event_type,
):
    persist, _ = _patch_phase_a(monkeypatch, durability=sync_engine._PMS_DURABLE)
    provider = _Provider([_reservation(state=state), _reservation(state=state)])

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is True
    assert result["fired"] == 1
    provider.confirm_delivery.assert_awaited_once_with(
        message_uid="opaque-message",
        pms_number="pms-booking",
    )
    assert all(call.args[3] == expected_event_type for call in persist.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("durability", "pipeline_status"),
    [
        (sync_engine._PMS_FAILED, "processed"),
        (sync_engine._PMS_FAILED, "failed"),
        (sync_engine._PMS_PENDING, "retry_later"),
    ],
    ids=["pms-create-failure", "pipeline-failed", "lock-contention"],
)
async def test_non_durable_pipeline_result_never_acks(
    monkeypatch,
    durability,
    pipeline_status,
):
    _patch_phase_a(
        monkeypatch,
        durability=durability,
        pipeline_status=pipeline_status,
    )
    provider = _Provider([_reservation()])

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is False
    assert result["fired"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapping_failure_creates_hold_and_alarm_but_never_acks(monkeypatch):
    trigger = AsyncMock()
    hold = AsyncMock(
        return_value={
            "created": True,
            "booking_id": "opaque-hold",
            "alarm_raised": True,
        }
    )
    monkeypatch.setattr(
        "domains.channel_manager.ingest.pipeline._trigger_import_bridge",
        trigger,
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        hold,
    )

    from domains.channel_manager.ingest.pipeline import _persist_mapping_hold

    persisted = await _persist_mapping_hold(
        tenant_id="tenant",
        property_id="property",
        provider="hotelrunner",
        lineage_id="lineage",
        canonical={
            "external_reservation_id": "opaque-reservation",
            "check_in": "2030-01-01",
            "check_out": "2030-01-02",
            "room_type_code": "opaque-room",
            "rate_plan_code": "opaque-rate",
        },
        room_mapping=None,
        rate_mapping=None,
        connector_id="connector",
    )

    assert persisted is True
    trigger.assert_awaited_once()
    hold.assert_awaited_once()

    _patch_phase_a(
        monkeypatch,
        durability=sync_engine._PMS_FAILED,
        pipeline_status="failed",
    )
    provider = _Provider([_reservation()])
    result = await sync_engine.run_phase_a("tenant", provider, 5)
    assert result["success"] is False
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_failure", ["http-500", "timeout"])
async def test_provider_failure_never_acks(monkeypatch, provider_failure, caplog):
    provider = _Provider([])
    if provider_failure == "http-500":
        provider.get_reservations.return_value = {
            "success": False,
            "error": "HTTP 500",
        }
    else:
        provider.get_reservations.side_effect = TimeoutError("provider timeout")
    monkeypatch.setattr(sync_engine, "log_pull", AsyncMock())

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is False
    assert result["fired"] == 0
    provider.confirm_delivery.assert_not_awaited()
    assert "HTTP 500" not in caplog.text
    if provider_failure == "http-500":
        assert "Provider page fetch failed" in caplog.text
        assert "failure_class=UPSTREAM_5XX" in caplog.text
        assert not any(record.levelname == "ERROR" for record in caplog.records)
    else:
        assert "Provider page fetch raised TimeoutError" in caplog.text
        assert any(record.levelname == "ERROR" for record in caplog.records)


@pytest.mark.asyncio
async def test_provider_parse_failure_never_acks(monkeypatch):
    provider = _Provider([])
    provider.get_reservations.return_value = {"success": True, "data": "invalid"}
    monkeypatch.setattr(sync_engine, "log_pull", AsyncMock())

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is False
    assert result["fired"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_ack_timeout_is_not_success(monkeypatch):
    _patch_phase_a(monkeypatch, durability=sync_engine._PMS_DURABLE)
    provider = _Provider([_reservation()])
    provider.confirm_delivery.side_effect = TimeoutError("ack timeout")

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is False
    assert result["fired"] == 0
    provider.confirm_delivery.assert_awaited_once()


@pytest.mark.asyncio
async def test_durable_booking_without_pms_number_never_acks(monkeypatch):
    _patch_phase_a(monkeypatch, durability=sync_engine._PMS_DURABLE)
    monkeypatch.setattr(
        sync_engine,
        "_read_durable_pms_number",
        AsyncMock(return_value=None),
    )
    provider = _Provider([_reservation()])

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is False
    assert result["fired"] == 0
    provider.confirm_delivery.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_cancellation", "readback_status"),
    [(False, "confirmed"), (True, "cancelled")],
    ids=["modification-readback", "cancellation-readback"],
)
async def test_durable_result_requires_pms_readback(
    monkeypatch,
    is_cancellation,
    readback_status,
):
    bookings = _Collection(find_one=lambda *_args, **_kwargs: {"status": readback_status})
    imported = _Collection(find_one=lambda *_args, **_kwargs: None)
    fake_db = SimpleNamespace(bookings=bookings, imported_reservations=imported)
    sync_update = AsyncMock(return_value=True)
    monkeypatch.setattr(sync_engine, "db", fake_db)
    monkeypatch.setattr(sync_engine, "sync_reservation_update", sync_update)
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.release_unmatched_reservation_hold",
        AsyncMock(return_value={"booking_id": None, "released": False}),
    )

    durability = await sync_engine._ensure_durable_pms_result(
        "tenant",
        _reservation(state="cancelled" if is_cancellation else "modified"),
        SimpleNamespace(status="processed", decision="update"),
        is_cancellation=is_cancellation,
    )

    assert durability == sync_engine._PMS_DURABLE
    assert bookings.find_one.await_count == 2
    sync_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_mapping_fix_replay_produces_one_booking_and_one_ack(monkeypatch):
    from core import import_bridge_service

    state = {"booking": None, "created": 0}

    async def _find_booking(*_args, **_kwargs):
        return {"id": "durable-booking", "status": "confirmed"} if state["booking"] else None

    async def _replay(**_kwargs):
        state["created"] += 1
        state["booking"] = "durable-booking"
        return {"status": "durable"}

    fake_db = SimpleNamespace(
        bookings=_Collection(find_one=_find_booking),
        imported_reservations=_Collection(find_one=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(sync_engine, "db", fake_db)
    monkeypatch.setattr(
        sync_engine,
        "explode_multi_room_reservation",
        lambda reservation: [reservation],
    )
    monkeypatch.setattr(sync_engine, "_resolve_property_id", lambda _: "property")
    monkeypatch.setattr(
        sync_engine,
        "_persist_and_process",
        AsyncMock(return_value=SimpleNamespace(status="duplicate", decision="skip")),
    )
    monkeypatch.setattr(sync_engine, "sync_reservation_update", AsyncMock(return_value=True))
    monkeypatch.setattr(sync_engine, "log_pull", AsyncMock())
    monkeypatch.setattr(
        import_bridge_service,
        "replay_reviewed_mapping_import",
        AsyncMock(side_effect=_replay),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.release_unmatched_reservation_hold",
        AsyncMock(return_value={"booking_id": None, "released": False}),
    )
    provider = _Provider([_reservation(), _reservation()])

    result = await sync_engine.run_phase_a("tenant", provider, 5)

    assert result["success"] is True
    assert state["created"] == 1
    assert result["fired"] == 1
    provider.confirm_delivery.assert_awaited_once_with(
        message_uid="opaque-message",
        pms_number="durable-booking",
    )


class _Collection:
    def __init__(self, *, find_one=None, find_one_and_update=None):
        self.find_one = AsyncMock(side_effect=find_one)
        self.find_one_and_update = AsyncMock(side_effect=find_one_and_update)


class _ReplayDB:
    def __init__(self, record):
        self.imported_reservations = _Collection(
            find_one=lambda *_args, **_kwargs: record,
            find_one_and_update=lambda *_args, **_kwargs: {
                **record,
                "import_status": "processing",
                "review_reason": None,
            },
        )
        self.room_mappings = _Collection(find_one=lambda *_args, **_kwargs: {"pms_room_type_id": "room"})
        self.rate_plan_mappings = _Collection(find_one=lambda *_args, **_kwargs: {"pms_rate_plan_id": "rate"})

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.mark.asyncio
async def test_mapping_fix_replay_creates_one_booking_and_duplicate_is_noop(monkeypatch):
    from core import import_bridge_service

    record = {
        "id": "import",
        "tenant_id": "tenant",
        "property_id": "property",
        "provider": "hotelrunner",
        "external_reservation_id": "opaque-reservation",
        "import_status": "review_required",
        "review_reason": "unmapped_room_type",
        "room_type_code": "opaque-room",
        "rate_plan_code": "opaque-rate",
    }
    fake_db = _ReplayDB(record)
    booking = {"id": None}

    async def _booking_exists(*_args, **_kwargs):
        return booking["id"]

    async def _auto_import(*_args, **_kwargs):
        booking["id"] = "durable-booking"
        return True, "imported"

    auto_import = AsyncMock(side_effect=_auto_import)
    monkeypatch.setattr(import_bridge_service, "db", fake_db)
    monkeypatch.setattr(
        import_bridge_service,
        "check_booking_source_exists",
        AsyncMock(side_effect=_booking_exists),
    )
    monkeypatch.setattr(
        import_bridge_service,
        "auto_import_reservation_to_pms",
        auto_import,
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.create_unmatched_reservation_hold",
        AsyncMock(return_value={"booking_id": "hold", "alarm_raised": True}),
    )

    first = await import_bridge_service.replay_reviewed_mapping_import(
        tenant_id="tenant",
        provider="hotelrunner",
        external_reservation_id="opaque-reservation",
    )
    second = await import_bridge_service.replay_reviewed_mapping_import(
        tenant_id="tenant",
        provider="hotelrunner",
        external_reservation_id="opaque-reservation",
    )

    assert first == {"status": "durable"}
    assert second == {"status": "durable"}
    auto_import.assert_awaited_once()
    assert fake_db.imported_reservations.find_one_and_update.await_count == 1
