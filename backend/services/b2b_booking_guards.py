"""
B2B booking guards (T003) — HARD, race-safe allotment + credit enforcement for the
B2B/agency reservation create path ONLY.

Both controls are OPT-IN (configured on the agency's approved contract, surfaced
by ``services.b2b_partner_contract``): when unconfigured the agency books exactly
as before (uncapped, pilot_drift=0, back-compatible). When configured they are
enforced atomically so concurrent bookings can never oversell an allotment block
or push an agency past its credit limit.

Atomicity model (no in-process / Redis lock — those are not crash-safe):
  - ALLOTMENT: a single ``find_one_and_update`` on the contract doc increments the
    matching ``allotments[]`` element's ``rooms_used`` ONLY when the query-level
    ``$expr`` guard proves ``rooms_used + room_nights <= rooms_allocated`` against
    the document's live state (re-evaluated under Mongo's per-document write lock).
    Guard fail => no match => returns None => reject. No oversell window.
  - CREDIT: a single ``find_one_and_update`` on the agency doc increments
    ``current_debt`` ONLY when ``current_debt + amount <= credit_limit``. Same
    write-lock re-evaluation => no over-credit window.

Saga compensation: the caller reserves allotment then credit BEFORE persisting the
booking; if anything afterwards fails (incl. ``create_booking_atomic`` conflict),
the caller calls the matching ``release_*`` to roll the counters back. Releases are
clamped (``>=`` filter) so a counter can never be driven negative.

Allotment is consumed in ROOM-NIGHT units (classic OTA / channel-manager model):
one B2B reservation consumes ``rooms * nights`` from the matching block, so
``rooms_allocated``/``rooms_used`` are a room-NIGHTS quota for the (room_type,
period). A single-room 3-night booking consumes 3. ``nights`` is derived from the
stay dates inside ``reserve_allotment`` (upstream validates check_out > check_in).
"""

from __future__ import annotations

import logging
from datetime import date

from pymongo import ReturnDocument

from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)


class GuardRejection(Exception):
    """A business reject from a hard guard (allotment exhausted / credit exceeded).

    Carries the HTTP status + Turkish detail the booking route should surface.
    Deterministic by design so the idempotency layer can cache it as failed_final.
    """

    def __init__(self, code: str, detail: str, status_code: int):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def _match_allotment(allotments: list[dict], room_type: str, check_in: str, check_out: str) -> dict | None:
    """Return the allotment entry whose period fully covers the stay for this room
    type, or None when no block applies (=> uncapped for this booking).

    Dates are ``YYYY-MM-DD`` strings; lexicographic order == chronological order.
    """
    for a in allotments or []:
        if a.get("room_type") != room_type:
            continue
        ps, pe = a.get("period_start"), a.get("period_end")
        if not ps or not pe:
            continue
        if ps <= check_in and pe >= check_out:
            return a
    return None


def _nights(check_in: str, check_out: str) -> int:
    """Number of nights for a ``YYYY-MM-DD`` stay (classic OTA room-night unit).

    ``check_out`` is the departure date, so ``nights = (check_out - check_in).days``.
    Upstream booking validation already guarantees ``check_out > check_in`` before
    this guard runs; a malformed date here would (correctly) fail the booking via
    the caller's saga ``except`` rather than silently bypass the cap.
    """
    return (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days


async def reserve_allotment(snapshot, room_type: str, check_in: str, check_out: str, rooms: int = 1):
    """Atomically claim ``rooms`` from the matching contract allotment block.

    Returns:
      - None  : no allotment block applies (uncapped) — nothing to release.
      - dict  : a release handle on success.
    Raises:
      - GuardRejection(allotment_exhausted, 409) : block exists but is full.
    """
    if not snapshot.has_contract or not snapshot.contract_id:
        return None
    entry = _match_allotment(snapshot.allotments, room_type, check_in, check_out)
    if entry is None:
        return None
    if rooms <= 0:
        return None
    # Classic OTA room-night consumption: a stay claims (rooms * nights) from the
    # block — rooms_allocated/rooms_used are a room-NIGHTS quota. nights is derived
    # from the stay dates; upstream booking validation guarantees check_out > check_in.
    nights = _nights(check_in, check_out)
    units = rooms * nights
    if units <= 0:
        return None

    ps = entry.get("period_start")
    pe = entry.get("period_end")
    sysdb = get_system_db()
    res = await sysdb.agency_contracts.find_one_and_update(
        {
            "id": snapshot.contract_id,
            "tenant_id": snapshot.tenant_id,
            "status": "approved",
            # Capacity guard re-evaluated under the doc write lock: at least one
            # element matching (room_type, period) must still have room for `units`
            # (room-nights).
            "$expr": {
                "$gt": [
                    {
                        "$size": {
                            "$filter": {
                                "input": {"$ifNull": ["$allotments", []]},
                                "as": "a",
                                "cond": {
                                    "$and": [
                                        {"$eq": ["$$a.room_type", room_type]},
                                        {"$eq": ["$$a.period_start", ps]},
                                        {"$eq": ["$$a.period_end", pe]},
                                        {
                                            "$lte": [
                                                {"$add": [{"$ifNull": ["$$a.rooms_used", 0]}, units]},
                                                {"$ifNull": ["$$a.rooms_allocated", 0]},
                                            ]
                                        },
                                    ]
                                },
                            }
                        }
                    },
                    0,
                ]
            },
        },
        {"$inc": {"allotments.$[elem].rooms_used": units}},
        array_filters=[
            {
                "elem.room_type": room_type,
                "elem.period_start": ps,
                "elem.period_end": pe,
            }
        ],
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "id": 1},
    )
    if res is None:
        raise GuardRejection(
            "allotment_exhausted",
            f"Kontenjan dolu: '{room_type}' oda tipi icin sozlesme kontenjani tukendi",
            409,
        )
    return {
        "kind": "allotment",
        "contract_id": snapshot.contract_id,
        "tenant_id": snapshot.tenant_id,
        "room_type": room_type,
        "period_start": ps,
        "period_end": pe,
        "rooms": rooms,
        "nights": nights,
        "units": units,
    }


async def release_allotment(handle: dict | None) -> None:
    """Compensate a prior ``reserve_allotment`` (clamped so it can't go negative)."""
    if not handle:
        return
    # Release the same room-NIGHT units that were reserved (back-compat fallback to
    # the legacy room-count handle shape if an in-flight pre-upgrade handle exists).
    units = handle.get("units", handle.get("rooms", 1))
    sysdb = get_system_db()
    try:
        await sysdb.agency_contracts.update_one(
            {"id": handle["contract_id"], "tenant_id": handle["tenant_id"]},
            {"$inc": {"allotments.$[elem].rooms_used": -units}},
            array_filters=[
                {
                    "elem.room_type": handle["room_type"],
                    "elem.period_start": handle["period_start"],
                    "elem.period_end": handle["period_end"],
                    "elem.rooms_used": {"$gte": units},
                }
            ],
        )
    except Exception:  # noqa: BLE001 — compensation must never mask the original error
        logger.exception("release_allotment failed (counter may need manual reconcile): %s", handle)


async def reserve_credit(snapshot, amount: float):
    """Atomically claim ``amount`` of the agency's credit line.

    Returns:
      - None  : no credit limit configured (uncapped) or amount<=0 — nothing to release.
      - dict  : a release handle on success.
    Raises:
      - GuardRejection(credit_exceeded, 402) : limit configured and would be exceeded.
    """
    if snapshot.credit_limit is None:
        return None
    if amount is None or amount <= 0:
        return None

    sysdb = get_system_db()
    res = await sysdb.agencies.find_one_and_update(
        {
            "id": snapshot.agency_id,
            # Tenant-scope the credit mutation: agency ids are unique within a
            # tenant, so an id-only filter could (in principle) match a different
            # tenant's agency. Fail-closed isolation — never touch another tenant's
            # current_debt counter.
            "tenant_id": snapshot.tenant_id,
            "$expr": {
                "$lte": [
                    {"$add": [{"$ifNull": ["$current_debt", 0]}, amount]},
                    snapshot.credit_limit,
                ]
            },
        },
        {"$inc": {"current_debt": amount}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "current_debt": 1},
    )
    if res is None:
        raise GuardRejection(
            "credit_exceeded",
            "Kredi limiti asildi: acente icin tanimli kredi limiti yetersiz",
            402,
        )
    return {"kind": "credit", "agency_id": snapshot.agency_id, "tenant_id": snapshot.tenant_id, "amount": amount}


async def release_credit(handle: dict | None) -> None:
    """Compensate a prior ``reserve_credit`` (clamped so it can't go negative)."""
    if not handle:
        return
    amount = handle.get("amount", 0)
    if amount <= 0:
        return
    sysdb = get_system_db()
    try:
        await sysdb.agencies.update_one(
            {"id": handle["agency_id"], "tenant_id": handle["tenant_id"], "current_debt": {"$gte": amount}},
            {"$inc": {"current_debt": -amount}},
        )
    except Exception:  # noqa: BLE001 — compensation must never mask the original error
        logger.exception("release_credit failed (counter may need manual reconcile): %s", handle)
