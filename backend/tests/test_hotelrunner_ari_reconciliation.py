from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from channel_manager.connectors.hotelrunner_v2 import router as hrv2_router
from channel_manager.connectors.hotelrunner_v2.endpoint_map import ENDPOINTS
from domains.channel_manager import availability_reconciliation_worker
from domains.channel_manager.ari.ack_service import process_ack
from domains.channel_manager.ari.adapters.hotelrunner_ari_adapter import (
    HotelRunnerARIAdapter,
)
from domains.channel_manager.ari.events import ARIDelta, ProviderResult
from domains.channel_manager.providers.hotelrunner import endpoints as ep
from domains.channel_manager.providers.hotelrunner import provider as provider_module
from domains.channel_manager.providers.hotelrunner import router_sync
from domains.channel_manager.providers.hotelrunner.ari_delivery import (
    STATE_AMBIGUOUS,
    STATE_BLOCKED,
    STATE_CONFIRMED,
    STATE_PARTIAL_FAILURE,
    STATE_RECONCILIATION_PENDING,
    ARIDeliveryResult,
    deliver_hotelrunner_ari,
    preview_ari_update,
)
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerTemporaryError,
)
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider


@pytest.fixture
def persistence_stubs(monkeypatch):
    create = AsyncMock(return_value=True)
    update = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._create_reconciliation_record",
        create,
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._update_reconciliation_record",
        update,
    )
    return create, update


def _update(**overrides):
    update = {
        "inv_code": "synthetic-room",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "availability": 3,
    }
    update.update(overrides)
    return update


def _provider(*, send=None, transaction=None):
    send = send or {"success": True, "data": {"status": "ok", "transaction_id": "synthetic-transaction"}}
    transaction = transaction or {
        "success": True,
        "data": {"transaction": {"counts": {"succeeded": 1, "failed": 0, "in_progress": 0}}},
    }
    return SimpleNamespace(
        update_room=AsyncMock(return_value=send),
        get_transaction_details=AsyncMock(return_value=transaction),
    )


def test_dry_run_preview_is_explicit_and_never_writes():
    result = preview_ari_update(_update(stop_sale=1, min_stay=2))

    assert result == {
        "success": True,
        "mode": "dry_run",
        "method": "PUT",
        "endpoint": "/api/v2/apps/rooms/~",
        "fields": ["availability", "min_stay", "stop_sale"],
        "provider_write_count": 0,
    }


@pytest.mark.asyncio
async def test_live_write_disabled_fails_before_provider_call(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=False),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.state == STATE_BLOCKED
    assert result.provider_write_count == 0
    provider.update_room.assert_not_awaited()
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("update", "error_code"),
    [
        (_update(start_date="09/01/2026"), "ARI_DATE_FORMAT_INVALID"),
        (_update(start_date="2026-09-03", end_date="2026-09-02"), "ARI_DATE_RANGE_INVALID"),
        (_update(availability=None), "ARI_MUTATION_FIELD_MISSING"),
        (_update(availability=-1), "ARI_AVAILABILITY_INVALID"),
        (_update(availability=1, min_stay=4, max_stay=2), "ARI_STAY_RANGE_INVALID"),
        (_update(availability=1, days=[7]), "ARI_DAYS_INVALID"),
    ],
)
async def test_invalid_contract_is_blocked_before_provider_call(update, error_code):
    provider = _provider()

    result = await deliver_hotelrunner_ari("synthetic-tenant", update, provider=provider)

    assert result.state == STATE_BLOCKED
    assert result.error_code == error_code
    assert result.provider_write_count == 0
    provider.update_room.assert_not_awaited()
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_transaction_is_the_only_success(monkeypatch, persistence_stubs):
    provider = _provider()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is True
    assert result.state == STATE_CONFIRMED
    assert result.provider_status_class == "SUCCEEDED"
    assert result.provider_write_count == 1
    provider.update_room.assert_awaited_once_with(**_update())
    provider.get_transaction_details.assert_awaited_once()


@pytest.mark.asyncio
async def test_accepted_write_without_durable_reconciliation_is_not_success(
    monkeypatch,
    persistence_stubs,
):
    _, update_record = persistence_stubs
    update_record.return_value = False
    provider = _provider()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is False
    assert result.state == STATE_AMBIGUOUS
    assert result.error_code == "ARI_RECONCILIATION_STORE_UNAVAILABLE"
    assert result.provider_write_count == 1
    provider.update_room.assert_awaited_once()
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("counts", "expected_state", "status_class"),
    [
        ({"succeeded": 1, "failed": 0, "in_progress": 1}, STATE_RECONCILIATION_PENDING, "PENDING"),
        ({"succeeded": 1, "failed": 1, "in_progress": 0}, STATE_PARTIAL_FAILURE, "PARTIAL_FAILURE"),
        ({"succeeded": 0, "failed": 0, "in_progress": 0}, STATE_AMBIGUOUS, "EMPTY_RESULT"),
    ],
)
async def test_non_terminal_or_partial_transaction_never_passes(
    monkeypatch,
    persistence_stubs,
    counts,
    expected_state,
    status_class,
):
    provider = _provider(
        transaction={
            "success": True,
            "data": {"transaction": {"counts": counts}},
        }
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is False
    assert result.state == expected_state
    assert result.provider_status_class == status_class
    assert result.provider_write_count == 1
    provider.update_room.assert_awaited_once()


@pytest.mark.asyncio
async def test_ambiguous_write_is_not_retried(monkeypatch, persistence_stubs):
    provider = _provider()
    provider.update_room.side_effect = TimeoutError("synthetic timeout")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is False
    assert result.state == STATE_AMBIGUOUS
    assert result.provider_write_count == 1
    assert provider.update_room.await_count == 1
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_write_response_is_ambiguous(monkeypatch, persistence_stubs):
    provider = _provider()
    provider.update_room.return_value = None
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is False
    assert result.state == STATE_AMBIGUOUS
    assert result.error_code == "ARI_WRITE_RESPONSE_INVALID"
    assert result.provider_write_count == 1
    assert provider.update_room.await_count == 1
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_500_classification_is_ambiguous_and_not_retryable(
    monkeypatch,
    persistence_stubs,
):
    provider = _provider(
        send={
            "success": False,
            "error": "synthetic server error",
            "error_type": "HotelRunnerTemporaryError",
        }
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        AsyncMock(return_value=True),
    )

    result = await deliver_hotelrunner_ari("synthetic-tenant", _update(), provider=provider)

    assert result.success is False
    assert result.state == STATE_AMBIGUOUS
    assert result.provider_status_class == "WRITE_OUTCOME_UNKNOWN"
    assert result.retryable is False
    assert result.provider_write_count == 1
    assert provider.update_room.await_count == 1
    provider.get_transaction_details.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_update_room_bypasses_retry_policy(monkeypatch):
    provider = object.__new__(HotelRunnerProvider)
    provider._connection_id = "synthetic-connection"
    provider._client = SimpleNamespace(put=AsyncMock(side_effect=HotelRunnerTemporaryError("synthetic timeout")))
    provider._retry = SimpleNamespace(execute=AsyncMock())
    monkeypatch.setattr(provider_module.obs, "record_provider_failure", lambda **kwargs: None)

    result = await provider.update_room(**_update(max_stay=5, cta=1, ctd=0))

    assert result["success"] is False
    assert result["error_type"] == "HotelRunnerTemporaryError"
    assert provider._client.put.await_count == 1
    assert provider._client.put.await_args.kwargs["params"]["max_stay"] == "5"
    assert provider._client.put.await_args.kwargs["params"]["cta"] == "1"
    assert provider._client.put.await_args.kwargs["params"]["ctd"] == "0"
    provider._retry.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_delivery_stops_after_first_unconfirmed_result(monkeypatch):
    confirmed = ARIDeliveryResult(True, STATE_CONFIRMED, "", "SUCCEEDED", 1)
    ambiguous = ARIDeliveryResult(
        False,
        STATE_AMBIGUOUS,
        "ARI_WRITE_TIMEOUT",
        "WRITE_OUTCOME_UNKNOWN",
        1,
    )
    deliver = AsyncMock(side_effect=[confirmed, ambiguous])
    monkeypatch.setattr(router_sync, "deliver_hotelrunner_ari", deliver)
    monkeypatch.setattr(router_sync, "get_provider", AsyncMock(return_value=(SimpleNamespace(), {})))
    monkeypatch.setattr(router_sync, "log_sync", AsyncMock())
    updates = [SimpleNamespace(model_dump=lambda **_: _update(availability=value)) for value in (1, 2, 3)]

    with pytest.raises(HTTPException) as exc_info:
        await router_sync.bulk_update_ari(
            updates,
            current_user=SimpleNamespace(tenant_id="synthetic-tenant", name="synthetic-user"),
            _perm=None,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["skipped"] == 1
    assert deliver.await_count == 2


@pytest.mark.asyncio
async def test_legacy_ari_dlq_retry_is_blocked_before_provider_write(monkeypatch):
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"operation": "ari_push"}),
    )
    monkeypatch.setattr(
        "core.database.db",
        {"connector_dlq": collection},
    )

    with pytest.raises(HTTPException) as exc_info:
        await hrv2_router.retry_dlq_entry(
            "synthetic-dlq",
            tenant_id="synthetic-tenant",
            property_id="synthetic-property",
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "ARI_DLQ_RETRY_REQUIRES_RECONCILIATION"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "payload", "expected"),
    [
        ("availability", {"availability": 4, "stop_sale": 1}, {"availability": 4, "stop_sale": 1}),
        ("rate", {"price": 125.0}, {"price": 125.0}),
        (
            "restriction",
            {"min_stay": 2, "max_stay": 5, "cta": 1, "ctd": 0},
            {"min_stay": 2, "max_stay": 5, "cta": 1, "ctd": 0},
        ),
    ],
)
async def test_all_scopes_use_canonical_date_range_contract(
    monkeypatch,
    scope,
    payload,
    expected,
):
    delivery = ARIDeliveryResult(
        success=True,
        state=STATE_CONFIRMED,
        error_code="",
        provider_status_class="SUCCEEDED",
        provider_write_count=1,
    )
    deliver = AsyncMock(return_value=delivery)
    monkeypatch.setattr(
        "domains.channel_manager.ari.adapters.hotelrunner_ari_adapter.deliver_hotelrunner_ari",
        deliver,
    )
    delta = ARIDelta(
        provider="hotelrunner",
        tenant_id="synthetic-tenant",
        property_id="synthetic-property",
        change_scope=scope,
        room_type_code="synthetic-room",
        rate_plan_code="synthetic-rate",
        date_from="2026-09-01",
        date_to="2026-09-02",
        payload=payload,
    )
    adapter = HotelRunnerARIAdapter(provider_client=SimpleNamespace())

    if scope == "availability":
        result = await adapter.push_availability(delta)
    elif scope == "rate":
        result = await adapter.push_rate(delta)
    else:
        result = await adapter.push_restrictions(delta)

    assert result.success is True
    sent_update = deliver.await_args.args[1]
    assert sent_update["inv_code"] == "synthetic-room"
    assert sent_update["start_date"] == "2026-09-01"
    assert sent_update["end_date"] == "2026-09-02"
    assert {key: sent_update[key] for key in expected} == expected


@pytest.mark.asyncio
async def test_unconfirmed_delivery_cannot_be_acked(monkeypatch):
    insert_log = AsyncMock()
    update_status = AsyncMock()
    monkeypatch.setattr(
        "domains.channel_manager.ari.ack_service.repo.insert_outbound_log",
        insert_log,
    )
    monkeypatch.setattr(
        "domains.channel_manager.ari.ack_service.repo.update_change_set_status",
        update_status,
    )
    change_set = {
        "id": "synthetic-change",
        "tenant_id": "synthetic-tenant",
        "property_id": "synthetic-property",
        "provider": "hotelrunner",
        "change_scope": "availability",
        "provider_delta_hash": "synthetic-hash",
        "compacted_payload": {"availability": 2},
    }
    result = ProviderResult(
        success=False,
        provider="hotelrunner",
        status_code=202,
        error="ARI_TRANSACTION_PENDING",
        delivery_state=STATE_RECONCILIATION_PENDING,
        provider_write_count=1,
    )

    status = await process_ack(change_set, result, "synthetic-outbound")

    assert status == "manual_review"
    assert update_status.await_args.args[1] == "manual_review"
    logged = insert_log.await_args.args[0]
    assert logged["request_payload"] == {
        "scope": "availability",
        "fields": ["availability"],
    }
    assert logged["response_payload"] is None


@pytest.mark.asyncio
async def test_periodic_hotelrunner_reconciliation_is_get_only(monkeypatch):
    connection_collection = SimpleNamespace(find_one=AsyncMock(return_value={"is_active": True}))
    monkeypatch.setattr(
        availability_reconciliation_worker,
        "db",
        SimpleNamespace(hotelrunner_connections=connection_collection),
    )
    reconcile = AsyncMock(
        return_value={
            "checked": 2,
            "confirmed": 1,
            "pending": 1,
            "failed": 0,
            "provider_write_count": 0,
        }
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.ari_delivery.reconcile_pending_hotelrunner_ari",
        reconcile,
    )

    confirmed = await availability_reconciliation_worker._push_reconciliation_hr(
        "synthetic-tenant",
        {"synthetic-room": {"2026-09-01": 3}},
    )

    assert confirmed == 1
    reconcile.assert_awaited_once_with("synthetic-tenant")
    assert reconcile.await_args is not None


def test_official_hotelrunner_ari_endpoints_are_canonical_v2_paths():
    assert ep.ROOMS_DATERANGE == "/api/v2/apps/rooms/~"
    assert ep.TRANSACTION_DETAILS == "/api/v2/apps/infos/transaction_details"
    assert ENDPOINTS["rooms_update"]["method"] == "PUT"
    assert ENDPOINTS["rooms_update"]["path"] == ep.ROOMS_DATERANGE
    assert ENDPOINTS["transaction_details"] == {
        "path": ep.TRANSACTION_DETAILS,
        "method": "GET",
        "api_version": "v2",
        "description": "Get ARI update transaction status/logs",
    }
