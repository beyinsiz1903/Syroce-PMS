"""Offline tenant-control, request preflight, and scheduler-isolation regressions."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_current_tenant_id
from domains.channel_manager.providers.exely import ari_publish, exely_pull_worker, exely_router
from domains.channel_manager.providers.exely.errors import ExelyValidationError
from domains.channel_manager.providers.exely.exely_pull_worker import ExelyPullScheduler
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.scheduling import connection_pull_interval_seconds


def user():
    return SimpleNamespace(tenant_id="tenant-a", name="Synthetic Operator", id="user-a")


@pytest.fixture
def controls(monkeypatch):
    connection = {"tenant_id": "tenant-a", "auto_sync_reservations": False, "sync_interval_minutes": 15}
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value=connection),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1, modified_count=0)),
    )
    db = SimpleNamespace(
        exely_connections=collection,
        exely_pull_cursors=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        exely_raw_events=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
        exely_reservations=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
    )
    scheduler = SimpleNamespace(is_running=True, start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(exely_router, "db", db)
    monkeypatch.setattr(exely_router, "exely_pull_scheduler", scheduler)
    monkeypatch.setattr(exely_router, "log_sync", AsyncMock())
    monkeypatch.setattr(exely_router, "reservation_sync_block_reason", lambda: "")
    return collection, scheduler


@pytest.mark.parametrize("enabled", [True, False])
async def test_sync_start_stop_persists_only_the_requesting_tenant(controls, enabled):
    collection, scheduler = controls
    endpoint = exely_router.start_scheduler if enabled else exely_router.stop_scheduler
    result = await endpoint(current_user=user(), _perm=None)
    query, update = collection.update_one.await_args.args
    assert query == {"tenant_id": "tenant-a", "is_active": True}
    assert update["$set"]["auto_sync_reservations"] is enabled
    assert result["reservation_sync_enabled"] is enabled
    scheduler.start.assert_not_awaited()
    scheduler.stop.assert_not_awaited()


async def test_stop_is_available_during_global_kill_switch(controls, monkeypatch):
    monkeypatch.setattr(exely_router, "reservation_sync_block_reason", lambda: "EXELY_PRODUCTION_DISABLED")
    result = await exely_router.stop_scheduler(current_user=user(), _perm=None)
    assert result["reservation_sync_enabled"] is False
    with pytest.raises(HTTPException) as error:
        await exely_router.start_scheduler(current_user=user(), _perm=None)
    assert error.value.status_code == 503


@pytest.mark.parametrize("endpoint", [exely_router.start_scheduler, exely_router.stop_scheduler])
async def test_sync_controls_fail_if_no_active_connection(controls, endpoint):
    collection, _ = controls
    collection.update_one.return_value = SimpleNamespace(matched_count=0)
    with pytest.raises(HTTPException) as error:
        await endpoint(current_user=user(), _perm=None)
    assert error.value.status_code == 404


async def test_interval_settings_are_tenant_scoped_and_never_start_provider_io(controls):
    collection, scheduler = controls
    result = await exely_router.update_sync_settings(exely_router.ExelySyncSettings(sync_interval_minutes=7), current_user=user(), _perm=None)
    query, update = collection.update_one.await_args.args
    assert query == {"tenant_id": "tenant-a", "is_active": True}
    assert update["$set"]["sync_interval_minutes"] == 7
    assert "auto_sync_reservations" not in update["$set"]
    assert result["sync_interval_minutes"] == 7
    scheduler.start.assert_not_awaited()


@pytest.mark.parametrize("minutes", [0, 1, 2, 61, -1, True, 3.5, "15"])
def test_interval_input_is_bounded_without_coercion(minutes):
    with pytest.raises(ValidationError):
        exely_router.ExelySyncSettings(sync_interval_minutes=minutes)


async def test_status_does_not_confuse_global_worker_with_tenant_enablement(controls):
    result = await exely_router.get_sync_status(current_user=user())
    assert result["scheduler_running"] is True
    assert result["reservation_sync_enabled"] is False
    assert result["sync_interval_seconds"] == 900
    assert result["total_reservations"] == 0


async def test_reapplying_same_currency_is_successful_not_a_false_404(controls):
    result = await exely_router.update_currency(exely_router.CurrencyUpdateRequest(currency="TRY"), current_user=user(), _perm=None)
    assert result["currency"] == "TRY"


@pytest.mark.parametrize(("connection", "seconds"), [
    ({"sync_interval_minutes": 15, "sync_interval_seconds": 60}, 900),
    ({"sync_interval_minutes": 3}, 180),
    ({"sync_interval_seconds": 420}, 420),
    ({"sync_interval_minutes": "invalid"}, 900),
    ({"sync_interval_minutes": True}, 900),
    ({"sync_interval_seconds": 1}, 180),
    ({"sync_interval_minutes": 100000}, 3600),
    ({}, 900),
])
def test_saved_interval_has_one_bounded_interpretation(connection, seconds):
    assert connection_pull_interval_seconds(connection) == seconds


async def test_scheduler_streams_more_than_100_connections_and_uses_each_interval(monkeypatch):
    async def cursor():
        for index in range(125):
            yield {"tenant_id": f"tenant-{index}", "sync_interval_minutes": 3 if index == 0 else 15}

    find_calls = []
    def find(query, projection):
        find_calls.append(query)
        return cursor()

    monkeypatch.setattr(exely_pull_worker, "reservation_sync_block_reason", lambda: "")
    monkeypatch.setattr(exely_pull_worker, "db", SimpleNamespace(exely_connections=SimpleNamespace(find=find)))
    monkeypatch.setattr(exely_pull_worker, "resolve_exely_credentials", AsyncMock(return_value={
        "username": "synthetic-user", "password": "synthetic-password", "hotel_code": "synthetic-property", "endpoint_url": "https://example.invalid",
    }))
    scheduler = ExelyPullScheduler()
    scheduler._acquire_tenant_lease = AsyncMock(return_value=True)
    scheduler.pull_for_tenant = AsyncMock()
    await scheduler._pull_all_tenants(5)
    assert find_calls == [{"is_active": True, "auto_sync_reservations": True}]
    assert scheduler.pull_for_tenant.await_count == 125
    assert scheduler._acquire_tenant_lease.await_args_list[0].args == ("tenant-0", 180)
    assert scheduler._acquire_tenant_lease.await_args_list[-1].args == ("tenant-124", 900)
    assert get_current_tenant_id() is None


async def test_lease_owner_cannot_bypass_its_own_saved_interval(monkeypatch):
    stored = {}
    async def claim(query, update, **kwargs):
        def matches(branch):
            if "owner_token" in branch:
                return stored.get("owner_token") == branch["owner_token"]
            condition = branch.get("lease_expires_at", {})
            if "$lte" in condition:
                return stored.get("lease_expires_at", 0) <= condition["$lte"]
            return condition.get("$exists") is False and "lease_expires_at" not in stored

        if stored and not any(matches(branch) for branch in query["$or"]):
            raise DuplicateKeyError("tenant lease already exists")
        stored.update(update["$set"])
        return stored.copy()

    monkeypatch.setattr(exely_pull_worker, "db", SimpleNamespace(exely_scheduler_leases=SimpleNamespace(find_one_and_update=claim)))
    scheduler = ExelyPullScheduler()
    before = datetime.now(UTC).timestamp()
    assert await scheduler._acquire_tenant_lease("tenant-a", 900) is True
    assert stored["lease_expires_at"] >= before + 900
    assert await scheduler._acquire_tenant_lease("tenant-a", 900) is False
    scheduler._lease_owner = "other-replica"
    assert await scheduler._acquire_tenant_lease("tenant-a", 900) is False
    stored["lease_expires_at"] = before - 1
    assert await scheduler._acquire_tenant_lease("tenant-a", 900) is True


ARI_BASE = {"room_type_code": "STD", "rate_plan_code": "BAR", "start_date": "2030-01-01", "end_date": "2030-01-02"}


@pytest.mark.parametrize("changes", [
    {"rate_amount": -1}, {"rate_amount": float("nan")}, {"rate_amount": float("inf")},
    {"rate_amount": 100, "currency": "usd"}, {"availability": -1}, {"availability": True},
    {"min_stay": 0}, {"cta": "false"}, {"availability": 2, "end_date": "2029-12-31"},
    {"availability": 2, "start_date": "2030-02-30"}, {"availability": 2, "room_type_code": " "}, {},
])
def test_invalid_ari_requests_are_rejected_before_handler(changes):
    with pytest.raises(ValidationError):
        exely_router.ExelyARIUpdate(**{**ARI_BASE, **changes})


def test_whole_bulk_request_is_validated_before_any_queue_write(monkeypatch):
    import inspect
    app = FastAPI()
    app.include_router(exely_router.router)
    app.dependency_overrides[exely_router.get_current_user] = user
    permission = inspect.signature(exely_router.bulk_push_ari).parameters["_perm"].default.dependency
    app.dependency_overrides[permission] = lambda: None
    enqueue = AsyncMock()
    monkeypatch.setattr(exely_router, "enqueue_exely_ari_update", enqueue)
    with TestClient(app) as client:
        response = client.post("/api/channel-manager/exely/ari/bulk-push", json=[
            {**ARI_BASE, "availability": 2}, {**ARI_BASE, "rate_amount": -1},
        ])
        assert response.status_code == 422
        assert client.post("/api/channel-manager/exely/ari/bulk-push", json=[]).status_code == 422
    enqueue.assert_not_awaited()


async def test_internal_mixed_ari_preflight_does_not_queue_valid_sibling_of_invalid_rate(monkeypatch):
    publish = AsyncMock()
    monkeypatch.setattr(ari_publish, "publish_ari_event", publish)
    monkeypatch.setattr(ari_publish, "ari_write_block_reason", lambda: "")
    result = await ari_publish.enqueue_exely_ari_update("tenant-a", "hotel-a", **ARI_BASE, source_service="test", availability=2, rate_amount=-1)
    assert result["accepted"] is False
    assert result["error_code"] == "EXELY_ARI_RATE_INVALID"
    assert result["queued_operation_count"] == 0
    publish.assert_not_awaited()


@pytest.mark.parametrize(("operation", "value"), [("rate", float("nan")), ("rate", -1), ("availability", -1), ("cta", "false"), ("min_los", 0)])
async def test_low_level_provider_rejects_bad_single_mutation_without_network(operation, value):
    provider = ExelyProvider(username="synthetic-user", password="synthetic-password", hotel_code="synthetic-hotel")
    provider._transport.send_soap = AsyncMock()
    with pytest.raises(ExelyValidationError):
        await provider.push_ari_operation(operation=operation, value=value, **ARI_BASE)
    provider._transport.send_soap.assert_not_awaited()


@pytest.mark.parametrize("start", ["2030-1-1", "20300101", "2030-01-01T00:00:00", "2030-02-30"])
async def test_internal_date_preflight_matches_the_queue_iso_date_contract(monkeypatch, start):
    publish = AsyncMock()
    monkeypatch.setattr(ari_publish, "publish_ari_event", publish)
    monkeypatch.setattr(ari_publish, "ari_write_block_reason", lambda: "")
    result = await ari_publish.enqueue_exely_ari_update("tenant-a", "hotel-a", **{**ARI_BASE, "start_date": start}, source_service="test", availability=2)
    assert result["error_code"] == "EXELY_ARI_DATE_FORMAT_INVALID"
    publish.assert_not_awaited()


async def test_zero_availability_and_false_restrictions_are_real_operations(monkeypatch):
    publish = AsyncMock()
    monkeypatch.setattr(ari_publish, "publish_ari_event", publish)
    monkeypatch.setattr(ari_publish, "ari_write_block_reason", lambda: "")
    result = await ari_publish.enqueue_exely_ari_update("tenant-a", "hotel-a", **ARI_BASE, source_service="test", availability=0, stop_sell=False, cta=False)
    assert result["accepted"] is True
    assert result["queued_operation_count"] == 3
    assert publish.await_count == 3


@pytest.fixture
async def local_mongo(monkeypatch):
    uri = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    if urlsplit(uri).hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Exely scheduler acceptance requires an isolated local MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    name = "exely_scheduler_acceptance_" + uuid.uuid4().hex
    database = client[name]
    try:
        await database.exely_scheduler_leases.create_index("tenant_id", unique=True)
        yield database
    finally:
        await client.drop_database(name)
        client.close()


@pytest.mark.live_mongo
async def test_real_mongo_tenant_stop_never_stops_another_hotel(local_mongo, monkeypatch):
    await local_mongo.exely_connections.insert_many([
        {"tenant_id": "tenant-a", "is_active": True, "auto_sync_reservations": True},
        {"tenant_id": "tenant-b", "is_active": True, "auto_sync_reservations": True},
    ])
    scheduler = SimpleNamespace(stop=AsyncMock(), start=AsyncMock())
    monkeypatch.setattr(exely_router, "db", local_mongo)
    monkeypatch.setattr(exely_router, "exely_pull_scheduler", scheduler)
    monkeypatch.setattr(exely_router, "log_sync", AsyncMock())
    await exely_router.stop_scheduler(current_user=user(), _perm=None)
    assert (await local_mongo.exely_connections.find_one({"tenant_id": "tenant-a"}))["auto_sync_reservations"] is False
    assert (await local_mongo.exely_connections.find_one({"tenant_id": "tenant-b"}))["auto_sync_reservations"] is True
    scheduler.stop.assert_not_awaited()


@pytest.mark.live_mongo
async def test_real_mongo_replicas_and_same_owner_respect_the_tenant_interval(local_mongo, monkeypatch):
    monkeypatch.setattr(exely_pull_worker, "db", local_mongo)
    schedulers = [ExelyPullScheduler() for _ in range(12)]
    results = await asyncio.gather(*(scheduler._acquire_tenant_lease("tenant-a", 900) for scheduler in schedulers))
    assert sum(results) == 1
    winner = schedulers[results.index(True)]
    assert await winner._acquire_tenant_lease("tenant-a", 900) is False
    assert await winner._acquire_tenant_lease("tenant-b", 180) is True
    await local_mongo.exely_scheduler_leases.update_one({"tenant_id": "tenant-a"}, {"$set": {"lease_expires_at": 0}})
    assert await winner._acquire_tenant_lease("tenant-a", 900) is True
    assert await local_mongo.exely_scheduler_leases.count_documents({"tenant_id": "tenant-a"}) == 1
