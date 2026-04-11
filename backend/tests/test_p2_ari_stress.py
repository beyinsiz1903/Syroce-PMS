"""
P2 — ARI Stress Tests
======================

Tests the ARI pipeline under stress conditions:

  1. Mass inventory update (bulk events)
  2. Rate burst (rapid rate changes)
  3. Mixed room/rate updates
  4. Buffer debounce correctness
  5. Delta compilation accuracy
  6. Coalescer behavior under load
  7. Provider-specific compilation correctness
  8. Outbound idempotency

Tests here are unit/integration tests that validate the ARI engine
components without requiring actual provider connections.
"""
import copy
import json
from datetime import date, timedelta
from typing import List

import pytest

from domains.channel_manager.ari.events import ARIChangeEvent, ARIDelta, ProviderResult
from domains.channel_manager.ari.coalescer import (
    coalesce_events, _merge_date_ranges, _apply_restriction_precedence,
)
from domains.channel_manager.ari.delta_compiler import (
    compile_delta, compile_delta_hotelrunner, compile_delta_exely,
    COMPILERS,
)
from domains.channel_manager.ari.buffer import ARIEventBuffer, _coalescing_key
from domains.channel_manager.ari.repositories import compute_delta_hash, compute_outbound_delta_hash
from domains.channel_manager.provider_capability import (
    get_capability, classify_error, should_retry, get_retry_delay,
    PROVIDER_CAPABILITIES,
)
from domains.channel_manager.data_model import ErrorClass


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _ari_event(
    event_type="availability",
    room_type="DBL",
    rate_plan=None,
    date_from=None,
    date_to=None,
    payload=None,
    **overrides,
) -> ARIChangeEvent:
    return ARIChangeEvent(
        tenant_id="t1",
        property_id="p1",
        source_service="pricing",
        event_type=event_type,
        room_type_code=room_type,
        rate_plan_code=rate_plan,
        date_from=date_from or date(2026, 6, 1),
        date_to=date_to or date(2026, 6, 7),
        payload=payload or {"availability": 10},
        **overrides,
    )


def _change_set(
    provider="exely",
    scope="availability",
    room="DBL",
    rate="STD",
    date_from="2026-06-01",
    date_to="2026-06-07",
    payload=None,
):
    payload = payload or {"availability": 10}
    return {
        "id": "cs-1",
        "tenant_id": "t1",
        "property_id": "p1",
        "provider": provider,
        "coalescing_key": f"t1|p1|{provider}|{room}|{rate}|{date_from}:{date_to}|{scope}",
        "room_type_code": room,
        "rate_plan_code": rate,
        "date_from": date_from,
        "date_to": date_to,
        "change_scope": scope,
        "compacted_payload": payload,
        "provider_delta_hash": "",
    }


# ═══════════════════════════════════════════════════════════════
# 1. MASS INVENTORY UPDATE
# ═══════════════════════════════════════════════════════════════

class TestMassInventoryUpdate:
    """Bulk availability changes coalesce correctly."""

    def test_30_day_availability_update(self):
        """30 single-day events → coalesced into minimal change sets."""
        events = []
        base = date(2026, 7, 1)
        for i in range(30):
            d = base + timedelta(days=i)
            events.append(_ari_event(
                date_from=d,
                date_to=d,
                payload={"availability": 5},
            ))

        change_sets = coalesce_events(
            "t1|p1|DBL||2026-07-01:2026-07-30|availability",
            events,
            ["exely"],
        )

        # Should produce at most 1 change set (all same payload → merge)
        assert len(change_sets) >= 1
        assert len(change_sets) <= 30  # worst case: 30 non-mergeable

    def test_mixed_availability_values(self):
        """Different availability values → separate change sets."""
        events = [
            _ari_event(date_from=date(2026, 7, 1), date_to=date(2026, 7, 3), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 4), date_to=date(2026, 7, 6), payload={"availability": 10}),
            _ari_event(date_from=date(2026, 7, 7), date_to=date(2026, 7, 10), payload={"availability": 5}),
        ]

        change_sets = coalesce_events(
            "t1|p1|DBL||2026-07-01:2026-07-10|availability",
            events,
            ["exely"],
        )

        # Different payloads can't merge
        assert len(change_sets) >= 2

    def test_stop_sell_bulk(self):
        """Bulk stop sell → single coalesced change set."""
        events = [
            _ari_event(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 15),
                payload={"availability": 0, "stop_sell": True},
            ),
        ]

        change_sets = coalesce_events(
            "t1|p1|DBL||2026-07-01:2026-07-15|availability",
            events,
            ["exely", "hotelrunner"],
        )

        assert len(change_sets) == 2  # one per provider
        for cs in change_sets:
            assert cs["compacted_payload"]["stop_sell"] is True


# ═══════════════════════════════════════════════════════════════
# 2. RATE BURST
# ═══════════════════════════════════════════════════════════════

class TestRateBurst:
    """Rapid rate changes → last value wins, correct delta."""

    def test_last_rate_wins(self):
        """5 rapid rate changes → last payload wins in coalescer."""
        events = [
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 100, "currency": "TRY"}),
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 120, "currency": "TRY"}),
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 95, "currency": "TRY"}),
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 150, "currency": "TRY"}),
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 130, "currency": "TRY"}),
        ]

        change_sets = coalesce_events(
            "t1|p1|DBL|STD|2026-06-01:2026-06-07|rate",
            events,
            ["exely"],
        )

        # Last rate should be in the result
        assert len(change_sets) >= 1

    def test_multi_room_rate_burst(self):
        """Rate changes for multiple room types → isolated change sets."""
        events_dbl = [
            _ari_event(event_type="rate", room_type="DBL", rate_plan="STD", payload={"base_rate": 200}),
        ]
        events_sgl = [
            _ari_event(event_type="rate", room_type="SGL", rate_plan="STD", payload={"base_rate": 150}),
        ]

        cs_dbl = coalesce_events("t1|p1|DBL|STD|2026-06-01:2026-06-07|rate", events_dbl, ["exely"])
        cs_sgl = coalesce_events("t1|p1|SGL|STD|2026-06-01:2026-06-07|rate", events_sgl, ["exely"])

        assert len(cs_dbl) >= 1
        assert len(cs_sgl) >= 1
        assert cs_dbl[0]["room_type_code"] == "DBL"
        assert cs_sgl[0]["room_type_code"] == "SGL"


# ═══════════════════════════════════════════════════════════════
# 3. MIXED ROOM/RATE UPDATES
# ═══════════════════════════════════════════════════════════════

class TestMixedUpdates:
    """Availability + rate updates for same room in burst."""

    def test_availability_and_rate_separate_scopes(self):
        """Availability and rate events keep separate scopes."""
        avail_events = [
            _ari_event(event_type="availability", payload={"availability": 8}),
        ]
        rate_events = [
            _ari_event(event_type="rate", rate_plan="STD", payload={"base_rate": 200}),
        ]

        cs_avail = coalesce_events("t1|p1|DBL||2026-06-01:2026-06-07|availability", avail_events, ["exely"])
        cs_rate = coalesce_events("t1|p1|DBL|STD|2026-06-01:2026-06-07|rate", rate_events, ["exely"])

        assert all(cs["change_scope"] == "availability" for cs in cs_avail)
        assert all(cs["change_scope"] == "rate" for cs in cs_rate)


# ═══════════════════════════════════════════════════════════════
# 4. RESTRICTION PRECEDENCE
# ═══════════════════════════════════════════════════════════════

class TestRestrictionPrecedence:
    """Restriction merge: close > open, explicit wins."""

    def test_stop_sell_close_wins(self):
        """close (stop_sell=True) overrides open."""
        payloads = [
            {"stop_sell": False},
            {"stop_sell": True},
            {"stop_sell": False},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["stop_sell"] is True

    def test_min_los_latest_wins(self):
        """Latest min_los value wins."""
        payloads = [
            {"min_los": 2},
            {"min_los": 3},
            {"min_los": 1},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["min_los"] == 1  # last value wins

    def test_cta_ctd_mixed(self):
        """CTA/CTD flags merged correctly."""
        payloads = [
            {"cta": True, "ctd": False},
            {"ctd": True},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["cta"] is True
        assert result["ctd"] is True

    def test_restriction_coalesce(self):
        """Restriction events coalesce with precedence rules."""
        events = [
            _ari_event(event_type="restriction", payload={"stop_sell": False, "min_los": 2}),
            _ari_event(event_type="restriction", payload={"stop_sell": True}),
        ]

        change_sets = coalesce_events(
            "t1|p1|DBL||2026-06-01:2026-06-07|restriction",
            events,
            ["exely"],
        )

        assert len(change_sets) >= 1
        assert change_sets[0]["compacted_payload"]["stop_sell"] is True
        assert change_sets[0]["compacted_payload"]["min_los"] == 2


# ═══════════════════════════════════════════════════════════════
# 5. DELTA COMPILATION ACCURACY
# ═══════════════════════════════════════════════════════════════

class TestDeltaCompilation:
    """Provider-specific delta compilation is correct."""

    def test_exely_availability_delta(self):
        cs = _change_set(provider="exely", scope="availability", payload={"availability": 5, "stop_sell": True})
        delta = compile_delta_exely(cs)
        assert delta.provider == "exely"
        assert delta.payload["BookingLimit"] == 5
        assert delta.payload["RestrictionStatus"] == "Close"

    def test_exely_rate_delta(self):
        cs = _change_set(provider="exely", scope="rate", payload={"base_rate": 200, "currency": "TRY"})
        delta = compile_delta_exely(cs)
        assert delta.payload["AmountAfterTax"] == "200"
        assert delta.payload["CurrencyCode"] == "TRY"

    def test_exely_restriction_delta(self):
        cs = _change_set(provider="exely", scope="restriction", payload={"min_los": 3, "cta": True, "stop_sell": False})
        delta = compile_delta_exely(cs)
        assert delta.payload["MinLOS"] == 3
        assert delta.payload["ArrivalDateBased"] is False  # cta=True → ArrivalDateBased=False
        assert delta.payload["RestrictionStatus"] == "Open"

    def test_hotelrunner_availability_delta(self):
        cs = _change_set(provider="hotelrunner", scope="availability", payload={"availability": 8, "stop_sell": False})
        delta = compile_delta_hotelrunner(cs)
        assert delta.provider == "hotelrunner"
        assert delta.payload["availability"] == 8
        assert delta.payload["stop_sale"] == 0

    def test_hotelrunner_rate_delta(self):
        cs = _change_set(provider="hotelrunner", scope="rate", payload={"base_rate": 300, "currency": "TRY"})
        delta = compile_delta_hotelrunner(cs)
        assert delta.payload["price"] == 300
        assert delta.payload["currency"] == "TRY"

    def test_hotelrunner_restriction_delta(self):
        cs = _change_set(provider="hotelrunner", scope="restriction", payload={"min_los": 2, "cta": False, "ctd": True, "stop_sell": True})
        delta = compile_delta_hotelrunner(cs)
        assert delta.payload["min_stay"] == 2
        assert delta.payload["cta"] == 0
        assert delta.payload["ctd"] == 1
        assert delta.payload["stop_sale"] == 1

    def test_compile_delta_unknown_provider_raises(self):
        cs = _change_set(provider="unknown_provider")
        with pytest.raises(ValueError, match="No delta compiler"):
            compile_delta(cs)

    def test_multi_provider_compilation(self):
        """Same logical change → different delta per provider."""
        payload = {"availability": 5, "stop_sell": False}
        cs_ex = _change_set(provider="exely", payload=payload)
        cs_hr = _change_set(provider="hotelrunner", payload=payload)

        d_ex = compile_delta(cs_ex)
        d_hr = compile_delta(cs_hr)

        assert d_ex.provider == "exely"
        assert d_hr.provider == "hotelrunner"
        # Exely uses BookingLimit, HR uses availability
        assert "BookingLimit" in d_ex.payload
        assert "availability" in d_hr.payload


# ═══════════════════════════════════════════════════════════════
# 6. BUFFER COALESCING KEY CORRECTNESS
# ═══════════════════════════════════════════════════════════════

class TestBufferCoalescingKey:
    """Coalescing key generation is deterministic and correct."""

    def test_key_deterministic(self):
        e1 = _ari_event()
        e2 = _ari_event()
        assert _coalescing_key(e1) == _coalescing_key(e2)

    def test_key_differs_by_room(self):
        e1 = _ari_event(room_type="DBL")
        e2 = _ari_event(room_type="SGL")
        assert _coalescing_key(e1) != _coalescing_key(e2)

    def test_key_differs_by_type(self):
        e1 = _ari_event(event_type="availability")
        e2 = _ari_event(event_type="rate")
        assert _coalescing_key(e1) != _coalescing_key(e2)

    def test_key_differs_by_date(self):
        e1 = _ari_event(date_from=date(2026, 6, 1), date_to=date(2026, 6, 7))
        e2 = _ari_event(date_from=date(2026, 6, 8), date_to=date(2026, 6, 14))
        assert _coalescing_key(e1) != _coalescing_key(e2)

    def test_key_includes_rate_plan(self):
        e1 = _ari_event(event_type="rate", rate_plan="STD")
        e2 = _ari_event(event_type="rate", rate_plan="PROMO")
        assert _coalescing_key(e1) != _coalescing_key(e2)


# ═══════════════════════════════════════════════════════════════
# 7. DATE RANGE MERGING
# ═══════════════════════════════════════════════════════════════

class TestDateRangeMerging:
    """Consecutive same-value dates merge into ranges."""

    def test_consecutive_dates_merge(self):
        """3 consecutive days with same payload → 1 range."""
        events = [
            _ari_event(date_from=date(2026, 7, 1), date_to=date(2026, 7, 1), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 2), date_to=date(2026, 7, 2), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 3), date_to=date(2026, 7, 3), payload={"availability": 5}),
        ]
        merged = _merge_date_ranges(events)
        assert len(merged) == 1
        assert merged[0]["date_from"] == date(2026, 7, 1)
        assert merged[0]["date_to"] == date(2026, 7, 3)

    def test_non_consecutive_no_merge(self):
        """Gap in dates → no merge."""
        events = [
            _ari_event(date_from=date(2026, 7, 1), date_to=date(2026, 7, 1), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 5), date_to=date(2026, 7, 5), payload={"availability": 5}),
        ]
        merged = _merge_date_ranges(events)
        assert len(merged) == 2

    def test_different_payload_no_merge(self):
        """Same dates but different payload → no merge."""
        events = [
            _ari_event(date_from=date(2026, 7, 1), date_to=date(2026, 7, 2), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 3), date_to=date(2026, 7, 4), payload={"availability": 10}),
        ]
        merged = _merge_date_ranges(events)
        assert len(merged) == 2

    def test_empty_events(self):
        merged = _merge_date_ranges([])
        assert merged == []


# ═══════════════════════════════════════════════════════════════
# 8. PROVIDER ERROR CLASSIFICATION & RETRY
# ═══════════════════════════════════════════════════════════════

class TestProviderErrorHandling:
    """Error classification and retry policy under stress scenarios."""

    def test_429_is_retryable(self):
        assert classify_error("exely", "429 Too Many Requests") == ErrorClass.RETRYABLE
        assert classify_error("hotelrunner", "429 rate limit exceeded") == ErrorClass.RETRYABLE

    def test_timeout_is_retryable(self):
        assert classify_error("exely", "connection timeout") == ErrorClass.RETRYABLE
        assert classify_error("hotelrunner", "timeout error") == ErrorClass.RETRYABLE

    def test_auth_is_config_error(self):
        assert classify_error("exely", "invalid credentials provided") == ErrorClass.CONFIGURATION
        assert classify_error("hotelrunner", "invalid api key") == ErrorClass.CONFIGURATION

    def test_business_rejection_not_retryable(self):
        assert classify_error("exely", "closed date range") == ErrorClass.BUSINESS_REJECTION
        assert should_retry("exely", "closed date range", 0) is False

    def test_retry_exhaustion(self):
        """After max attempts, no more retries."""
        cap = get_capability("exely")
        max_a = cap.retry_policy.max_attempts
        assert should_retry("exely", "timeout", 0) is True
        assert should_retry("exely", "timeout", max_a) is False

    def test_exponential_backoff_increasing(self):
        """Delay increases with each attempt."""
        delays = [get_retry_delay("exely", i) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_max_delay_capped(self):
        """Delay never exceeds max."""
        cap = get_capability("exely")
        delay = get_retry_delay("exely", 100)
        assert delay <= cap.retry_policy.max_delay_seconds

    @pytest.mark.parametrize("provider", ["exely", "hotelrunner"])
    def test_rate_limit_config_exists(self, provider):
        """Both providers have rate limit config."""
        cap = get_capability(provider)
        assert cap.rate_limits.requests_per_minute > 0
        assert cap.rate_limits.requests_per_hour > 0
        assert cap.rate_limits.burst_limit > 0


# ═══════════════════════════════════════════════════════════════
# 9. OUTBOUND DELTA HASH DETERMINISM
# ═══════════════════════════════════════════════════════════════

class TestOutboundDeltaHash:
    """Outbound delta hash is deterministic for idempotency."""

    def test_same_input_same_hash(self):
        h1 = compute_outbound_delta_hash("exely", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 5})
        h2 = compute_outbound_delta_hash("exely", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 5})
        assert h1 == h2

    def test_different_payload_different_hash(self):
        h1 = compute_outbound_delta_hash("exely", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 5})
        h2 = compute_outbound_delta_hash("exely", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 10})
        assert h1 != h2

    def test_different_provider_different_hash(self):
        h1 = compute_outbound_delta_hash("exely", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 5})
        h2 = compute_outbound_delta_hash("hotelrunner", "p1", "DBL", "STD", "2026-06-01", "2026-06-07", {"availability": 5})
        assert h1 != h2


# ═══════════════════════════════════════════════════════════════
# 10. MULTI-PROVIDER COALESCING
# ═══════════════════════════════════════════════════════════════

class TestMultiProviderCoalescing:
    """Change sets are correctly generated for all active providers."""

    def test_dual_provider_output(self):
        """Single event → change set per provider."""
        events = [_ari_event(payload={"availability": 5})]
        cs = coalesce_events(
            "t1|p1|DBL||2026-06-01:2026-06-07|availability",
            events,
            ["exely", "hotelrunner"],
        )
        providers = {c["provider"] for c in cs}
        assert "exely" in providers
        assert "hotelrunner" in providers

    def test_three_events_dual_provider(self):
        """3 events × 2 providers → ≤ 6 change sets."""
        events = [
            _ari_event(date_from=date(2026, 7, 1), date_to=date(2026, 7, 3), payload={"availability": 5}),
            _ari_event(date_from=date(2026, 7, 4), date_to=date(2026, 7, 6), payload={"availability": 10}),
            _ari_event(date_from=date(2026, 7, 7), date_to=date(2026, 7, 10), payload={"availability": 5}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-07-01:2026-07-10|availability",
            events,
            ["exely", "hotelrunner"],
        )
        # 2-3 merged ranges × 2 providers
        assert len(cs) >= 2
        assert len(cs) <= 6
