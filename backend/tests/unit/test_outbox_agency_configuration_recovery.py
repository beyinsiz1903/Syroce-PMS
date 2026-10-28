"""Agency failures must not inherit the OTA mapping readiness fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import agency_webhook
from core import outbox_configuration as module
from routers import agency_contracts, outbox_admin


def event(error="permanent: agency contract has no webhook_url"):
    return {
        "id": "agency-event", "tenant_id": "hotel", "provider": "agency",
        "event_type": agency_webhook.AGENCY_INVENTORY_UPDATED, "status": "failed",
        "last_error": error, "payload": {"agency_id": "partner", "room_type_id": "Standard"},
    }


@pytest.fixture
def configuration(monkeypatch):
    contract = AsyncMock(return_value={"webhook_url": "https://partner.example/events"})
    secret = AsyncMock(return_value={
        "tenant_id": "hotel", "agency_id": "partner", "shared_secret": "synthetic-secret",
    })
    monkeypatch.setattr(agency_contracts, "has_active_contract", contract)
    monkeypatch.setattr(agency_webhook, "_resolve_outbound_secret", secret)
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: "read-only-db")
    # Any accidental external dispatch must fail, not simulate a delivery.
    monkeypatch.setattr(agency_webhook, "safe_post_async", AsyncMock(side_effect=AssertionError("network forbidden")))
    return contract, secret


@pytest.mark.asyncio
async def test_live_failure_shape_is_not_ready_without_webhook(configuration, monkeypatch):
    contract, secret = configuration
    contract.return_value = {"id": "contract"}
    events = SimpleNamespace(find_one=AsyncMock(return_value=event()))
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    result = await outbox_admin.outbox_requeue_readiness("agency-event")
    assert result["ready"] is False and result["can_requeue"] is False
    assert result["issues"] == ["agency_webhook_url_missing"]
    secret.assert_not_awaited()


@pytest.mark.asyncio
async def test_requeue_is_blocked_without_touching_the_failed_record(configuration, monkeypatch):
    contract, _ = configuration
    contract.return_value = {"id": "contract"}
    events = SimpleNamespace(find_one=AsyncMock(return_value=event()), find_one_and_update=AsyncMock())
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    with pytest.raises(HTTPException) as exc:
        await outbox_admin.requeue_event("agency-event")
    assert exc.value.status_code == 409
    events.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_repaired_configuration_can_be_rechecked_without_delivery(configuration):
    contract, secret = configuration
    result = await module.agency_configuration_readiness(event())
    assert result == {"ready": True, "issues": [], "providers": ["agency"]}
    contract.assert_awaited_once_with("partner", "hotel")
    secret.assert_awaited_once_with("read-only-db", "hotel", "partner")
    agency_webhook.safe_post_async.assert_not_awaited()
    assert "synthetic-secret" not in str(result) and "partner.example" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("contract,issue", [
    (None, "agency_contract_inactive"), ({}, "agency_contract_inactive"),
    ({"id": "contract"}, "agency_webhook_url_missing"),
    ({"webhook_url": "   "}, "agency_webhook_url_missing"),
])
async def test_missing_contract_or_address_is_fail_closed(configuration, contract, issue):
    configuration[0].return_value = contract
    assert (await module.agency_configuration_readiness(event()))["issues"] == [issue]
    configuration[1].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("resolved", [
    None, {},
    {"tenant_id": "other-hotel", "agency_id": "partner", "shared_secret": "secret"},
    {"tenant_id": "hotel", "agency_id": "other-partner", "shared_secret": "secret"},
    {"tenant_id": "hotel", "agency_id": "partner", "shared_secret": ""},
])
async def test_missing_or_wrong_scope_signing_configuration_is_not_ready(configuration, resolved):
    configuration[1].return_value = resolved
    result = await module.agency_configuration_readiness(event())
    assert result == {"ready": False, "issues": ["agency_signing_secret_not_configured"], "providers": ["agency"]}
    agency_webhook.safe_post_async.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("document", [
    {**event(), "tenant_id": ""}, {**event(), "payload": {}},
    {**event(), "payload": "malformed"},
])
async def test_incomplete_event_does_not_query_configuration(configuration, document):
    result = await module.agency_configuration_readiness(document)
    assert result["ready"] is False and result["issues"] == ["agency_webhook_payload_incomplete"]
    configuration[0].assert_not_awaited()


def test_only_known_agency_configuration_failures_are_classified():
    assert module.is_agency_configuration_failure(event())
    assert not module.is_agency_configuration_failure({**event(), "event_type": "booking.created.v1"})
    assert not module.is_agency_configuration_failure(event("retryable: HTTP 503"))


@pytest.mark.asyncio
async def test_repaired_single_requeue_preserves_error_and_compare_and_set(configuration, monkeypatch):
    events = SimpleNamespace(find_one=AsyncMock(return_value=event()), find_one_and_update=AsyncMock(return_value={"id": "agency-event"}))
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    assert (await outbox_admin.requeue_event("agency-event")).success
    query, update = events.find_one_and_update.call_args.args
    assert query["tenant_id"] == "hotel" and query["last_error"] == event()["last_error"]
    assert update["$set"]["requeue_previous_error"] == event()["last_error"]
    agency_webhook.safe_post_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_replay_cannot_bypass_agency_configuration_preflight(monkeypatch):
    events = SimpleNamespace(count_documents=AsyncMock(return_value=2), update_many=AsyncMock(return_value=SimpleNamespace(modified_count=0)))
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    result = await outbox_admin.replay_failed_events(provider="agency", tenant_id="hotel")
    assert result.blocked_count == 2 and result.requeued_count == 0
    query = events.update_many.call_args.args[0]
    agency_filter = query["$nor"][1]
    assert set(agency_filter["event_type"]["$in"]) == agency_webhook.AGENCY_OUTBOX_EVENT_TYPES
    assert agency_filter["last_error"]["$regex"] == module.AGENCY_CONFIGURATION_ERROR_PATTERN
    assert query["tenant_id"] == "hotel" and query["provider"] == "agency"
    counted = events.count_documents.call_args.args[0]
    assert counted["$or"] == query["$nor"]
    assert counted["tenant_id"] == "hotel" and counted["provider"] == "agency"
