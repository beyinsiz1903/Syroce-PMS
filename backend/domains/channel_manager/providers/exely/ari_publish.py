"""Publish Exely ARI mutations into the canonical durable outbox."""

from __future__ import annotations

from datetime import date
from typing import Any

from domains.channel_manager.ari.events import ARIChangeEvent
from domains.channel_manager.ari.outbound_service import publish_ari_event


async def enqueue_exely_ari_update(
    tenant_id: str,
    property_id: str,
    room_type_code: str,
    rate_plan_code: str,
    start_date: str,
    end_date: str,
    *,
    source_service: str,
    availability: int | None = None,
    rate_amount: float | None = None,
    currency: str = "TRY",
    stop_sell: bool | None = None,
    min_los: int | None = None,
    min_los_arrival: int | None = None,
    max_los: int | None = None,
    cta: bool | None = None,
    ctd: bool | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    operations = (
        ("availability", "availability", availability, {"availability": availability}),
        ("rate", "rate", rate_amount, {"base_rate": rate_amount, "currency": currency}),
        ("restriction", "stop_sell", stop_sell, {"stop_sell": stop_sell}),
        ("restriction", "min_los", min_los, {"min_los": min_los}),
        ("restriction", "min_los_arrival", min_los_arrival, {"min_los_arrival": min_los_arrival}),
        ("restriction", "max_los", max_los, {"max_los": max_los}),
        ("restriction", "cta", cta, {"cta": cta}),
        ("restriction", "ctd", ctd, {"ctd": ctd}),
    )
    queued = []
    for event_type, operation, value, payload in operations:
        if value is None:
            continue
        event = ARIChangeEvent(
            tenant_id=tenant_id,
            property_id=property_id,
            source_service=source_service,
            event_type=event_type,
            room_type_code=room_type_code,
            rate_plan_code=rate_plan_code,
            date_from=date.fromisoformat(start_date),
            date_to=date.fromisoformat(end_date),
            payload={"operation": operation, **payload},
            actor_id=actor_id,
            target_provider="exely",
        )
        queued.append(await publish_ari_event(event))
    return {
        "accepted": bool(queued),
        "delivery_state": "queued" if queued else "blocked",
        "queued_operation_count": len(queued),
        "provider_write_count": 0,
    }
