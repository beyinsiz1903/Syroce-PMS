"""
ARI Event Coalescer.

Takes a batch of events for the same coalescing key and produces
a single compacted change set per provider.

Rules:
  - Same key + same payload → single record
  - Same key + different payload → last payload wins
  - Consecutive dates with same value → date range merge
  - Restriction precedence: close > open, explicit values override old
"""
import logging
from datetime import date, timedelta
from typing import Dict, List

from .events import ARIChangeEvent
from .repositories import compute_delta_hash, compute_outbound_delta_hash

logger = logging.getLogger(__name__)


def _parse_date(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d))


def _deduplicate_by_date_range(events: List[ARIChangeEvent]) -> List[ARIChangeEvent]:
    """For overlapping date ranges, keep only the last event (last write wins).

    Events arriving in the same debounce window for the same date range
    represent successive updates — only the final value matters.
    """
    # Group by (date_from, date_to), preserve insertion order, keep last
    seen: Dict[tuple, ARIChangeEvent] = {}
    for ev in events:
        key = (_parse_date(ev.date_from), _parse_date(ev.date_to))
        seen[key] = ev  # last write wins
    return list(seen.values())


def _merge_date_ranges(events: List[ARIChangeEvent]) -> List[dict]:
    """Deduplicate overlapping ranges (last write wins), then merge consecutive
    date ranges with identical payloads into minimal range set."""
    if not events:
        return []

    # Step 1: Last-write-wins for identical date ranges
    deduped = _deduplicate_by_date_range(events)

    # Step 2: Sort by date_from and merge consecutive ranges with same payload
    sorted_events = sorted(deduped, key=lambda e: _parse_date(e.date_from))
    merged = []
    current = {
        "date_from": _parse_date(sorted_events[0].date_from),
        "date_to": _parse_date(sorted_events[0].date_to),
        "payload": sorted_events[0].payload,
    }

    for ev in sorted_events[1:]:
        ev_from = _parse_date(ev.date_from)
        ev_to = _parse_date(ev.date_to)
        payload_hash_current = compute_delta_hash(current["payload"])
        payload_hash_new = compute_delta_hash(ev.payload)

        if payload_hash_current == payload_hash_new and ev_from <= current["date_to"] + timedelta(days=1):
            current["date_to"] = max(current["date_to"], ev_to)
        else:
            merged.append(current)
            current = {
                "date_from": ev_from,
                "date_to": ev_to,
                "payload": ev.payload,
            }

    merged.append(current)
    return merged


def _apply_restriction_precedence(payloads: List[dict]) -> dict:
    """Apply restriction precedence rules: close > open, latest explicit wins."""
    result = {}
    for p in payloads:
        if "stop_sell" in p:
            if p["stop_sell"] is True:
                result["stop_sell"] = True
            elif "stop_sell" not in result:
                result["stop_sell"] = False
        for key in ("min_los", "max_los"):
            if key in p:
                result[key] = p[key]
        for key in ("cta", "ctd"):
            if key in p:
                result[key] = p[key]
    return result


def coalesce_events(
    coalescing_key: str,
    events: List[ARIChangeEvent],
    providers: List[str],
) -> List[dict]:
    """
    Coalesce a batch of events into per-provider change sets.

    Returns a list of change set dicts ready for upsert_change_set().
    """
    if not events:
        return []

    ref = events[0]
    event_type = ref.event_type

    # For restrictions, apply precedence rules
    if event_type == "restriction":
        merged_payload = _apply_restriction_precedence([e.payload for e in events])
        merged_ranges = [{
            "date_from": _parse_date(ref.date_from),
            "date_to": _parse_date(ref.date_to),
            "payload": merged_payload,
        }]
    else:
        # For availability/rate: last write wins, then merge date ranges
        merged_ranges = _merge_date_ranges(events)

    change_sets = []
    for provider in providers:
        for mr in merged_ranges:
            payload = mr["payload"]
            provider_key = coalescing_key.replace(
                f"{ref.tenant_id}|{ref.property_id}|",
                f"{ref.tenant_id}|{ref.property_id}|{provider}|",
            )
            cs = {
                "tenant_id": ref.tenant_id,
                "property_id": ref.property_id,
                "provider": provider,
                "coalescing_key": provider_key,
                "room_type_code": ref.room_type_code,
                "rate_plan_code": ref.rate_plan_code,
                "date_from": str(mr["date_from"]),
                "date_to": str(mr["date_to"]),
                "change_scope": event_type,
                "compacted_payload": payload,
                "provider_delta_hash": compute_outbound_delta_hash(
                    provider=provider,
                    property_id=ref.property_id,
                    room_type_code=ref.room_type_code,
                    rate_plan_code=ref.rate_plan_code or "",
                    date_from=str(mr["date_from"]),
                    date_to=str(mr["date_to"]),
                    payload=payload,
                ),
            }
            change_sets.append(cs)

    logger.info(
        f"Coalesced {len(events)} events → {len(change_sets)} change sets "
        f"for key={coalescing_key}"
    )
    return change_sets
