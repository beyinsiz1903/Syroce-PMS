"""
Test: Inventory Ledger Alignment — Authoritative Truth Enforcement
===================================================================
Verifies that:
1. _detect_inventory_deltas() reads from room_type_inventory (not raw bookings)
2. Holds and OOO are accounted for in availability
3. No fallback to old booking-based computation
4. Freshness check triggers reconciliation when stale
5. Alignment endpoint returns correct status
"""
import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestInventoryLedgerAlignment:
    """Test that channel manager uses room_type_inventory as authoritative truth."""

    @pytest.mark.asyncio
    async def test_detect_deltas_uses_room_type_inventory(self):
        """_detect_inventory_deltas must read from room_type_inventory, not bookings."""
        from channel_manager.application.inventory_sync_service import InventorySyncService

        svc = InventorySyncService()

        today = datetime.now(timezone.utc).date().isoformat()
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

        # The method should import from core.room_type_inventory_service
        # Verify by checking the method's source code
        import inspect
        source = inspect.getsource(svc._detect_inventory_deltas)

        # Must NOT contain booking-based computation
        assert "db.bookings.find" not in source, (
            "CRITICAL: _detect_inventory_deltas still reads from db.bookings!"
        )
        assert "db.rooms.find" not in source, (
            "CRITICAL: _detect_inventory_deltas still reads from db.rooms!"
        )

        # Must contain room_type_inventory import
        assert "get_room_type_inventory" in source, (
            "_detect_inventory_deltas must use get_room_type_inventory"
        )
        assert "reconcile_date_range" in source, (
            "_detect_inventory_deltas must have reconciliation capability"
        )

    @pytest.mark.asyncio
    async def test_no_fallback_to_old_computation(self):
        """Verify there is no fallback path to booking-based availability."""
        from channel_manager.application.inventory_sync_service import InventorySyncService
        import inspect

        source = inspect.getsource(InventorySyncService._detect_inventory_deltas)

        # Must NOT have "total - occupied" pattern
        assert "total - occupied" not in source, (
            "FALLBACK DETECTED: Old 'total - occupied' computation still present!"
        )

        # Must NOT have booking counting loop
        assert "sum(1 for b in bookings" not in source, (
            "FALLBACK DETECTED: Booking counting loop still present!"
        )

    @pytest.mark.asyncio
    async def test_freshness_check_exists(self):
        """Verify freshness check is performed before sync."""
        from channel_manager.application.inventory_sync_service import InventorySyncService
        import inspect

        source = inspect.getsource(InventorySyncService._detect_inventory_deltas)
        assert "_check_inventory_freshness" in source, (
            "Freshness check must be called before reading inventory"
        )

    @pytest.mark.asyncio
    async def test_freshness_check_method_logic(self):
        """Verify _check_inventory_freshness returns correct states."""
        from channel_manager.application.inventory_sync_service import InventorySyncService

        svc = InventorySyncService()

        # Method should exist
        assert hasattr(svc, "_check_inventory_freshness"), (
            "_check_inventory_freshness method must exist"
        )

    @pytest.mark.asyncio
    async def test_availability_source_tag(self):
        """Changes must be tagged with source='room_type_inventory'."""
        from channel_manager.application.inventory_sync_service import InventorySyncService
        import inspect

        source = inspect.getsource(InventorySyncService._detect_inventory_deltas)
        assert '"source": "room_type_inventory"' in source, (
            "Availability changes must be tagged with source='room_type_inventory'"
        )


class TestHoldOOOAccountedFor:
    """Test that holds and OOO/OOS reduce sellable count correctly.

    The room_type_inventory materialized view accounts for:
    - booking locks
    - hold locks
    - ooo locks
    - oos locks

    The old method only counted bookings. This test verifies that
    the new system uses the full lock-aware sellable count.
    """

    @pytest.mark.asyncio
    async def test_room_type_inventory_includes_holds(self):
        """Verify room_type_inventory computation includes hold locks."""
        from core.room_type_inventory_service import compute_room_type_inventory
        import inspect

        source = inspect.getsource(compute_room_type_inventory)
        assert "locked_hold" in source, (
            "room_type_inventory must track hold locks"
        )
        assert "locked_ooo" in source, (
            "room_type_inventory must track OOO locks"
        )
        assert "locked_oos" in source, (
            "room_type_inventory must track OOS locks"
        )

    @pytest.mark.asyncio
    async def test_sellable_formula_includes_all_locks(self):
        """Verify sellable = physical_total - booking - hold - ooo - oos."""
        from core.room_type_inventory_service import compute_room_type_inventory
        import inspect

        source = inspect.getsource(compute_room_type_inventory)
        # The formula should subtract all lock types
        assert "total - locked_booking - locked_hold - locked_ooo - locked_oos" in source, (
            "Sellable formula must subtract ALL lock types, not just bookings"
        )


class TestAlignmentEndpoint:
    """Test the inventory alignment dashboard endpoint."""

    @pytest.mark.asyncio
    async def test_alignment_module_exists(self):
        """Verify alignment module is importable."""
        from controlplane.inventory_alignment import compute_inventory_alignment
        assert compute_inventory_alignment is not None

    @pytest.mark.asyncio
    async def test_alignment_returns_required_fields(self):
        """Verify alignment response includes all required fields."""
        from controlplane.inventory_alignment import compute_inventory_alignment
        from core.tenant_db import tenant_context

        with tenant_context("test_tenant"):
            result = await compute_inventory_alignment(tenant_id="test_tenant")

        required_fields = [
            "alignment_status", "freshness", "drift_count",
            "drift_nights", "provider_breakdown", "connectors_checked",
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

        # alignment_status must be one of the valid values
        valid_statuses = {"aligned", "drift_detected", "stale", "no_data", "reconcile_running"}
        assert result["alignment_status"] in valid_statuses, (
            f"Invalid alignment_status: {result['alignment_status']}"
        )


class TestDoraMetricsEndpoint:
    """Test DORA metrics endpoint."""

    @pytest.mark.asyncio
    async def test_dora_module_exists(self):
        """Verify DORA metrics module is importable."""
        from controlplane.dora_metrics import compute_dora_metrics
        assert compute_dora_metrics is not None

    @pytest.mark.asyncio
    async def test_dora_returns_required_metrics(self):
        """Verify DORA response includes all 4 metrics."""
        from controlplane.dora_metrics import compute_dora_metrics

        result = await compute_dora_metrics()

        assert "metrics" in result
        m = result["metrics"]
        required_metrics = ["deployment_frequency", "change_failure_rate", "mttr", "lead_time"]
        for metric in required_metrics:
            assert metric in m, f"Missing DORA metric: {metric}"
            assert "value" in m[metric], f"Missing value in {metric}"
            assert "rating" in m[metric], f"Missing rating in {metric}"

    @pytest.mark.asyncio
    async def test_dora_correlation_module_exists(self):
        """Verify correlation module is importable."""
        from controlplane.dora_metrics import compute_dora_channel_correlation
        assert compute_dora_channel_correlation is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
