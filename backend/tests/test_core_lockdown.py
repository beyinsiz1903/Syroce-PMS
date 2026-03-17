"""
Core Lockdown Regression Tests
===============================

Minimum safety net for P1 lockdown:
  1. Duplicate reservation event → no-op
  2. Out-of-order cancel/modify → stale rejection
  3. Unmapped room → hard fail (PENDING_MAPPING)
  4. Retryable provider error classification
  5. Stale event rejection
  6. Same reservation concurrent processing
  7. Canonical state transitions
  8. Provider capability matrix
  9. Reconciliation truth table
"""
import asyncio
import json
import hashlib
from datetime import datetime, timezone

import pytest

# ── 1. Decision Engine Tests ──────────────────────────────────────

from domains.channel_manager.ingest.decision_engine import (
    decide, detect_mutation_type, IngestDecision,
)
from domains.channel_manager.data_model import (
    ReservationState, MutationType, STATE_TRANSITIONS, is_valid_transition,
    ErrorClass, DriftType, DriftResolution, MappingFailure,
)


class TestDecisionEngine:
    """Tests for the core decision engine logic."""

    def _canonical(self, **overrides):
        base = {
            "external_reservation_id": "EXT-001",
            "check_in": "2026-04-01",
            "check_out": "2026-04-05",
            "room_type_code": "DBL",
            "rate_plan_code": "STD",
            "adults": 2,
            "children": 0,
            "total_amount": 500.0,
            "currency": "TRY",
            "guest_name": "Test Guest",
            "guest_email": "test@test.com",
            "guest_phone": "+905551234567",
            "status": "confirmed",
            "provider_last_modified_at": "2026-03-17T10:00:00",
        }
        base.update(overrides)
        return base

    def _room_mapping(self, active=True, valid=True, has_pms_id=True):
        return {
            "is_active": active,
            "validation_status": "valid" if valid else "invalid",
            "pms_room_type_id": "room_123" if has_pms_id else "",
        }

    def _rate_mapping(self, active=True, valid=True, has_pms_id=True):
        return {
            "is_active": active,
            "validation_status": "valid" if valid else "invalid",
            "pms_rate_plan_id": "rate_456" if has_pms_id else "",
        }

    def _lineage(self, **overrides):
        base = {
            "external_reservation_id": "EXT-001",
            "payload_hash": "existing_hash",
            "provider_version": "2026-03-17T08:00:00",
            "status": "confirmed",
            "currency": "TRY",
            "total_amount": 500.0,
            "arrival_date": "2026-04-01",
            "departure_date": "2026-04-05",
            "room_type_code": "DBL",
            "rate_plan_code": "STD",
            "guest_name": "Test Guest",
            "guest_email": "test@test.com",
            "guest_phone": "+905551234567",
            "provider_last_modified": "2026-03-17T08:00:00",
            "version": 1,
            "decision_version": 1,
        }
        base.update(overrides)
        return base

    # ── Test 1: New reservation → CREATE ─────────────────────────
    def test_new_reservation_creates(self):
        canonical = self._canonical()
        decision, reason = decide(
            canonical, None,
            self._room_mapping(), self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.CREATE
        assert "New reservation" in reason

    # ── Test 2: Same hash → SKIP (duplicate) ─────────────────────
    def test_duplicate_payload_skip(self):
        canonical = self._canonical()
        existing = self._lineage(payload_hash="same_hash")
        decision, reason = decide(
            canonical, existing,
            self._room_mapping(), self._rate_mapping(),
            "same_hash",
        )
        assert decision == IngestDecision.SKIP
        assert "Same payload" in reason

    # ── Test 3: Stale version → SKIP ─────────────────────────────
    def test_stale_version_skip(self):
        canonical = self._canonical(
            provider_last_modified_at="2026-03-17T06:00:00",
        )
        existing = self._lineage(
            provider_last_modified="2026-03-17T08:00:00",
        )
        decision, reason = decide(
            canonical, existing,
            self._room_mapping(), self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.SKIP
        assert "Stale" in reason

    # ── Test 4: Cancellation always wins ─────────────────────────
    def test_cancellation_always_wins(self):
        canonical = self._canonical(status="cancelled")
        existing = self._lineage(status="confirmed")
        decision, reason = decide(
            canonical, existing,
            self._room_mapping(), self._rate_mapping(),
            "cancel_hash",
        )
        assert decision == IngestDecision.CANCEL

    # ── Test 5: Cancellation without existing → CANCEL + case ────
    def test_cancellation_without_existing(self):
        canonical = self._canonical(status="cancelled")
        decision, reason = decide(
            canonical, None,
            self._room_mapping(), self._rate_mapping(),
            "cancel_hash",
        )
        assert decision == IngestDecision.CANCEL

    # ── Test 6: Unmapped room → HARD FAIL ────────────────────────
    def test_unmapped_room_hard_fail(self):
        canonical = self._canonical()
        decision, reason = decide(
            canonical, None,
            None,  # No room mapping
            self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.PENDING_MAPPING
        assert "unmapped" in reason.lower()

    # ── Test 7: Inactive room mapping → HARD FAIL ────────────────
    def test_inactive_room_mapping_hard_fail(self):
        canonical = self._canonical()
        decision, reason = decide(
            canonical, None,
            self._room_mapping(active=False),
            self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.PENDING_MAPPING
        assert "inactive" in reason.lower()

    # ── Test 8: Unmapped rate plan → HARD FAIL ───────────────────
    def test_unmapped_rate_plan_hard_fail(self):
        canonical = self._canonical()
        decision, reason = decide(
            canonical, None,
            self._room_mapping(),
            None,  # No rate mapping
            "new_hash",
        )
        assert decision == IngestDecision.PENDING_MAPPING
        assert "unmapped" in reason.lower()

    # ── Test 9: Amount anomaly → MANUAL_REVIEW ───────────────────
    def test_amount_anomaly_manual_review(self):
        canonical = self._canonical(total_amount=5000.0)
        existing = self._lineage(total_amount=500.0)
        decision, reason = decide(
            canonical, existing,
            self._room_mapping(), self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.MANUAL_REVIEW
        assert "Amount anomaly" in reason

    # ── Test 10: Normal update → UPDATE ──────────────────────────
    def test_normal_update(self):
        canonical = self._canonical(total_amount=550.0)
        existing = self._lineage(total_amount=500.0)
        decision, reason = decide(
            canonical, existing,
            self._room_mapping(), self._rate_mapping(),
            "new_hash",
        )
        assert decision == IngestDecision.UPDATE


class TestMutationDetection:
    """Tests for mutation type classification."""

    def _canonical(self, **overrides):
        base = {
            "external_reservation_id": "EXT-001",
            "check_in": "2026-04-01",
            "check_out": "2026-04-05",
            "room_type_code": "DBL",
            "rate_plan_code": "STD",
            "total_amount": 500.0,
            "guest_name": "Test Guest",
            "guest_email": "test@test.com",
            "guest_phone": "+905551234567",
            "status": "confirmed",
        }
        base.update(overrides)
        return base

    def _lineage(self, **overrides):
        base = {
            "arrival_date": "2026-04-01",
            "departure_date": "2026-04-05",
            "room_type_code": "DBL",
            "rate_plan_code": "STD",
            "total_amount": 500.0,
            "guest_name": "Test Guest",
            "guest_email": "test@test.com",
            "guest_phone": "+905551234567",
            "status": "confirmed",
        }
        base.update(overrides)
        return base

    def test_new_booking(self):
        assert detect_mutation_type(self._canonical(), None) == MutationType.NEW_BOOKING

    def test_cancellation(self):
        assert detect_mutation_type(
            self._canonical(status="cancelled"),
            self._lineage(),
        ) == MutationType.CANCELLATION

    def test_reinstatement(self):
        assert detect_mutation_type(
            self._canonical(status="confirmed"),
            self._lineage(status="cancelled"),
        ) == MutationType.REINSTATEMENT

    def test_date_change(self):
        assert detect_mutation_type(
            self._canonical(check_in="2026-04-02"),
            self._lineage(),
        ) == MutationType.DATE_CHANGE

    def test_room_type_change(self):
        assert detect_mutation_type(
            self._canonical(room_type_code="SGL"),
            self._lineage(),
        ) == MutationType.ROOM_TYPE_CHANGE

    def test_rate_change(self):
        assert detect_mutation_type(
            self._canonical(rate_plan_code="PROMO"),
            self._lineage(),
        ) == MutationType.RATE_CHANGE

    def test_guest_detail_change(self):
        assert detect_mutation_type(
            self._canonical(guest_email="new@test.com"),
            self._lineage(),
        ) == MutationType.GUEST_DETAIL_CHANGE

    def test_partial_modification(self):
        # Multiple fields changed → partial modification
        assert detect_mutation_type(
            self._canonical(check_in="2026-04-02", room_type_code="SGL", total_amount=600.0),
            self._lineage(),
        ) == MutationType.PARTIAL_MODIFICATION


# ── 2. State Transition Tests ─────────────────────────────────────

class TestStateTransitions:
    """Tests for canonical reservation state transitions."""

    def test_pending_to_confirmed(self):
        assert is_valid_transition("pending", "confirmed")

    def test_confirmed_to_checked_in(self):
        assert is_valid_transition("confirmed", "checked_in")

    def test_confirmed_to_cancelled(self):
        assert is_valid_transition("confirmed", "cancelled")

    def test_confirmed_to_no_show(self):
        assert is_valid_transition("confirmed", "no_show")

    def test_checked_in_to_checked_out(self):
        assert is_valid_transition("checked_in", "checked_out")

    def test_cancelled_to_confirmed_reinstatement(self):
        assert is_valid_transition("cancelled", "confirmed")

    def test_invalid_checked_out_to_confirmed(self):
        assert not is_valid_transition("checked_out", "confirmed")

    def test_invalid_no_show_to_any(self):
        assert not is_valid_transition("no_show", "confirmed")
        assert not is_valid_transition("no_show", "checked_in")

    def test_invalid_pending_to_checked_in(self):
        assert not is_valid_transition("pending", "checked_in")


# ── 3. Provider Capability Tests ──────────────────────────────────

from domains.channel_manager.provider_capability import (
    get_capability, classify_error, should_retry, get_retry_delay,
    PROVIDER_CAPABILITIES,
)


class TestProviderCapability:
    """Tests for provider capability matrix."""

    def test_exely_exists(self):
        cap = get_capability("exely")
        assert cap.display_name == "Exely"
        assert cap.ari_push_behavior.value == "split_messages"

    def test_hotelrunner_exists(self):
        cap = get_capability("hotelrunner")
        assert cap.display_name == "HotelRunner"
        assert cap.ari_push_behavior.value == "single_message"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            get_capability("unknown_provider")

    def test_exely_error_classification(self):
        assert classify_error("exely", "connection timeout") == ErrorClass.RETRYABLE
        assert classify_error("exely", "invalid credentials") == ErrorClass.CONFIGURATION
        assert classify_error("exely", "closed date range") == ErrorClass.BUSINESS_REJECTION

    def test_should_retry_retryable(self):
        assert should_retry("exely", "timeout error", 0) is True
        assert should_retry("exely", "timeout error", 3) is False  # max 3 attempts (0,1,2)

    def test_should_not_retry_config_error(self):
        assert should_retry("exely", "invalid credentials", 0) is False

    def test_retry_delay_exponential(self):
        d0 = get_retry_delay("exely", 0)
        d1 = get_retry_delay("exely", 1)
        d2 = get_retry_delay("exely", 2)
        assert d1 > d0
        assert d2 > d1

    def test_exely_ack_not_applied(self):
        cap = get_capability("exely")
        assert cap.ack_means_applied is False


# ── 4. Reconciliation Truth Table Tests ───────────────────────────

from domains.channel_manager.reconciliation_truth import (
    get_resolution_for_drift, can_auto_heal, get_truth_table_summary,
)


class TestReconciliationTruth:
    """Tests for reconciliation truth table."""

    def test_missing_locally_manual_review(self):
        rule = get_resolution_for_drift("missing_locally")
        assert rule.resolution == DriftResolution.MANUAL_REVIEW

    def test_stale_locally_auto_heal(self):
        rule = get_resolution_for_drift("stale_locally")
        assert rule.resolution == DriftResolution.SAFE_AUTO_HEAL

    def test_financial_mismatch_manual_review(self):
        rule = get_resolution_for_drift("financial_mismatch")
        assert rule.resolution == DriftResolution.MANUAL_REVIEW

    def test_can_auto_heal_stale(self):
        assert can_auto_heal("stale_locally") is True
        assert can_auto_heal("stale_remotely") is True

    def test_cannot_auto_heal_missing(self):
        assert can_auto_heal("missing_locally") is False
        assert can_auto_heal("missing_remotely") is False

    def test_truth_table_summary_serializable(self):
        summary = get_truth_table_summary()
        assert len(summary) > 0
        for item in summary:
            assert "drift_type" in item
            assert "resolution" in item
            assert "gold_source" in item
            assert "can_auto_heal" in item
            # Must be JSON serializable
            json.dumps(item)


# ── 5. Mapping Validator Tests ────────────────────────────────────

from domains.channel_manager.mapping_validator import (
    validate_room_mapping, validate_rate_plan_mapping,
    compute_mapping_health, MappingValidationError,
)


class TestMappingValidator:
    """Tests for mapping completeness hard fail."""

    def test_unmapped_room_fails(self):
        err = validate_room_mapping(None, "ROOM_X")
        assert err is not None
        assert err.failure_type == MappingFailure.UNMAPPED
        assert "operator_action" in err.to_dict()

    def test_inactive_room_fails(self):
        mapping = {"is_active": False, "pms_room_type_id": "r1"}
        err = validate_room_mapping(mapping, "ROOM_X")
        assert err is not None
        assert err.failure_type == MappingFailure.INACTIVE

    def test_valid_room_passes(self):
        mapping = {"is_active": True, "validation_status": "valid", "pms_room_type_id": "r1"}
        err = validate_room_mapping(mapping, "ROOM_X")
        assert err is None

    def test_unmapped_rate_plan_fails(self):
        err = validate_rate_plan_mapping(None, "RATE_X")
        assert err is not None
        assert err.failure_type == MappingFailure.UNMAPPED

    def test_deleted_room_fails(self):
        mapping = {"is_active": True, "validation_status": "valid", "pms_room_type_id": ""}
        err = validate_room_mapping(mapping, "ROOM_X")
        assert err is not None
        assert err.failure_type == MappingFailure.DELETED


@pytest.mark.asyncio
class TestMappingHealth:
    async def test_empty_mappings(self):
        health = await compute_mapping_health("t1", "p1", "exely", [], [])
        assert health["overall_completeness_pct"] == 0
        assert health["is_production_ready"] is False

    async def test_full_healthy_mappings(self):
        rooms = [
            {"is_active": True, "validation_status": "valid", "pms_room_type_id": "r1"},
            {"is_active": True, "validation_status": "valid", "pms_room_type_id": "r2"},
        ]
        rates = [
            {"is_active": True, "validation_status": "valid", "pms_rate_plan_id": "rp1"},
        ]
        health = await compute_mapping_health("t1", "p1", "exely", rooms, rates)
        assert health["overall_completeness_pct"] == 100.0
        assert health["room_mapping"]["broken"] == 0
        assert health["is_production_ready"] is True
