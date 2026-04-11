"""
Tests for Phase 5 hardening:
- FrontdeskServiceV2 (room move, late checkout, no-show, walk-in, concurrency)
- PosFnbServiceV2 (order lifecycle, void, stock race, table reserve)
- Alert Enrichment Engine
- Incident Response Service
- Provider Validation
- Tenant Isolation Validation
- Pilot Readiness
"""
import os
import pytest
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)
import uuid


# ── FrontdeskServiceV2 Tests ──────────────────────────────────────

class TestFrontdeskServiceV2:
    """Tests for production-grade front desk operations."""

    @pytest.fixture
    def service(self):
        from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2
        svc = FrontdeskServiceV2()
        return svc

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_email="test@hotel.com",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_checkin_not_found(self, service, ctx):
        result = await service.checkin(ctx, "nonexistent-booking-id")
        assert not result.ok
        assert result.code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_walk_in_creates_booking_and_folio(self, service, ctx):
        # First create a room
        room_id = str(uuid.uuid4())
        await service._db.rooms.insert_one({
            "id": room_id,
            "tenant_id": ctx.tenant_id,
            "room_number": "901",
            "status": "available",
            "room_type": "standard",
        })
        try:
            result = await service.walk_in(
                ctx, guest_name="Walk-In Guest", room_id=room_id,
                nights=2, rate_amount=100.0
            )
            assert result.ok
            assert result.data["booking_id"]
            assert result.data["guest_id"]
            assert result.data["folio_id"]
            assert result.data["room_number"] == "901"
        finally:
            await service._db.rooms.delete_one({"id": room_id})
            if result.ok:
                await service._db.bookings.delete_one({"id": result.data["booking_id"]})
                await service._db.guests.delete_one({"id": result.data["guest_id"]})
                await service._db.folios.delete_one({"id": result.data["folio_id"]})

    @pytest.mark.asyncio
    async def test_room_move_requires_reason(self, service, ctx):
        result = await service.room_move(ctx, "any-booking", "any-room", reason="")
        # @audited with require_reason should block if no reason
        # The reason="" should trigger REASON_REQUIRED
        assert not result.ok
        assert result.code == "REASON_REQUIRED"

    @pytest.mark.asyncio
    async def test_late_checkout_requires_reason(self, service, ctx):
        result = await service.late_checkout(ctx, "any-booking", "2026-03-15", reason="")
        assert not result.ok
        assert result.code == "REASON_REQUIRED"

    @pytest.mark.asyncio
    async def test_void_charge_requires_permission(self, service, ctx):
        # Create a low-permission context
        from common.context import OperationContext
        low_ctx = OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-low",
            actor_role="receptionist",
        )
        result = await service.void_charge(low_ctx, "any-charge", reason="test")
        assert not result.ok
        assert result.code == "FORBIDDEN"


# ── PosFnbServiceV2 Tests ──────────────────────────────────────

class TestPosFnbServiceV2:
    """Tests for production-grade POS operations."""

    @pytest.fixture
    def service(self):
        from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2
        return PosFnbServiceV2()

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_email="test@hotel.com",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_create_order_requires_items(self, service, ctx):
        result = await service.create_order(ctx, "outlet-1", items=[])
        assert not result.ok
        assert result.code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_order_success(self, service, ctx):
        items = [{"name": "Burger", "price": 50.0, "quantity": 2}]
        result = await service.create_order(ctx, "outlet-1", items=items, guest_name="Test Guest")
        assert result.ok
        assert result.data["order_id"]
        assert result.data["grand_total"] == 110.0  # 100 + 10% tax
        # Cleanup
        await service._db.pos_orders.delete_one({"id": result.data["order_id"]})
        await service._db.kitchen_orders.delete_many({"order_id": result.data["order_id"]})

    @pytest.mark.asyncio
    async def test_void_order_requires_permission(self, service, ctx):
        from common.context import OperationContext
        low_ctx = OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-low",
            actor_role="waiter",
        )
        result = await service.void_order(low_ctx, "any-order", reason="test")
        assert not result.ok
        assert result.code == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_stock_adjust_negative_fails(self, service, ctx):
        result = await service.adjust_stock(ctx, "prod-1", "in", -5, "test")
        assert not result.ok
        assert result.code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_stock_adjust_invalid_type(self, service, ctx):
        result = await service.adjust_stock(ctx, "prod-1", "invalid", 5, "test")
        assert not result.ok
        assert result.code == "VALIDATION_ERROR"


# ── Alert Enrichment Tests ──────────────────────────────────────

class TestAlertEnrichment:
    """Tests for alert enrichment engine."""

    @pytest.fixture
    def engine(self):
        from modules.observability.alert_enrichment import AlertEnrichmentEngine
        return AlertEnrichmentEngine()

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_evaluate_no_metrics(self, engine, ctx):
        result = await engine.evaluate_all_rules(ctx, {})
        assert result.ok
        assert result.data["alerts_fired"] == 0

    @pytest.mark.asyncio
    async def test_evaluate_fires_on_threshold(self, engine, ctx):
        metrics = {"pending_count": 1000}  # Exceeds 500 threshold
        result = await engine.evaluate_all_rules(ctx, metrics)
        assert result.ok
        assert result.data["alerts_fired"] > 0
        alert = result.data["alerts"][0]
        assert alert["severity"] == "high"
        assert alert["blast_radius"] == "platform"
        # Cleanup
        for a in result.data["alerts"]:
            await engine._db.alert_events.delete_one({"id": a["id"]})

    def test_get_rules_returns_all(self, engine):
        rules = engine.get_rules()
        assert len(rules) == 15
        assert all("rule_id" in r for r in rules)


# ── Incident Response Tests ──────────────────────────────────────

class TestIncidentResponse:
    """Tests for incident lifecycle."""

    @pytest.fixture
    def service(self):
        from modules.incident.incident_service import IncidentResponseService
        return IncidentResponseService()

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_incident_lifecycle(self, service, ctx):
        # Create
        result = await service.create_incident(
            ctx, title="Test Incident", description="Testing lifecycle", severity="P3"
        )
        assert result.ok
        inc_id = result.data["incident_id"]

        try:
            # Acknowledge
            ack_result = await service.acknowledge_incident(ctx, inc_id)
            assert ack_result.ok

            # Resolve
            resolve_result = await service.resolve_incident(ctx, inc_id, "Fixed")
            assert resolve_result.ok

            # List
            list_result = await service.list_incidents(ctx)
            assert list_result.ok
        finally:
            await service._db.incidents.delete_one({"id": inc_id})

    @pytest.mark.asyncio
    async def test_service_health_matrix(self, service, ctx):
        result = await service.get_service_health_matrix(ctx)
        assert result.ok
        assert "services" in result.data
        assert "overall_status" in result.data


# ── Tenant Isolation Tests ──────────────────────────────────────

class TestTenantIsolation:
    """Tests for tenant isolation validation."""

    @pytest.fixture
    def service(self):
        from security.tenant_isolation_service import TenantIsolationService
        return TenantIsolationService()

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_isolation_validation_returns_score(self, service, ctx):
        result = await service.run_isolation_validation(ctx)
        assert result.ok
        assert "score" in result.data
        assert "checks" in result.data
        assert result.data["score"] >= 0

    @pytest.mark.asyncio
    async def test_noisy_tenant_detection(self, service, ctx):
        result = await service.detect_noisy_tenants(ctx, window_minutes=60)
        assert result.ok
        assert "noisy_tenants" in result.data
        assert "noisy_count" in result.data


# ── Pilot Readiness Tests ──────────────────────────────────────

class TestPilotReadiness:
    """Tests for pilot readiness checks."""

    @pytest.fixture
    def service(self):
        from ops.pilot_readiness import PilotReadinessService
        return PilotReadinessService()

    @pytest.fixture
    def ctx(self):
        from common.context import OperationContext
        return OperationContext(
            tenant_id="test-tenant-001",
            actor_id="test-user-001",
            actor_role="admin",
        )

    @pytest.mark.asyncio
    async def test_readiness_check_returns_score(self, service, ctx):
        result = await service.run_readiness_check(ctx)
        assert result.ok
        assert "score" in result.data
        assert "checklist" in result.data
        assert "ready_for_pilot" in result.data

    @pytest.mark.asyncio
    async def test_feature_toggles(self, service, ctx):
        result = await service.get_feature_toggles(ctx)
        assert result.ok
        assert "toggles" in result.data
        assert len(result.data["toggles"]) > 0

    @pytest.mark.asyncio
    async def test_sign_off_check(self, service, ctx):
        result = await service.sign_off_check(ctx, "pms_checkin_flow", notes="Verified")
        assert result.ok
        assert result.data["signed_off"]
        # Cleanup
        await service._db.pilot_signoffs.delete_one({"check_id": "pms_checkin_flow", "tenant_id": ctx.tenant_id})
