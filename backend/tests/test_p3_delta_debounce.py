"""
P3 — Delta-Only Push + Debounce Correctness
=============================================

Proves the ARI pipeline produces correct, minimal, non-redundant pushes:

  1. Multiple rate changes within same debounce window → only final value pushed
  2. Inventory + restriction changing simultaneously → separate correct deltas
  3. close/open/close pattern → final state is "close"
  4. Intermediate state loss — intermediate states never reach provider
  5. Same data not re-pushed — outbound idempotency blocks duplicate push
  6. Burst → correct final payload after debounce
  7. Delta-only: unchanged fields are NOT pushed
  8. Cross-room isolation: changes in room A don't leak into room B
  9. Rate plan scoping: same room, different rate plans stay isolated
  10. Debounce window respects event_type-specific timing
  11. Coalescing + compilation pipeline end-to-end correctness
  12. Concurrent availability+rate+restriction burst → 3 isolated deltas

Success criteria:
  - After any burst, compiled delta matches ONLY the final intended state
  - No stale/intermediate payloads survive past debounce
  - Outbound hash blocks identical re-pushes
  - Different scopes (avail/rate/restriction) never bleed into each other
"""
import asyncio
import copy
import json
import time
from datetime import date, timedelta
from typing import List, Dict

import pytest

from domains.channel_manager.ari.events import ARIChangeEvent, ARIDelta
from domains.channel_manager.ari.coalescer import (
    coalesce_events, _merge_date_ranges, _apply_restriction_precedence,
)
from domains.channel_manager.ari.delta_compiler import (
    compile_delta, compile_delta_hotelrunner, compile_delta_exely,
)
from domains.channel_manager.ari.buffer import ARIEventBuffer, _coalescing_key
from domains.channel_manager.ari.repositories import (
    compute_delta_hash, compute_outbound_delta_hash,
)
from domains.channel_manager.ari.models import DEBOUNCE_WINDOWS


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _ev(
    event_type="availability",
    room="DBL",
    rate=None,
    date_from=None,
    date_to=None,
    payload=None,
    **kw,
) -> ARIChangeEvent:
    return ARIChangeEvent(
        tenant_id="t1",
        property_id="p1",
        source_service="pricing",
        event_type=event_type,
        room_type_code=room,
        rate_plan_code=rate,
        date_from=date_from or date(2026, 8, 1),
        date_to=date_to or date(2026, 8, 7),
        payload=payload or {"availability": 10},
        **kw,
    )


def _cs(
    provider="exely",
    scope="availability",
    room="DBL",
    rate="STD",
    date_from="2026-08-01",
    date_to="2026-08-07",
    payload=None,
):
    payload = payload or {"availability": 10}
    return {
        "id": "cs-test",
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
        "provider_delta_hash": compute_outbound_delta_hash(
            provider, "p1", room, rate, date_from, date_to, payload,
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 1. MULTIPLE RATE CHANGES WITHIN SAME WINDOW
# ═══════════════════════════════════════════════════════════════

class TestMultiRateChangesInWindow:
    """Multiple rate changes in one debounce window → only final value pushed."""

    def test_5_rapid_rate_changes_last_wins(self):
        """5 rate changes → coalescer keeps last payload per date range."""
        events = [
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 100, "currency": "TRY"}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 120, "currency": "TRY"}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 90, "currency": "TRY"}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 200, "currency": "TRY"}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 150, "currency": "TRY"}),
        ]
        change_sets = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            events, ["exely"],
        )
        # All same date range → merged into 1 change set
        # _merge_date_ranges processes sorted by date, last payload in list wins
        assert len(change_sets) == 1
        # The final merged payload should be the last event's payload
        # because _merge_date_ranges keeps last non-mergeable payload
        final = change_sets[0]["compacted_payload"]
        assert final["base_rate"] == 150

    def test_10_rate_oscillations_final_value(self):
        """10 oscillating rates → only final rate survives."""
        rates = [100, 200, 100, 200, 100, 200, 100, 200, 100, 250]
        events = [
            _ev(event_type="rate", rate="BAR", payload={"base_rate": r, "currency": "TRY"})
            for r in rates
        ]
        change_sets = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            events, ["exely"],
        )
        assert len(change_sets) == 1
        assert change_sets[0]["compacted_payload"]["base_rate"] == 250

    def test_rate_change_compiled_to_exely(self):
        """Final rate → correct Exely AmountAfterTax."""
        cs = _cs(provider="exely", scope="rate", payload={"base_rate": 350, "currency": "EUR"})
        delta = compile_delta_exely(cs)
        assert delta.payload["AmountAfterTax"] == "350"
        assert delta.payload["CurrencyCode"] == "EUR"

    def test_rate_change_compiled_to_hotelrunner(self):
        """Final rate → correct HotelRunner price."""
        cs = _cs(provider="hotelrunner", scope="rate", payload={"base_rate": 350, "currency": "EUR"})
        delta = compile_delta_hotelrunner(cs)
        assert delta.payload["price"] == 350
        assert delta.payload["currency"] == "EUR"


# ═══════════════════════════════════════════════════════════════
# 2. INVENTORY + RESTRICTION SIMULTANEOUS CHANGE
# ═══════════════════════════════════════════════════════════════

class TestSimultaneousAvailAndRestriction:
    """Inventory and restriction change at the same time → separate deltas."""

    def test_avail_and_restriction_separate_keys(self):
        """Availability and restriction events produce different coalescing keys."""
        e_avail = _ev(event_type="availability", payload={"availability": 5})
        e_restr = _ev(event_type="restriction", payload={"min_los": 3, "stop_sell": False})
        assert _coalescing_key(e_avail) != _coalescing_key(e_restr)

    def test_avail_and_restriction_parallel_coalesce(self):
        """Parallel changes → 2 independent change set batches."""
        avail_events = [_ev(event_type="availability", payload={"availability": 5})]
        restr_events = [_ev(event_type="restriction", payload={"min_los": 2, "stop_sell": True})]

        cs_avail = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            avail_events, ["exely"],
        )
        cs_restr = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            restr_events, ["exely"],
        )

        assert len(cs_avail) == 1
        assert len(cs_restr) == 1
        assert cs_avail[0]["change_scope"] == "availability"
        assert cs_restr[0]["change_scope"] == "restriction"
        assert cs_avail[0]["compacted_payload"]["availability"] == 5
        assert cs_restr[0]["compacted_payload"]["stop_sell"] is True
        assert cs_restr[0]["compacted_payload"]["min_los"] == 2

    def test_avail_and_restriction_compile_correctly(self):
        """Both compile to valid provider-specific deltas."""
        cs_a = _cs(provider="exely", scope="availability", payload={"availability": 0, "stop_sell": True})
        cs_r = _cs(provider="exely", scope="restriction", payload={"min_los": 3, "cta": True})

        d_a = compile_delta_exely(cs_a)
        d_r = compile_delta_exely(cs_r)

        assert d_a.payload["BookingLimit"] == 0
        assert d_a.payload["RestrictionStatus"] == "Close"
        assert d_r.payload["MinLOS"] == 3
        assert d_r.payload["ArrivalDateBased"] is False  # cta=True → !cta

    def test_avail_restr_rate_triple_burst(self):
        """All 3 scopes change at once → 3 isolated change set groups."""
        avail = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            [_ev(event_type="availability", payload={"availability": 3})],
            ["exely"],
        )
        rate = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            [_ev(event_type="rate", rate="BAR", payload={"base_rate": 500, "currency": "TRY"})],
            ["exely"],
        )
        restr = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            [_ev(event_type="restriction", payload={"min_los": 2})],
            ["exely"],
        )

        assert len(avail) == 1 and avail[0]["change_scope"] == "availability"
        assert len(rate) == 1 and rate[0]["change_scope"] == "rate"
        assert len(restr) == 1 and restr[0]["change_scope"] == "restriction"


# ═══════════════════════════════════════════════════════════════
# 3. CLOSE/OPEN/CLOSE PATTERN
# ═══════════════════════════════════════════════════════════════

class TestCloseOpenClosePattern:
    """close → open → close → final state is 'close' (close wins)."""

    def test_close_open_close_restriction(self):
        """Restriction precedence: close > open."""
        events = [
            _ev(event_type="restriction", payload={"stop_sell": True}),
            _ev(event_type="restriction", payload={"stop_sell": False}),
            _ev(event_type="restriction", payload={"stop_sell": True}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            events, ["exely"],
        )
        assert cs[0]["compacted_payload"]["stop_sell"] is True

    def test_open_close_open_close(self):
        """4 toggles → close wins."""
        payloads = [
            {"stop_sell": False},
            {"stop_sell": True},
            {"stop_sell": False},
            {"stop_sell": True},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["stop_sell"] is True

    def test_close_stays_even_with_more_opens(self):
        """1 close + 5 opens → close wins."""
        payloads = [
            {"stop_sell": True},
            {"stop_sell": False},
            {"stop_sell": False},
            {"stop_sell": False},
            {"stop_sell": False},
            {"stop_sell": False},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["stop_sell"] is True

    def test_close_open_close_compiles_to_exely(self):
        """After precedence, Exely delta has RestrictionStatus=Close."""
        cs = _cs(provider="exely", scope="restriction", payload={"stop_sell": True, "min_los": 1})
        delta = compile_delta_exely(cs)
        assert delta.payload["RestrictionStatus"] == "Close"

    def test_close_open_close_compiles_to_hotelrunner(self):
        """After precedence, HotelRunner delta has stop_sale=1."""
        cs = _cs(provider="hotelrunner", scope="restriction", payload={"stop_sell": True})
        delta = compile_delta_hotelrunner(cs)
        assert delta.payload["stop_sale"] == 1

    def test_cta_ctd_toggle_pattern(self):
        """CTA/CTD flip-flop: latest value wins for each."""
        payloads = [
            {"cta": True, "ctd": False},
            {"cta": False, "ctd": True},
            {"cta": True, "ctd": True},
        ]
        result = _apply_restriction_precedence(payloads)
        assert result["cta"] is True
        assert result["ctd"] is True

    def test_mixed_restriction_fields_close_open_close(self):
        """close/open/close with min_los changes → close wins, latest min_los."""
        events = [
            _ev(event_type="restriction", payload={"stop_sell": True, "min_los": 3}),
            _ev(event_type="restriction", payload={"stop_sell": False, "min_los": 1}),
            _ev(event_type="restriction", payload={"stop_sell": True, "min_los": 2}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            events, ["exely"],
        )
        assert cs[0]["compacted_payload"]["stop_sell"] is True
        assert cs[0]["compacted_payload"]["min_los"] == 2  # latest wins


# ═══════════════════════════════════════════════════════════════
# 4. INTERMEDIATE STATE LOSS
# ═══════════════════════════════════════════════════════════════

class TestIntermediateStateLoss:
    """Intermediate states within debounce window never reach provider."""

    def test_avail_10_5_0_only_final_survives(self):
        """avail=10 → avail=5 → avail=0: only avail=0 in change set."""
        events = [
            _ev(payload={"availability": 10}),
            _ev(payload={"availability": 5}),
            _ev(payload={"availability": 0}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        assert len(cs) == 1
        assert cs[0]["compacted_payload"]["availability"] == 0

    def test_rate_100_200_150_only_150(self):
        """rate=100 → 200 → 150: only 150 in delta."""
        events = [
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 100}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 200}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 150}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            events, ["exely"],
        )
        assert len(cs) == 1
        assert cs[0]["compacted_payload"]["base_rate"] == 150

    def test_no_intermediate_hash_leak(self):
        """Intermediate payloads don't affect final delta hash."""
        # Hash with intermediate
        events_with = [
            _ev(payload={"availability": 10}),
            _ev(payload={"availability": 5}),
            _ev(payload={"availability": 3}),
        ]
        cs_with = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events_with, ["exely"],
        )

        # Hash without intermediate
        events_without = [
            _ev(payload={"availability": 3}),
        ]
        cs_without = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events_without, ["exely"],
        )

        # Same final payload → same delta hash
        assert cs_with[0]["provider_delta_hash"] == cs_without[0]["provider_delta_hash"]


# ═══════════════════════════════════════════════════════════════
# 5. SAME DATA NOT RE-PUSHED (Outbound Idempotency)
# ═══════════════════════════════════════════════════════════════

class TestOutboundIdempotency:
    """Identical data produces identical hash → prevents re-push."""

    def test_identical_payloads_same_hash(self):
        """Same payload at same coordinates → same outbound delta hash."""
        h1 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 200, "currency": "TRY"},
        )
        h2 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 200, "currency": "TRY"},
        )
        assert h1 == h2

    def test_key_order_irrelevant(self):
        """JSON key ordering doesn't affect hash (sort_keys=True)."""
        h1 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"currency": "TRY", "base_rate": 200},
        )
        h2 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 200, "currency": "TRY"},
        )
        assert h1 == h2

    def test_different_value_different_hash(self):
        """Even 1 TRY difference → different hash → will be pushed."""
        h1 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 200},
        )
        h2 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 201},
        )
        assert h1 != h2

    def test_same_payload_different_date_range(self):
        """Same payload but different date range → different hash → pushed."""
        h1 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07",
            {"base_rate": 200},
        )
        h2 = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-08", "2026-08-14",
            {"base_rate": 200},
        )
        assert h1 != h2

    def test_change_set_hash_matches_after_coalescing(self):
        """Hash from coalescing == hash from manual computation."""
        events = [_ev(payload={"availability": 7})]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        expected_hash = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "",
            str(cs[0]["date_from"]), str(cs[0]["date_to"]),
            cs[0]["compacted_payload"],
        )
        assert cs[0]["provider_delta_hash"] == expected_hash

    def test_re_coalesce_same_events_same_hash(self):
        """Running coalescer twice on same events → same hash."""
        events = [
            _ev(payload={"availability": 5}),
            _ev(payload={"availability": 8}),
        ]
        cs1 = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        cs2 = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        assert cs1[0]["provider_delta_hash"] == cs2[0]["provider_delta_hash"]


# ═══════════════════════════════════════════════════════════════
# 6. BURST → CORRECT FINAL PAYLOAD
# ═══════════════════════════════════════════════════════════════

class TestBurstFinalPayload:
    """After a burst of events, final payload is correct end-to-end."""

    def test_20_event_avail_burst_final(self):
        """20 availability events → final availability in delta."""
        events = [_ev(payload={"availability": i}) for i in range(20)]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        assert len(cs) == 1
        assert cs[0]["compacted_payload"]["availability"] == 19

        # Compile to Exely
        delta = compile_delta_exely(cs[0])
        assert delta.payload["BookingLimit"] == 19

    def test_burst_with_stop_sell_final(self):
        """Availability burst ending with stop_sell → Close status."""
        events = [
            _ev(payload={"availability": 10}),
            _ev(payload={"availability": 5}),
            _ev(payload={"availability": 0, "stop_sell": True}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        # Last event wins for availability
        final = cs[-1]["compacted_payload"]
        assert final["availability"] == 0
        assert final.get("stop_sell") is True

    def test_burst_rate_dual_provider_final_matches(self):
        """Rate burst → final rate matches for both providers."""
        events = [
            _ev(event_type="rate", rate="BAR", payload={"base_rate": r, "currency": "TRY"})
            for r in [100, 150, 200, 175, 225]
        ]
        cs = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            events, ["exely", "hotelrunner"],
        )
        # 2 change sets (one per provider), both have final rate
        for c in cs:
            assert c["compacted_payload"]["base_rate"] == 225

    def test_restriction_burst_final_state(self):
        """Restriction burst → precedence applied correctly in final."""
        events = [
            _ev(event_type="restriction", payload={"min_los": 1, "stop_sell": False}),
            _ev(event_type="restriction", payload={"min_los": 3, "cta": True}),
            _ev(event_type="restriction", payload={"stop_sell": True, "ctd": True}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            events, ["exely"],
        )
        payload = cs[0]["compacted_payload"]
        assert payload["stop_sell"] is True   # close wins
        assert payload["min_los"] == 3        # latest explicit value
        assert payload["cta"] is True
        assert payload["ctd"] is True


# ═══════════════════════════════════════════════════════════════
# 7. DELTA-ONLY: UNCHANGED FIELDS NOT RE-PUSHED
# ═══════════════════════════════════════════════════════════════

class TestDeltaOnlyPush:
    """Only changed data appears in compiled delta."""

    def test_avail_only_has_booking_limit(self):
        """Availability delta → only BookingLimit, no rate fields."""
        cs = _cs(provider="exely", scope="availability", payload={"availability": 5})
        delta = compile_delta_exely(cs)
        assert "BookingLimit" in delta.payload
        assert "AmountAfterTax" not in delta.payload
        assert "MinLOS" not in delta.payload

    def test_rate_only_has_amount(self):
        """Rate delta → only AmountAfterTax, no avail/restriction fields."""
        cs = _cs(provider="exely", scope="rate", payload={"base_rate": 200, "currency": "TRY"})
        delta = compile_delta_exely(cs)
        assert "AmountAfterTax" in delta.payload
        assert "BookingLimit" not in delta.payload
        assert "MinLOS" not in delta.payload

    def test_restriction_only_has_restriction_fields(self):
        """Restriction delta → only restriction fields."""
        cs = _cs(provider="exely", scope="restriction", payload={"min_los": 2})
        delta = compile_delta_exely(cs)
        assert "MinLOS" in delta.payload
        assert "BookingLimit" not in delta.payload
        assert "AmountAfterTax" not in delta.payload

    def test_hr_avail_delta_clean(self):
        """HotelRunner availability → only availability, no price."""
        cs = _cs(provider="hotelrunner", scope="availability", payload={"availability": 8})
        delta = compile_delta_hotelrunner(cs)
        assert "availability" in delta.payload
        assert "price" not in delta.payload
        assert "min_stay" not in delta.payload


# ═══════════════════════════════════════════════════════════════
# 8. CROSS-ROOM ISOLATION
# ═══════════════════════════════════════════════════════════════

class TestCrossRoomIsolation:
    """Changes in room A don't leak into room B."""

    def test_different_rooms_different_keys(self):
        """DBL and SGL produce different coalescing keys."""
        e1 = _ev(room="DBL")
        e2 = _ev(room="SGL")
        assert _coalescing_key(e1) != _coalescing_key(e2)

    def test_room_a_change_doesnt_affect_room_b(self):
        """DBL avail=0 doesn't touch SGL's change set."""
        cs_dbl = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            [_ev(room="DBL", payload={"availability": 0})],
            ["exely"],
        )
        cs_sgl = coalesce_events(
            "t1|p1|SGL||2026-08-01:2026-08-07|availability",
            [_ev(room="SGL", payload={"availability": 10})],
            ["exely"],
        )
        assert cs_dbl[0]["compacted_payload"]["availability"] == 0
        assert cs_sgl[0]["compacted_payload"]["availability"] == 10
        assert cs_dbl[0]["room_type_code"] == "DBL"
        assert cs_sgl[0]["room_type_code"] == "SGL"

    def test_room_change_hash_isolation(self):
        """Same payload but different rooms → different hashes."""
        h_dbl = compute_outbound_delta_hash("exely", "p1", "DBL", "", "2026-08-01", "2026-08-07", {"availability": 5})
        h_sgl = compute_outbound_delta_hash("exely", "p1", "SGL", "", "2026-08-01", "2026-08-07", {"availability": 5})
        assert h_dbl != h_sgl


# ═══════════════════════════════════════════════════════════════
# 9. RATE PLAN SCOPING
# ═══════════════════════════════════════════════════════════════

class TestRatePlanScoping:
    """Same room, different rate plans stay isolated."""

    def test_bar_and_nr_separate_keys(self):
        """BAR and NR rate plans produce different coalescing keys."""
        e1 = _ev(event_type="rate", rate="BAR")
        e2 = _ev(event_type="rate", rate="NR")
        assert _coalescing_key(e1) != _coalescing_key(e2)

    def test_rate_plan_changes_isolated(self):
        """BAR rate change doesn't affect NR rate."""
        cs_bar = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            [_ev(event_type="rate", rate="BAR", payload={"base_rate": 300})],
            ["exely"],
        )
        cs_nr = coalesce_events(
            "t1|p1|DBL|NR|2026-08-01:2026-08-07|rate",
            [_ev(event_type="rate", rate="NR", payload={"base_rate": 250})],
            ["exely"],
        )
        assert cs_bar[0]["compacted_payload"]["base_rate"] == 300
        assert cs_nr[0]["compacted_payload"]["base_rate"] == 250


# ═══════════════════════════════════════════════════════════════
# 10. DEBOUNCE WINDOW CONFIGURATION
# ═══════════════════════════════════════════════════════════════

class TestDebounceWindowConfig:
    """Each event type has correct debounce window."""

    def test_availability_window(self):
        assert DEBOUNCE_WINDOWS["availability"] == 2

    def test_rate_window(self):
        assert DEBOUNCE_WINDOWS["rate"] == 5

    def test_restriction_window(self):
        assert DEBOUNCE_WINDOWS["restriction"] == 3

    def test_rate_window_longer_than_avail(self):
        """Rate changes debounce longer (pricing decisions more volatile)."""
        assert DEBOUNCE_WINDOWS["rate"] > DEBOUNCE_WINDOWS["availability"]


# ═══════════════════════════════════════════════════════════════
# 11. END-TO-END COALESCE → COMPILE PIPELINE
# ═══════════════════════════════════════════════════════════════

class TestEndToEndPipeline:
    """Full pipeline: events → coalesce → compile → verify."""

    def test_avail_e2e_exely(self):
        """Avail events → coalesce → compile → Exely delta correct."""
        events = [
            _ev(payload={"availability": 10}),
            _ev(payload={"availability": 3}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            events, ["exely"],
        )
        delta = compile_delta(cs[0])
        assert delta.provider == "exely"
        assert delta.payload["BookingLimit"] == 3

    def test_rate_e2e_hotelrunner(self):
        """Rate events → coalesce → compile → HR delta correct."""
        events = [
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 100, "currency": "TRY"}),
            _ev(event_type="rate", rate="BAR", payload={"base_rate": 200, "currency": "TRY"}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            events, ["hotelrunner"],
        )
        delta = compile_delta(cs[0])
        assert delta.provider == "hotelrunner"
        assert delta.payload["price"] == 200

    def test_restriction_e2e_dual_provider(self):
        """Restriction events → coalesce → compile for both providers."""
        events = [
            _ev(event_type="restriction", payload={"min_los": 2, "stop_sell": True}),
        ]
        cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            events, ["exely", "hotelrunner"],
        )
        assert len(cs) == 2
        for c in cs:
            delta = compile_delta(c)
            assert delta.change_scope == "restriction"

    def test_e2e_hash_determinism(self):
        """Full pipeline twice → identical delta hashes."""
        events = [_ev(payload={"availability": 7})]
        cs1 = coalesce_events("t1|p1|DBL||2026-08-01:2026-08-07|availability", events, ["exely"])
        cs2 = coalesce_events("t1|p1|DBL||2026-08-01:2026-08-07|availability", events, ["exely"])
        d1 = compile_delta(cs1[0])
        d2 = compile_delta(cs2[0])
        assert d1.provider_delta_hash == d2.provider_delta_hash


# ═══════════════════════════════════════════════════════════════
# 12. CONCURRENT BURST — ALL 3 SCOPES
# ═══════════════════════════════════════════════════════════════

class TestConcurrentTripleScopeBurst:
    """Concurrent avail+rate+restriction burst → 3 isolated deltas."""

    def test_triple_scope_isolation(self):
        """3 scopes changing simultaneously → each produces correct delta."""
        avail_cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|availability",
            [
                _ev(payload={"availability": 10}),
                _ev(payload={"availability": 5}),
                _ev(payload={"availability": 2}),
            ],
            ["exely"],
        )
        rate_cs = coalesce_events(
            "t1|p1|DBL|BAR|2026-08-01:2026-08-07|rate",
            [
                _ev(event_type="rate", rate="BAR", payload={"base_rate": 100, "currency": "TRY"}),
                _ev(event_type="rate", rate="BAR", payload={"base_rate": 300, "currency": "TRY"}),
            ],
            ["exely"],
        )
        restr_cs = coalesce_events(
            "t1|p1|DBL||2026-08-01:2026-08-07|restriction",
            [
                _ev(event_type="restriction", payload={"stop_sell": False, "min_los": 1}),
                _ev(event_type="restriction", payload={"stop_sell": True, "min_los": 3}),
            ],
            ["exely"],
        )

        # Compile each
        d_avail = compile_delta(avail_cs[0])
        d_rate = compile_delta(rate_cs[0])
        d_restr = compile_delta(restr_cs[0])

        # Verify isolation
        assert d_avail.payload["BookingLimit"] == 2
        assert "AmountAfterTax" not in d_avail.payload

        assert d_rate.payload["AmountAfterTax"] == "300"
        assert "BookingLimit" not in d_rate.payload

        assert d_restr.payload["RestrictionStatus"] == "Close"
        assert d_restr.payload["MinLOS"] == 3
        assert "BookingLimit" not in d_restr.payload

    def test_triple_scope_different_hashes(self):
        """All 3 scope deltas have different hashes."""
        h_avail = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "", "2026-08-01", "2026-08-07", {"BookingLimit": 5},
        )
        h_rate = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "BAR", "2026-08-01", "2026-08-07", {"AmountAfterTax": "200"},
        )
        h_restr = compute_outbound_delta_hash(
            "exely", "p1", "DBL", "", "2026-08-01", "2026-08-07", {"MinLOS": 2},
        )
        assert len({h_avail, h_rate, h_restr}) == 3  # all unique


# ═══════════════════════════════════════════════════════════════
# 13. MULTI-DAY DELTA COMPILATION
# ═══════════════════════════════════════════════════════════════

class TestMultiDayDeltaCompilation:
    """Multi-day ranges compile correctly."""

    def test_7_day_range_single_delta(self):
        """7-day availability update → single compiled delta."""
        cs = _cs(
            provider="exely", scope="availability",
            date_from="2026-09-01", date_to="2026-09-07",
            payload={"availability": 4},
        )
        delta = compile_delta_exely(cs)
        assert str(delta.date_from) == "2026-09-01"
        assert str(delta.date_to) == "2026-09-07"
        assert delta.payload["BookingLimit"] == 4

    def test_merged_consecutive_days_produce_range(self):
        """7 consecutive same-value days → 1 merged range."""
        events = []
        base = date(2026, 9, 1)
        for i in range(7):
            d = base + timedelta(days=i)
            events.append(_ev(date_from=d, date_to=d, payload={"availability": 4}))

        merged = _merge_date_ranges(events)
        assert len(merged) == 1
        assert merged[0]["date_from"] == date(2026, 9, 1)
        assert merged[0]["date_to"] == date(2026, 9, 7)

    def test_weekend_vs_weekday_split(self):
        """Different values weekday vs weekend → separate ranges."""
        events = [
            # Mon-Fri: avail=10
            _ev(date_from=date(2026, 9, 7), date_to=date(2026, 9, 11), payload={"availability": 10}),
            # Sat-Sun: avail=5
            _ev(date_from=date(2026, 9, 12), date_to=date(2026, 9, 13), payload={"availability": 5}),
        ]
        merged = _merge_date_ranges(events)
        assert len(merged) == 2
