"""Normal bulk action must not create one provider request per interval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lxml import etree

from domains.channel_manager.providers.exely import ari_delivery, exely_router
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import QuotaDecision

pytestmark = pytest.mark.exely_failure_stress


def update(room, start, end, availability):
    return exely_router.ExelyARIUpdate(room_type_code=room, rate_plan_code="BASE", start_date=start, end_date=end, availability=availability)


@pytest.fixture
def bulk(monkeypatch):
    database = SimpleNamespace(exely_connections=SimpleNamespace(find_one=AsyncMock(return_value={"hotel_code": "synthetic-property"})))
    monkeypatch.setattr(exely_router, "db", database)
    monkeypatch.setattr(exely_router, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr(exely_router, "log_sync", AsyncMock())
    deliver = AsyncMock(return_value=ari_delivery.ExelyARIDeliveryResult(True, "confirmed", "", "SUCCESS", 1, "synthetic-operation"))
    monkeypatch.setattr(exely_router, "deliver_exely_ari", deliver)
    enqueue = AsyncMock(return_value={"accepted": True, "queued_operation_count": 1})
    monkeypatch.setattr(exely_router, "enqueue_exely_ari_update", enqueue)
    return SimpleNamespace(db=database, deliver=deliver, enqueue=enqueue)


async def send(updates, key="synthetic-request-1"):
    return await exely_router.bulk_push_ari(updates, SimpleNamespace(tenant_id="synthetic-tenant", id="synthetic-operator", name="Synthetic"), None, key)


async def test_existing_bulk_action_delivers_all_rooms_and_stock_periods_once(bulk):
    rows = [update("STD", "2026-11-02", "2026-11-09", 8), update("STD", "2026-11-10", "2026-11-10", 4),
            update("STD", "2026-11-11", "2028-11-01", 8), update("DLX", "2026-11-02", "2028-11-01", 8)]
    result = await send(rows)
    assert result["queued"] == 0 and result["confirmed"] == 4 and result["provider_write_count"] == 1
    assert result["provider_verified"] is True
    bulk.enqueue.assert_not_awaited()
    bulk.deliver.assert_awaited_once()
    tenant, operation, payload = bulk.deliver.await_args.args
    assert (tenant, operation, payload["property_id"]) == ("synthetic-tenant", "availability_batch", "synthetic-property")
    assert len(payload["value"]) == 4
    assert {m["room_type_code"] for m in payload["value"]} == {"STD", "DLX"}
    assert payload["operation_identity"] == "exely-bulk-availability:synthetic-request-1"
    assert bulk.db.exely_connections.find_one.await_args.args[0] == {"tenant_id": tenant, "is_active": True}


def test_merge_only_adjacent_equal_stock_not_changed_values_or_gaps():
    messages = exely_router._availability_batch_messages([
        update("STD", "2026-11-05", "2026-11-05", 0), update("STD", "2026-11-03", "2026-11-03", 0),
        update("STD", "2026-11-04", "2026-11-04", 0), update("STD", "2026-11-07", "2026-11-07", 0),
        update("STD", "2026-11-08", "2026-11-09", 3), update("DLX", "2026-11-03", "2026-11-09", 8),
    ])
    assert [(m["room_type_code"], m["start_date"], m["end_date"], m["availability"]) for m in messages] == [
        ("DLX", "2026-11-03", "2026-11-09", 8), ("STD", "2026-11-03", "2026-11-05", 0),
        ("STD", "2026-11-07", "2026-11-07", 0), ("STD", "2026-11-08", "2026-11-09", 3),
    ]


@pytest.mark.parametrize("availability", [4, 8])
async def test_overlap_rejects_whole_bulk_before_any_queue_or_provider_write(bulk, availability):
    with pytest.raises(HTTPException) as exc:
        await send([update("STD", "2026-11-02", "2026-11-09", 8), update("STD", "2026-11-09", "2026-11-10", availability)])
    assert exc.value.status_code == 422
    bulk.deliver.assert_not_awaited()
    bulk.enqueue.assert_not_awaited()


@pytest.mark.parametrize("state,status,warnings,success,writes", [
    ("warning_success", "WARNING_SUCCESS", ("438",), True, 1),
    ("ambiguous", "AMBIGUOUS", (), False, 1),
    ("blocked", "NOT_SENT", (), False, 0),
])
async def test_unconfirmed_batch_is_never_reported_as_error_free_or_retried(bulk, state, status, warnings, success, writes):
    bulk.deliver.return_value = ari_delivery.ExelyARIDeliveryResult(success, state, "blocked" if not success else "", status, writes, "synthetic", warnings)
    result = await send([update("STD", "2026-11-02", "2026-11-09", 8)])
    assert result["provider_verified"] is False and result["confirmed"] == 0
    assert result["provider_write_count"] == writes
    bulk.deliver.assert_awaited_once()
    bulk.enqueue.assert_not_awaited()


async def test_native_batch_reaches_one_soap_container_and_one_transport_call(bulk, monkeypatch):
    await send([update("STD", "2026-11-02", "2026-11-09", 8), update("STD", "2026-11-10", "2026-11-10", 0),
                update("DLX", "2026-11-02", "2026-11-10", 4)])
    messages = bulk.deliver.await_args.args[2]["value"]
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="synthetic-property", connection_id="offline-bulk")
    provider._transport.send_soap = AsyncMock(return_value=b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/></OTA_HotelAvailNotifRS></s:Body></s:Envelope>')
    result = await provider.push_ari_operation(operation="availability_batch", room_type_code="", rate_plan_code="", start_date="", end_date="", value=messages)
    assert result.success and result.metadata["provider_write_count"] == 1
    provider._transport.send_soap.assert_awaited_once()
    xml = etree.fromstring(provider._transport.send_soap.await_args.args[0].encode())
    ns = {"ota": "http://www.opentravel.org/OTA/2003/05"}
    assert len(xml.findall(".//ota:AvailStatusMessages", ns)) == 1
    assert [m.get("BookingLimit") for m in xml.findall(".//ota:AvailStatusMessage", ns)] == ["4", "8", "0"]


async def test_full_period_batch_still_respects_quota_denial_before_one_write(monkeypatch):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(False, "PROVIDER_QUOTA_EXCEEDED", 2)))
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="synthetic-property", connection_id="offline-quota", quota_guard=quota)
    provider._transport.send_soap = AsyncMock()
    rows = exely_router._availability_batch_messages([update(room, "2026-11-02", "2028-11-01", 8) for room in ("STD", "DLX")])
    result = await provider.push_ari_operation(operation="availability_batch", room_type_code="", rate_plan_code="", start_date="", end_date="", value=rows)
    assert not result.success and result.metadata["provider_write_count"] == 0
    quota.reserve.assert_awaited_once_with(operation="ari_mutation", change_count=731)
    provider._transport.send_soap.assert_not_awaited()


async def test_same_idempotency_key_with_changed_values_does_not_claim_old_confirmation(monkeypatch):
    monkeypatch.setattr(ari_delivery, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr(ari_delivery, "_prepare_delivery", AsyncMock(return_value=(False, {"state": "confirmed", "payload_fingerprint": "different"})))
    provider = AsyncMock()
    rows = exely_router._availability_batch_messages([update("STD", "2026-11-02", "2026-11-09", 8)])
    result = await ari_delivery.deliver_exely_ari("synthetic", "availability_batch", {
        "property_id": "synthetic-property", "value": rows, "operation_identity": "same-key",
    }, provider=provider, write_enabled=True)
    assert not result.success and result.error_code == "EXELY_ARI_IDENTITY_PAYLOAD_MISMATCH"
    provider.push_ari_operation.assert_not_awaited()


async def test_mixed_rate_and_inventory_requests_keep_existing_queue_contract(bulk):
    result = await send([update("STD", "2026-11-02", "2026-11-09", 8),
                         exely_router.ExelyARIUpdate(room_type_code="STD", rate_plan_code="BASE", start_date="2026-11-02", end_date="2026-11-09", rate_amount=100)])
    assert result["queued"] == 2
    assert result["provider_write_count"] == 0
    assert bulk.enqueue.await_count == 2
    bulk.deliver.assert_not_awaited()
