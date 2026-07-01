"""CapX counter-offer state machine.

Inbound flow (webhook receiver):
  CapX → POST /api/webhooks/capx (event_type=counter_offer)
    → kaydet `capx_counter_offers` (status=pending)
    → operatöre bildirim (best-effort)

Outbound flow (admin endpoints):
  /api/capx/counter-offers/{id}/accept → status=accepted, CapX'e onay event push
  /api/capx/counter-offers/{id}/reject → status=rejected, CapX'e ret event push
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

COLLECTION = "capx_counter_offers"
ALLOWED_STATUSES = ("pending", "accepted", "rejected", "expired")


async def record_counter_offer(
    *,
    event_id: str,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> dict[str, Any]:
    """Webhook handler tarafından çağrılır. Idempotent: aynı event_id ikinci kez
    geldiğinde mevcut kaydı geri döner."""
    existing = await get_system_db()[COLLECTION].find_one({"event_id": event_id}, {"_id": 0})
    if existing:
        return {"counter_offer": existing, "duplicate": True}

    doc = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "tenant_id": tenant_id,
        "status": "pending",
        "pms_external_ref": payload.get("pms_external_ref"),
        "booking_id": payload.get("booking_id"),
        "guest_name": payload.get("guest_name"),
        "check_in": payload.get("check_in"),
        "check_out": payload.get("check_out"),
        "original_amount": payload.get("original_amount") or payload.get("amount"),
        "counter_amount": payload.get("counter_amount"),
        "currency": payload.get("currency", "TRY"),
        "expires_at": payload.get("expires_at"),
        "raw_payload": payload,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await get_system_db()[COLLECTION].insert_one(doc)
    doc.pop("_id", None)
    return {"counter_offer": doc, "duplicate": False}


async def list_counter_offers(
    *,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    if status:
        query["status"] = status
    items: list[dict[str, Any]] = []
    async for doc in get_system_db()[COLLECTION].find(query, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(doc)
    return items


async def get_counter_offer(offer_id: str) -> dict[str, Any] | None:
    return await get_system_db()[COLLECTION].find_one({"id": offer_id}, {"_id": 0})


async def transition(
    *,
    offer_id: str,
    new_status: str,
    actor_id: str,
    notes: str = "",
) -> dict[str, Any]:
    """Transition counter-offer between states. Returns updated doc.

    State rule: pending → accepted | rejected. expired-only via system.
    """
    if new_status not in ("accepted", "rejected"):
        raise ValueError(f"invalid target status: {new_status}")

    offer = await get_system_db()[COLLECTION].find_one({"id": offer_id})
    if not offer:
        raise LookupError(f"counter offer {offer_id} not found")
    if offer.get("status") != "pending":
        raise ValueError(f"only pending offers can transition (current={offer.get('status')})")

    now = datetime.now(UTC).isoformat()
    update = {
        "status": new_status,
        "updated_at": now,
        "decided_at": now,
        "decided_by": actor_id,
        "decision_notes": notes,
    }
    await get_system_db()[COLLECTION].update_one({"id": offer_id}, {"$set": update})
    return {**{k: v for k, v in offer.items() if k != "_id"}, **update}
