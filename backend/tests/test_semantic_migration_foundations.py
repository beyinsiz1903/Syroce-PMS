from types import SimpleNamespace

from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.inventory.services.availability_read_service import AvailabilityReadService
from modules.reservations.services.reservation_read_service import ReservationReadService
from modules.stays.services.stay_read_service import StayReadService
from shared_kernel.event_envelope import build_event_envelope
from shared_kernel.idempotency import normalize_idempotency_key
from shared_kernel.tenancy_context import build_property_context, build_tenant_context
from tests.harnesses.contract import assert_required_keys, build_contract_snapshot
from tests.harnesses.tenant_isolation import TenantIsolationHarness


def test_shared_kernel_tenant_context_builds():
    user = SimpleNamespace(id="user-1", tenant_id="tenant-1", role="admin", property_id="property-1")
    tenant_ctx = build_tenant_context(user)
    property_ctx = build_property_context(user)

    assert tenant_ctx.tenant_id == "tenant-1"
    assert tenant_ctx.user_id == "user-1"
    assert property_ctx.property_id == "property-1"


def test_event_envelope_factory_produces_contract():
    envelope = build_event_envelope(
        event_type="reservation.created.v1",
        tenant_id="tenant-1",
        payload={"reservation_id": "res-1"},
        correlation_id="corr-1",
    )

    snapshot = build_contract_snapshot(envelope.model_dump())
    assert_required_keys(snapshot, ["event_id", "event_type", "tenant_id", "payload"])
    assert snapshot["event_type"] == "str"


def test_idempotency_key_normalization():
    assert normalize_idempotency_key("  key-123  ") == "key-123"
    assert normalize_idempotency_key("   ") is None


def test_read_services_are_importable():
    assert ReservationReadService is not None
    assert StayReadService is not None
    assert AvailabilityReadService is not None
    assert FolioBalanceReadService is not None


def test_tenant_isolation_harness_can_initialize():
    harness = TenantIsolationHarness(base_url="https://example.com/")
    assert harness.base_url == "https://example.com"
    headers = harness.build_headers("token-1", property_id="property-9")
    assert headers["Authorization"] == "Bearer token-1"
    assert headers["x-property-id"] == "property-9"