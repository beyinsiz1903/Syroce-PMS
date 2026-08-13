"""Auto-split from hotel_services.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_op
from security.encrypted_lookup import decrypt_guest_doc
from shared_kernel.pos_idem import ensure_compound_unique

from ._common import (
    GroupBulkPaymentRequest,
    GroupFolioMerge,
    GroupPaymentRequest,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()


async def _insert_merge_copy(collection, merge_key: str, document: dict) -> bool:
    """Insert a deterministic merge copy once, including under concurrent retries."""
    document["merge_key"] = merge_key
    try:
        result = await collection.update_one(
            {"tenant_id": document["tenant_id"], "merge_key": merge_key},
            {"$setOnInsert": document},
            upsert=True,
        )
    except DuplicateKeyError:
        return False
    return result.upserted_id is not None


def _guest_display_name(guest: dict | None, booking: dict) -> str:
    if guest:
        guest = decrypt_guest_doc(guest)
        name = guest.get("name") or " ".join(value for value in (guest.get("first_name"), guest.get("last_name")) if value).strip()
        if name:
            return name
    return booking.get("guest_name") or "-"


async def _load_group_booking_rows(tenant_id: str, booking_ids: list[str]) -> list[dict]:
    """Load group-folio rows with a constant number of tenant-scoped queries."""
    ordered_ids = list(dict.fromkeys(booking_id for booking_id in booking_ids if booking_id))
    if not ordered_ids:
        return []

    bookings = await db.bookings.find(
        {"id": {"$in": ordered_ids}, "tenant_id": tenant_id},
        {"_id": 0},
    ).to_list(len(ordered_ids))
    booking_map = {booking["id"]: booking for booking in bookings}

    guest_ids = list({booking["guest_id"] for booking in bookings if booking.get("guest_id")})
    room_ids = list({booking["room_id"] for booking in bookings if booking.get("room_id")})

    guest_map: dict[str, dict] = {}
    if guest_ids:
        guests = await db.guests.find(
            {"id": {"$in": guest_ids}, "tenant_id": tenant_id},
            {"_id": 0},
        ).to_list(len(guest_ids))
        guest_map = {guest["id"]: guest for guest in guests}

    room_map: dict[str, str] = {}
    if room_ids:
        rooms = await db.rooms.find(
            {"id": {"$in": room_ids}, "tenant_id": tenant_id},
            {"_id": 0, "id": 1, "room_number": 1},
        ).to_list(len(room_ids))
        room_map = {room["id"]: room.get("room_number") or "-" for room in rooms}

    folio_totals = dict.fromkeys(ordered_ids, 0)
    folios = await db.folios.find(
        {
            "booking_id": {"$in": ordered_ids},
            "tenant_id": tenant_id,
            "type": {"$ne": "payment"},
        },
        {"_id": 0, "booking_id": 1, "amount": 1},
    ).to_list(100000)
    for folio in folios:
        booking_id = folio.get("booking_id")
        if booking_id in folio_totals:
            folio_totals[booking_id] += folio.get("amount") or 0

    payment_totals = dict.fromkeys(ordered_ids, 0)
    payments = await db.payments.find(
        {"booking_id": {"$in": ordered_ids}, "tenant_id": tenant_id},
        {"_id": 0, "booking_id": 1, "amount": 1},
    ).to_list(100000)
    for payment in payments:
        booking_id = payment.get("booking_id")
        if booking_id in payment_totals:
            payment_totals[booking_id] += payment.get("amount") or 0

    rows = []
    for booking_id in ordered_ids:
        booking = booking_map.get(booking_id)
        if not booking:
            continue
        accommodation_total = booking.get("total_amount") or 0
        folio_total = folio_totals[booking_id]
        payment_total = payment_totals[booking_id]
        rows.append(
            {
                "booking": booking,
                "booking_id": booking_id,
                "guest_name": _guest_display_name(guest_map.get(booking.get("guest_id")), booking),
                "room_number": booking.get("room_number") or room_map.get(booking.get("room_id"), "-"),
                "accommodation_total": accommodation_total,
                "folio_charges": folio_total,
                "payments": payment_total,
                "balance": accommodation_total + folio_total - payment_total,
                "folio_merged_to": booking.get("folio_merged_to"),
            }
        )
    return rows


@sub_router.post("/group-folio/merge")
async def merge_group_folios(
    data: GroupFolioMerge,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v101 DW
):
    """Merge multiple folios from a group into a master folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": data.group_id, "tenant_id": tid}, {"_id": 0, "booking_ids": 1})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    group_booking_ids = set(group.get("booking_ids") or [])
    requested_booking_ids = set(data.merge_booking_ids) | {data.master_booking_id}
    if not requested_booking_ids.issubset(group_booking_ids):
        raise HTTPException(status_code=400, detail="Rezervasyonlardan biri bu gruba ait degil")

    master = await db.bookings.find_one({"id": data.master_booking_id, "tenant_id": tid}, {"_id": 0})
    if not master:
        raise HTTPException(status_code=404, detail="Ana rezervasyon bulunamadi")
    if master.get("folio_merged_to") or master.get("folio_merge_claim"):
        raise HTTPException(status_code=409, detail="Birlestirilmis bir folio ana folio olamaz")

    await ensure_compound_unique(
        db.folios,
        [("tenant_id", 1), ("merge_key", 1)],
        partial_filter={"merge_key": {"$type": "string"}},
        name="ux_group_folio_merge_key",
    )
    await ensure_compound_unique(
        db.payments,
        [("tenant_id", 1), ("merge_key", 1)],
        partial_filter={"merge_key": {"$type": "string"}},
        name="ux_group_payment_merge_key",
    )
    await ensure_compound_unique(
        db.folio_merge_logs,
        [("tenant_id", 1), ("merge_key", 1)],
        partial_filter={"merge_key": {"$type": "string"}},
        name="ux_group_folio_merge_log_key",
    )

    merged_entries = []
    merged_payments = []

    for bid in dict.fromkeys(data.merge_booking_ids):
        if bid == data.master_booking_id:
            continue

        source_booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not source_booking:
            raise HTTPException(status_code=404, detail="Kaynak rezervasyon bulunamadi")
        if source_booking.get("folio_merged_to") == data.master_booking_id:
            continue
        if source_booking.get("folio_merged_to"):
            raise HTTPException(status_code=409, detail="Kaynak folio baska bir rezervasyona birlestirilmis")

        claim_key = f"group-folio-claim:{data.group_id}:{data.master_booking_id}:{bid}"
        await db.bookings.update_one(
            {
                "id": bid,
                "tenant_id": tid,
                "$and": [
                    {"$or": [{"folio_merged_to": {"$exists": False}}, {"folio_merged_to": None}]},
                    {"$or": [{"folio_merge_claim": {"$exists": False}}, {"folio_merge_claim": claim_key}]},
                ],
            },
            {"$set": {"folio_merge_claim": claim_key}},
        )
        claimed_booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if claimed_booking and claimed_booking.get("folio_merged_to") == data.master_booking_id:
            continue
        if not claimed_booking or claimed_booking.get("folio_merge_claim") != claim_key:
            raise HTTPException(status_code=409, detail="Kaynak folio baska bir birlestirme islemi tarafindan kullaniliyor")

        room_number = source_booking.get("room_number")
        if not room_number and source_booking.get("room_id"):
            room = await db.rooms.find_one(
                {"id": source_booking["room_id"], "tenant_id": tid},
                {"_id": 0, "room_number": 1},
            )
            room_number = room.get("room_number") if room else None

        async for folio in db.folios.find(
            {"booking_id": bid, "tenant_id": tid, "type": {"$ne": "payment"}},
        ):
            source_folio_id = str(folio.get("id") or folio.get("_id"))
            if not source_folio_id or source_folio_id == "None":
                raise HTTPException(status_code=409, detail="Kaynak folio kimligi gecersiz")
            merge_key = f"group-folio:{data.master_booking_id}:{bid}:{source_folio_id}"
            new_entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": data.master_booking_id,
                "original_booking_id": bid,
                "description": f"[Oda {room_number or '?'}] {folio.get('description', '')}",
                "category": folio.get("category", "transfer"),
                "amount": folio.get("amount", 0),
                "type": folio.get("type", "charge"),
                "merged_from": bid,
                "created_at": datetime.now(UTC).isoformat(),
                "merged_at": datetime.now(UTC).isoformat(),
            }
            if await _insert_merge_copy(db.folios, merge_key, new_entry):
                new_entry.pop("_id", None)
                merged_entries.append(new_entry)

        if data.merge_payments:
            async for payment in db.payments.find({"booking_id": bid, "tenant_id": tid}):
                source_payment_id = str(payment.get("id") or payment.get("_id"))
                if not source_payment_id or source_payment_id == "None":
                    raise HTTPException(status_code=409, detail="Kaynak odeme kimligi gecersiz")
                merge_key = f"group-payment:{data.master_booking_id}:{bid}:{source_payment_id}"
                new_payment = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tid,
                    "booking_id": data.master_booking_id,
                    "original_booking_id": bid,
                    "amount": payment.get("amount", 0),
                    "method": payment.get("method", "transfer"),
                    "payment_type": "transfer",
                    "reference": f"Grup birlestirme - Oda {room_number or '?'}",
                    "merged_from": bid,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                if await _insert_merge_copy(db.payments, merge_key, new_payment):
                    new_payment.pop("_id", None)
                    merged_payments.append(new_payment)

        await db.bookings.update_one(
            {
                "id": bid,
                "tenant_id": tid,
                "folio_merge_claim": claim_key,
                "$or": [{"folio_merged_to": {"$exists": False}}, {"folio_merged_to": None}],
            },
            {
                "$set": {"folio_merged_to": data.master_booking_id, "folio_merged_at": datetime.now(UTC).isoformat()},
                "$unset": {"folio_merge_claim": ""},
            },
        )

    operation_source_ids = sorted(set(data.merge_booking_ids) - {data.master_booking_id})
    stored_entries = await db.folios.find(
        {
            "tenant_id": tid,
            "booking_id": data.master_booking_id,
            "merged_from": {"$in": operation_source_ids},
            "merge_key": {"$type": "string"},
        },
        {"_id": 0, "amount": 1},
    ).to_list(100000)
    stored_payments = await db.payments.find(
        {
            "tenant_id": tid,
            "booking_id": data.master_booking_id,
            "merged_from": {"$in": operation_source_ids},
            "merge_key": {"$type": "string"},
        },
        {"_id": 0, "amount": 1},
    ).to_list(100000)
    log_merge_key = f"group-merge:{data.group_id}:{data.master_booking_id}:{','.join(operation_source_ids)}"
    merge_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "merge_key": log_merge_key,
        "group_id": data.group_id,
        "master_booking_id": data.master_booking_id,
        "merged_booking_ids": operation_source_ids,
        "total_entries_merged": len(stored_entries),
        "total_payments_merged": len(stored_payments),
        "total_amount_transferred": sum(entry.get("amount") or 0 for entry in stored_entries),
        "merged_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await _insert_merge_copy(db.folio_merge_logs, log_merge_key, merge_log)
    stored_merge_log = await db.folio_merge_logs.find_one(
        {"tenant_id": tid, "merge_key": log_merge_key},
        {"_id": 0},
    )
    merge_log = stored_merge_log or merge_log
    merge_log.pop("_id", None)

    return {
        "success": True,
        "merge_log": merge_log,
        "merged_entries_count": len(merged_entries),
        "merged_payments_count": len(merged_payments),
    }


@sub_router.get("/group-folio/{group_id}")
async def get_group_folio_status(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get folio status for a group booking."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Get group
    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    bookings_data = await _load_group_booking_rows(tid, group.get("booking_ids", []))
    for row in bookings_data:
        row.pop("booking", None)

    # Check merge logs
    merge_logs = []
    async for log in db.folio_merge_logs.find({"group_id": group_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        merge_logs.append(log)

    return {
        "group": group,
        "bookings": bookings_data,
        "merge_logs": merge_logs,
    }


# ═══════════════════════════════════════════════════
# 7. GROUP FOLIO - BOOKING DETAIL & GROUP PAYMENT
# ═══════════════════════════════════════════════════


@sub_router.get("/group-folio/{group_id}/booking/{booking_id}")
async def get_group_booking_folio_detail(
    group_id: str,
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed folio line items for a booking within a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking_rows = await _load_group_booking_rows(tid, [booking_id])
    if not booking_rows:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    booking_row = booking_rows[0]
    booking = booking_row["booking"]

    charges = []
    async for c in db.folio_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        charges.append(c)

    folios = []
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        folios.append(f)

    payments = []
    async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        payments.append(p)

    extra_charges = []
    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        extra_charges.append(ec)

    return {
        "booking_id": booking_id,
        "guest_name": booking_row["guest_name"],
        "room_number": booking_row["room_number"],
        "check_in": booking.get("check_in"),
        "check_out": booking.get("check_out"),
        "status": booking.get("status", "confirmed"),
        "total_amount": booking.get("total_amount", 0),
        "charges": charges,
        "folios": folios,
        "payments": payments,
        "extra_charges": extra_charges,
    }


@sub_router.post("/group-folio/payment")
async def record_group_payment(
    data: GroupPaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    """Record a payment for a booking within a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": data.booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": data.booking_id,
        "amount": data.amount,
        "method": data.method,
        "payment_type": "group_payment",
        "reference": data.reference or f"Grup odeme - {data.group_id[:8]}",
        "recorded_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.payments.insert_one(payment)
    payment.pop("_id", None)

    return {"success": True, "payment": payment}


@sub_router.post("/group-folio/bulk-payment")
async def record_group_bulk_payment(
    data: GroupBulkPaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),
):
    """Record a bulk payment distributed across all active bookings in a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": data.group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    # Collect active (unmerged) bookings with positive balances.
    active_bookings = [row for row in await _load_group_booking_rows(tid, group.get("booking_ids", [])) if not row.get("folio_merged_to")]

    if not active_bookings:
        raise HTTPException(status_code=400, detail="Aktif rezervasyon bulunamadi")

    # Calculate distribution
    total_positive_balance = sum(max(b["balance"], 0) for b in active_bookings)
    remaining = data.total_amount
    payments_created = []

    for i, ab in enumerate(active_bookings):
        if remaining <= 0:
            break

        if data.distribution == "equal":
            share = round(data.total_amount / len(active_bookings), 2)
        elif data.distribution == "balance_only":
            if ab["balance"] <= 0:
                continue
            share = min(ab["balance"], remaining)
        else:  # proportional
            if total_positive_balance > 0 and ab["balance"] > 0:
                share = round(data.total_amount * (ab["balance"] / total_positive_balance), 2)
            else:
                share = round(data.total_amount / len(active_bookings), 2)

        # Last booking gets the remainder to avoid rounding issues
        if i == len(active_bookings) - 1 and data.distribution != "balance_only":
            share = remaining

        share = min(share, remaining)
        if share <= 0:
            continue

        payment = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": ab["booking_id"],
            "amount": share,
            "method": data.method,
            "payment_type": "group_bulk_payment",
            "reference": data.reference or f"Toplu grup odeme - Oda {ab['room_number']}",
            "recorded_by": current_user.name,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.payments.insert_one(payment)
        payment.pop("_id", None)
        payments_created.append({**payment, "guest_name": ab["guest_name"]})
        remaining = round(remaining - share, 2)

    return {
        "success": True,
        "total_distributed": round(data.total_amount - remaining, 2),
        "payments_count": len(payments_created),
        "payments": payments_created,
    }


@sub_router.get("/group-folio-summary")
async def get_group_folio_summary(
    current_user: User = Depends(get_current_user),
):
    """Get summary statistics for all group folios.

    Optimized: replaces N+1 per-booking find/find_one loops with three bulk
    aggregations against `$in: booking_ids`.  Previously took ~9.3s on tenants
    with many group bookings — now sub-second.
    """
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    groups: list[dict] = []
    async for g in db.group_bookings.find({"tenant_id": tid}, {"_id": 0}).limit(2000):
        groups.append(g)

    total_groups = len(groups)
    active_groups = sum(1 for g in groups if g.get("status") == "active")

    all_booking_ids: list[str] = []
    for g in groups:
        all_booking_ids.extend(g.get("booking_ids", []) or [])
    # Deduplicate while preserving order
    seen = set()
    unique_booking_ids: list[str] = []
    for bid in all_booking_ids:
        if bid and bid not in seen:
            seen.add(bid)
            unique_booking_ids.append(bid)
    total_bookings = len(all_booking_ids)

    if not unique_booking_ids:
        merge_log_count = await db.folio_merge_logs.count_documents({"tenant_id": tid})
        return {
            "total_groups": total_groups,
            "active_groups": active_groups,
            "total_bookings": 0,
            "total_balance": 0,
            "merged_folios": 0,
            "merge_operations": merge_log_count,
        }

    # Bulk fetch all bookings (1 query)
    bookings_map: dict[str, dict] = {}
    async for b in db.bookings.find(
        {"id": {"$in": unique_booking_ids}, "tenant_id": tid},
        {"_id": 0, "id": 1, "total_amount": 1, "folio_merged_to": 1},
    ):
        bookings_map[b["id"]] = b

    # Bulk-aggregate folio totals (excluding payments) (1 query)
    folio_totals: dict[str, float] = {}
    folio_pipeline = [
        {
            "$match": {
                "booking_id": {"$in": unique_booking_ids},
                "tenant_id": tid,
                "type": {"$ne": "payment"},
            }
        },
        {"$group": {"_id": "$booking_id", "total": {"$sum": "$amount"}}},
    ]
    async for doc in db.folios.aggregate(folio_pipeline):
        folio_totals[doc["_id"]] = doc.get("total") or 0

    # Bulk-aggregate payment totals (1 query)
    payment_totals: dict[str, float] = {}
    payment_pipeline = [
        {"$match": {"booking_id": {"$in": unique_booking_ids}, "tenant_id": tid}},
        {"$group": {"_id": "$booking_id", "total": {"$sum": "$amount"}}},
    ]
    async for doc in db.payments.aggregate(payment_pipeline):
        payment_totals[doc["_id"]] = doc.get("total") or 0

    total_balance = 0.0
    merged_count = 0
    for bid in all_booking_ids:
        booking = bookings_map.get(bid)
        if not booking:
            continue
        if booking.get("folio_merged_to"):
            merged_count += 1
        total_balance += (booking.get("total_amount") or 0) + folio_totals.get(bid, 0) - payment_totals.get(bid, 0)

    merge_log_count = await db.folio_merge_logs.count_documents({"tenant_id": tid})

    return {
        "total_groups": total_groups,
        "active_groups": active_groups,
        "total_bookings": total_bookings,
        "total_balance": total_balance,
        "merged_folios": merged_count,
        "merge_operations": merge_log_count,
    }


# ═══════════════════════════════════════════════════
# 10. RESERVATION CANCELLATION
# ═══════════════════════════════════════════════════
