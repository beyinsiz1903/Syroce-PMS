"""Sandbox certification must retain the active connection's routing scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from domains.channel_manager.providers.exely import exely_router
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import (
    EXELY_TEST_ENDPOINT_URL,
    validate_exely_endpoint,
)

pytestmark = pytest.mark.exely_failure_stress


@pytest.fixture
def scoped_connection(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    connection = {"tenant_id": "tenant-a", "hotel_code": "501694", "mode": "sandbox"}
    collection = SimpleNamespace(find_one=AsyncMock(return_value=connection))
    reservations = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        count_documents=AsyncMock(return_value=0),
        find=lambda *args, **kwargs: SimpleNamespace(to_list=AsyncMock(return_value=[])),
    )
    monkeypatch.setattr(exely_router, "db", SimpleNamespace(
        exely_connections=collection,
        exely_reservations=reservations,
    ))
    monkeypatch.setattr(exely_router, "reservation_sync_block_reason", lambda: "")
    monkeypatch.setattr(exely_router, "resolve_exely_credentials", AsyncMock(return_value={
        "username": "synthetic-user", "password": "synthetic-password",
        "hotel_code": "501694", "endpoint_url": EXELY_TEST_ENDPOINT_URL,
    }))
    monkeypatch.setattr(exely_router, "log_sync", AsyncMock())
    return connection, collection


@pytest.mark.parametrize("operation", ["manual_pull", "general_verification"])
async def test_pull_entrypoints_forward_explicit_sandbox_scope(scoped_connection, monkeypatch, operation):
    async def pull(**kwargs):
        # Exercise the real production endpoint guard, without provider IO.
        validate_exely_endpoint(kwargs["endpoint_url"], connection_mode=kwargs.get("connection_mode", ""))
        return {"success": True, "processed": 0}

    scheduler = SimpleNamespace(pull_for_tenant=AsyncMock(side_effect=pull))
    monkeypatch.setattr(exely_router, "exely_pull_scheduler", scheduler)
    user = SimpleNamespace(tenant_id="tenant-a")

    if operation == "manual_pull":
        result = await exely_router.manual_pull(current_user=user, _perm=None)
        assert result["success"] is True
    else:
        result = await exely_router.verify_test_booking(
            exely_router.TestBookingVerifyRequest(), current_user=user, _perm=None,
        )
        assert result["errors"] == []
        assert result["pull_result"]["success"] is True

    kwargs = scheduler.pull_for_tenant.await_args.kwargs
    assert kwargs["connection_mode"] == "sandbox"
    assert kwargs["tenant_id"] == "tenant-a"
    assert kwargs["hotel_code"] == "501694"
    _, collection = scoped_connection
    assert collection.find_one.await_args.args[0] == {"tenant_id": "tenant-a", "is_active": True}


@pytest.mark.parametrize("mode", ["sandbox", "production", "", None])
async def test_id_verification_uses_saved_mode_and_ingests_only_matching_booking(scoped_connection, monkeypatch, mode):
    connection, _ = scoped_connection
    connection["mode"] = mode
    target = {"reservation_id": "synthetic-child-booking", "guest_name": "Synthetic Child QA", "status": "confirmed"}
    provider_read = AsyncMock(return_value=SimpleNamespace(success=True, data={"reservations": [
        {"reservation_id": "another-booking"}, target,
    ]}))
    constructed = []

    def provider_factory(**kwargs):
        # Do not mock away the endpoint/mode validation that failed live.
        provider = ExelyProvider(**kwargs)
        constructed.append(kwargs)
        provider.pull_reservations = provider_read
        return provider

    ingest = AsyncMock(return_value={"action": "queued"})
    monkeypatch.setattr(exely_router, "ExelyProvider", provider_factory)
    monkeypatch.setattr(exely_router, "ingest_reservation", ingest)
    scheduler = SimpleNamespace(pull_for_tenant=AsyncMock())
    monkeypatch.setattr(exely_router, "exely_pull_scheduler", scheduler)

    result = await exely_router.verify_test_booking(
        exely_router.TestBookingVerifyRequest(reservation_id="synthetic-child-booking"),
        current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None,
    )

    scheduler.pull_for_tenant.assert_not_awaited()
    if mode == "sandbox":
        assert result["verification_status"] == "found"
        assert result["errors"] == []
        provider_read.assert_awaited_once()
        ingest.assert_awaited_once()
        kwargs = constructed[0]
        assert kwargs["connection_mode"] == "sandbox"
        assert kwargs["tenant_id"] == "tenant-a"
        assert kwargs["property_id"] == "501694"
        assert kwargs["connection_id"] == "tenant-a:501694"
        assert ingest.await_args.kwargs["tenant_id"] == "tenant-a"
        assert ingest.await_args.kwargs["raw_payload"] == {**target, "property_id": "501694"}
    else:
        assert result["verification_status"] == "error"
        assert result["errors"] == ["ExelyValidationError"]
        provider_read.assert_not_awaited()
        ingest.assert_not_awaited()


@pytest.mark.parametrize("children,ages,acceptance", [(0, [], "mismatch"), (1, [6], "not_verified"), (1, [7], "mismatch"), (1, [], "mismatch")])
async def test_existing_acked_booking_compares_counts_without_reimport_or_provider_io(scoped_connection, monkeypatch, children, ages, acceptance):
    stored = {
        "external_id": "synthetic-child-booking", "pms_status": "imported",
        "delivery_confirmed": True, "state": "confirmed",
        "rooms": [{"adults": 2 if children else 3, "children": children, "children_ages": ages}],
    }
    collection = exely_router.db.exely_reservations
    collection.find_one.return_value = stored
    provider = AsyncMock()
    ingest = AsyncMock()
    monkeypatch.setattr(exely_router, "ExelyProvider", provider)
    monkeypatch.setattr(exely_router, "ingest_reservation", ingest)
    result = await exely_router.verify_test_booking(
        exely_router.TestBookingVerifyRequest(reservation_id="synthetic-child-booking", expected_adults=2, expected_children_ages=[6]),
        current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None,
    )
    assert result["verification_status"] == "found"
    assert result["lookup_source"] == "stored"
    assert result["acceptance_status"] == acceptance
    assert result["new_count"] == 0
    checks = result["new_reservations"][0]["checks"]
    assert checks["pms_import"] == checks["provider_ack"] == "passed"
    assert checks["guest_demographics"] == "not_verified"
    scope = {"tenant_id": "tenant-a", "property_id": "501694", "external_id": "synthetic-child-booking"}
    assert collection.find_one.await_args.args[0] == scope
    for call in collection.count_documents.await_args_list:
        assert call.args[0] == scope
    provider.assert_not_called()
    ingest.assert_not_awaited()
    exely_router.resolve_exely_credentials.assert_not_awaited()


def test_multiroom_counts_cannot_be_aggregated_into_an_ambiguous_single_room_match():
    request = exely_router.TestBookingVerifyRequest(reservation_id="synthetic", expected_adults=2, expected_children_ages=[6])
    result = exely_router._test_booking_summary({"rooms": [
        {"adults": 2, "children": 1, "children_ages": [6]},
        {"adults": 2, "children": 1, "children_ages": [6]},
    ]}, request)
    assert result["acceptance_status"] == "mismatch"


@pytest.mark.parametrize("payload", [
    {"expected_adults": 2, "expected_children_ages": [6]},
    {"reservation_id": "synthetic", "expected_adults": 2},
    {"reservation_id": "synthetic", "expected_children_ages": [6]},
    {"reservation_id": "synthetic", "expected_adults": True, "expected_children_ages": [6]},
    {"reservation_id": "synthetic", "expected_adults": 2, "expected_children_ages": [6.5]},
    {"reservation_id": "synthetic", "expected_adults": 2, "expected_children_ages": [18]},
])
def test_expectations_require_an_exact_id_and_strict_completed_ages(payload):
    with pytest.raises(ValidationError):
        exely_router.TestBookingVerifyRequest(**payload)


async def test_failed_general_pull_is_not_reported_as_not_found(scoped_connection, monkeypatch):
    monkeypatch.setattr(exely_router, "exely_pull_scheduler", SimpleNamespace(
        pull_for_tenant=AsyncMock(return_value={"success": False, "error": "Unavailable"}),
    ))
    result = await exely_router.verify_test_booking(exely_router.TestBookingVerifyRequest(), current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None)
    assert result["verification_status"] == "error"


@pytest.mark.parametrize("operation", ["_test_exely_connection", "_validate_exely"])
@pytest.mark.parametrize("saved_mode", ["sandbox", "production", ""])
async def test_shared_config_uses_only_active_saved_property_mode(monkeypatch, operation, saved_mode):
    from domains.channel_manager import provider_config_router as config
    from domains.channel_manager.providers.exely.errors import ExelyValidationError

    monkeypatch.setenv("APP_ENV", "production")
    collection = SimpleNamespace(find_one=AsyncMock(return_value={"mode": saved_mode} if saved_mode else None))
    monkeypatch.setattr(config, "db", SimpleNamespace(exely_connections=collection))
    fake = SimpleNamespace(
        success=True, data={"connected": True, "room_types": [], "rate_plans": [], "reservations": []}, duration_ms=1,
    )
    provider_read = AsyncMock(return_value=fake)
    original = ExelyProvider.__init__

    def init(self, **kwargs):
        original(self, **kwargs)
        self.test_connection = provider_read
        self.discover_rooms = provider_read
        self.pull_reservations = provider_read

    monkeypatch.setattr(ExelyProvider, "__init__", init)
    credentials = {
        "username": "synthetic", "password": "synthetic", "hotel_code": "501694",
        "endpoint_url": EXELY_TEST_ENDPOINT_URL, "connection_mode": "sandbox", "mode": "sandbox",
    }
    if saved_mode == "sandbox":
        await getattr(config, operation)(credentials, "tenant-a")
        assert provider_read.await_count >= 1
    else:
        with pytest.raises(ExelyValidationError):
            await getattr(config, operation)(credentials, "tenant-a")
        provider_read.assert_not_awaited()
    assert collection.find_one.await_args.args[0] == {"tenant_id": "tenant-a", "hotel_code": "501694", "is_active": True}
