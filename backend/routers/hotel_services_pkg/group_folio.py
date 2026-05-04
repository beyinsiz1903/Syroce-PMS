"""Auto-split from hotel_services.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_op

from ._common import (
    GroupBulkPaymentRequest,
    GroupFolioMerge,
    GroupPaymentRequest,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()

@sub_router.post("/group-folio/merge")
async def merge_group_folios(
    data: GroupFolioMerge,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v101 DW
):
    """Merge multiple folios from a group into a master folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Verify master booking exists
    master = await db.bookings.find_one({"id": data.master_booking_id, "tenant_id": tid}, {"_id": 0})
    if not master:
        raise HTTPException(status_code=404, detail="Ana rezervasyon bulunamadi")

    merged_entries = []
    merged_payments = []
    total_transferred = 0

    for bid in data.merge_booking_ids:
        if bid == data.master_booking_id:
            continue

        source_booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not source_booking:
            continue

        # Transfer folio entries
        async for folio in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            new_entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": data.master_booking_id,
                "original_booking_id": bid,
                "description": f"[Oda {source_booking.get('room_number', '?')}] {folio.get('description', '')}",
                "category": folio.get("category", "transfer"),
                "amount": folio.get("amount", 0),
                "type": folio.get("type", "charge"),
                "merged_from": bid,
                "created_at": datetime.now(UTC).isoformat(),
                "merged_at": datetime.now(UTC).isoformat(),
            }
            await db.folios.insert_one(new_entry)
            new_entry.pop("_id", None)
            merged_entries.append(new_entry)
            total_transferred += folio.get("amount", 0)

        # Transfer payments if requested
        if data.merge_payments:
            async for payment in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
                new_payment = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tid,
                    "booking_id": data.master_booking_id,
                    "original_booking_id": bid,
                    "amount": payment.get("amount", 0),
                    "method": payment.get("method", "transfer"),
                    "payment_type": "transfer",
                    "reference": f"Grup birlestirme - Oda {source_booking.get('room_number', '?')}",
                    "merged_from": bid,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await db.payments.insert_one(new_payment)
                new_payment.pop("_id", None)
                merged_payments.append(new_payment)

        # Mark source booking folio as merged
        await db.bookings.update_one(
            {"id": bid, "tenant_id": tid},
            {"$set": {"folio_merged_to": data.master_booking_id, "folio_merged_at": datetime.now(UTC).isoformat()}}
        )

    # Log the merge
    merge_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "group_id": data.group_id,
        "master_booking_id": data.master_booking_id,
        "merged_booking_ids": data.merge_booking_ids,
        "total_entries_merged": len(merged_entries),
        "total_payments_merged": len(merged_payments),
        "total_amount_transferred": total_transferred,
        "merged_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.folio_merge_logs.insert_one(merge_log)
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

    booking_ids = group.get("booking_ids", [])
    bookings_data = []

    for bid in booking_ids:
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not booking:
            continue

        # Get folio summary
        folio_total = 0
        async for f in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            if f.get("type") != "payment":
                folio_total += f.get("amount", 0)

        payment_total = 0
        async for p in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            payment_total += p.get("amount", 0)

        bookings_data.append({
            "booking_id": bid,
            "guest_name": booking.get("guest_name", "-"),
            "room_number": booking.get("room_number", "-"),
            "accommodation_total": booking.get("total_amount", 0),
            "folio_charges": folio_total,
            "payments": payment_total,
            "balance": booking.get("total_amount", 0) + folio_total - payment_total,
            "folio_merged_to": booking.get("folio_merged_to"),
        })

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

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

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
        "guest_name": booking.get("guest_name", "-"),
        "room_number": booking.get("room_number", "-"),
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Record a bulk payment distributed across all active bookings in a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": data.group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    # Collect active (unmerged) bookings with positive balances
    active_bookings = []
    for bid in group.get("booking_ids", []):
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not booking or booking.get("folio_merged_to"):
            continue

        folio_total = 0
        async for f in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            if f.get("type") != "payment":
                folio_total += f.get("amount", 0)
        payment_total = 0
        async for p in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            payment_total += p.get("amount", 0)

        balance = booking.get("total_amount", 0) + folio_total - payment_total
        active_bookings.append({
            "booking_id": bid,
            "guest_name": booking.get("guest_name", "-"),
            "room_number": booking.get("room_number", "-"),
            "balance": balance,
        })

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
        {"$match": {
            "booking_id": {"$in": unique_booking_ids},
            "tenant_id": tid,
            "type": {"$ne": "payment"},
        }},
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
        total_balance += (
            (booking.get("total_amount") or 0)
            + folio_totals.get(bid, 0)
            - payment_totals.get(bid, 0)
        )

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


