"""
Travel Agent AR/AP Router
=========================
Endpoints for tracking agency receivables, payables, commissions,
payment plans, aging reports, and transaction history.

All endpoints under /api/agent-arap/
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/agent-arap", tags=["travel-agent-arap"])


class RecordPaymentRequest(BaseModel):
    agency_id: str
    amount: float = Field(..., gt=0)
    payment_method: str = "bank_transfer"
    reference: str = ""
    notes: str = ""


class CreatePaymentPlanRequest(BaseModel):
    agency_id: str
    total_amount: float = Field(..., gt=0)
    installments: int = Field(..., ge=2, le=24)
    start_date: str
    notes: str = ""


class UpdatePaymentPlanInstallment(BaseModel):
    plan_id: str
    installment_index: int = Field(..., ge=0)
    paid: bool = True
    payment_reference: str = ""


async def _get_agency_ledger(tenant_id: str, agency_id: str | None = None) -> list[dict]:
    match = {"tenant_id": tenant_id}
    if agency_id:
        match["id"] = agency_id

    agencies = await db.agencies.find(
        {**match, "status": {"$ne": "deleted"}},
    ).to_list(500)

    results = []
    for agency in agencies:
        aid = agency["id"]

        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "agency_id": aid, "status": {"$nin": ["cancelled"]}},
            {"_id": 0, "total_amount": 1, "check_in": 1, "check_out": 1, "status": 1, "created_at": 1},
        ).to_list(5000)

        total_bookings_revenue = sum(b.get("total_amount", 0) for b in bookings)
        commission_rate = agency.get("commission_rate", 10) / 100
        total_commission_owed = round(total_bookings_revenue * commission_rate, 2)

        txns = await db.agency_transactions.find(
            {"tenant_id": tenant_id, "agency_id": aid},
        ).to_list(5000)

        total_paid = sum(t.get("amount", 0) for t in txns if t.get("type") == "payment")
        total_adjustments = sum(t.get("amount", 0) for t in txns if t.get("type") == "adjustment")

        balance = round(total_commission_owed - total_paid + total_adjustments, 2)

        oldest_unpaid = None
        days_outstanding = 0
        for b in sorted(bookings, key=lambda x: x.get("created_at", "")):
            if b.get("status") in ("confirmed", "guaranteed", "checked_out"):
                oldest_unpaid = b.get("created_at", "")
                if oldest_unpaid:
                    try:
                        od = datetime.fromisoformat(oldest_unpaid.replace("Z", "+00:00"))
                        days_outstanding = (datetime.now(UTC) - od).days
                    except (ValueError, TypeError):
                        pass
                break

        plans = await db.agency_payment_plans.find(
            {"tenant_id": tenant_id, "agency_id": aid, "status": {"$ne": "cancelled"}},
        ).to_list(100)
        active_plans = [p for p in plans if p.get("status") == "active"]

        results.append({
            "agency_id": aid,
            "agency_name": agency.get("name", ""),
            "contact_name": agency.get("contact_name", ""),
            "contact_email": agency.get("contact_email", ""),
            "contact_phone": agency.get("contact_phone", ""),
            "commission_rate": agency.get("commission_rate", 10),
            "status": agency.get("status", "active"),
            "total_bookings": len(bookings),
            "total_bookings_revenue": total_bookings_revenue,
            "total_commission_owed": total_commission_owed,
            "total_paid": round(total_paid, 2),
            "total_adjustments": round(total_adjustments, 2),
            "balance": balance,
            "balance_type": "receivable" if balance >= 0 else "payable",
            "days_outstanding": days_outstanding,
            "oldest_unpaid_date": oldest_unpaid,
            "active_payment_plans": len(active_plans),
            "last_payment_date": max(
                (t.get("created_at", "") for t in txns if t.get("type") == "payment"),
                default=None,
            ),
        })

    return results


@router.get("/summary")
async def get_summary(current_user: User = Depends(get_current_user)):
    ledger = await _get_agency_ledger(current_user.tenant_id)

    total_receivable = sum(a["balance"] for a in ledger if a["balance"] > 0)
    total_payable = abs(sum(a["balance"] for a in ledger if a["balance"] < 0))
    total_commission = sum(a["total_commission_owed"] for a in ledger)
    total_paid = sum(a["total_paid"] for a in ledger)
    total_bookings_revenue = sum(a["total_bookings_revenue"] for a in ledger)

    overdue_30 = sum(1 for a in ledger if a["days_outstanding"] > 30 and a["balance"] > 0)
    overdue_60 = sum(1 for a in ledger if a["days_outstanding"] > 60 and a["balance"] > 0)
    overdue_90 = sum(1 for a in ledger if a["days_outstanding"] > 90 and a["balance"] > 0)

    return {
        "total_agencies": len(ledger),
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
        "net_balance": round(total_receivable - total_payable, 2),
        "total_commission_earned": round(total_commission, 2),
        "total_paid": round(total_paid, 2),
        "total_bookings_revenue": round(total_bookings_revenue, 2),
        "collection_rate": round((total_paid / total_commission * 100), 1) if total_commission > 0 else 0,
        "overdue_30_count": overdue_30,
        "overdue_60_count": overdue_60,
        "overdue_90_count": overdue_90,
        "agencies": ledger,
    }


@router.get("/aging")
async def get_aging_report(current_user: User = Depends(get_current_user)):
    ledger = await _get_agency_ledger(current_user.tenant_id)

    buckets = {"current": [], "30_days": [], "60_days": [], "90_days": [], "over_90": []}
    for a in ledger:
        if a["balance"] <= 0:
            continue
        d = a["days_outstanding"]
        if d <= 30:
            buckets["current"].append(a)
        elif d <= 60:
            buckets["30_days"].append(a)
        elif d <= 90:
            buckets["60_days"].append(a)
        elif d <= 120:
            buckets["90_days"].append(a)
        else:
            buckets["over_90"].append(a)

    return {
        "current": {
            "count": len(buckets["current"]),
            "total": round(sum(a["balance"] for a in buckets["current"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["current"]],
        },
        "30_days": {
            "count": len(buckets["30_days"]),
            "total": round(sum(a["balance"] for a in buckets["30_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["30_days"]],
        },
        "60_days": {
            "count": len(buckets["60_days"]),
            "total": round(sum(a["balance"] for a in buckets["60_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["60_days"]],
        },
        "90_days": {
            "count": len(buckets["90_days"]),
            "total": round(sum(a["balance"] for a in buckets["90_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["90_days"]],
        },
        "over_90": {
            "count": len(buckets["over_90"]),
            "total": round(sum(a["balance"] for a in buckets["over_90"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["over_90"]],
        },
    }


@router.get("/transactions/{agency_id}")
async def get_agency_transactions(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")

    txns = await db.agency_transactions.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
    ).sort("created_at", -1).to_list(500)

    for t in txns:
        t.pop("_id", None)

    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
        {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(500)

    commission_rate = agency.get("commission_rate", 10) / 100
    commission_entries = []
    for b in bookings:
        commission_entries.append({
            "id": f"comm-{b['id']}",
            "type": "commission",
            "booking_id": b["id"],
            "guest_name": b.get("guest_name", ""),
            "check_in": b.get("check_in", ""),
            "check_out": b.get("check_out", ""),
            "booking_amount": b.get("total_amount", 0),
            "amount": round(b.get("total_amount", 0) * commission_rate, 2),
            "created_at": b.get("created_at", ""),
        })

    return {
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "commission_rate": agency.get("commission_rate", 10),
        "transactions": txns,
        "commission_entries": commission_entries,
    }


@router.post("/payment")
async def record_payment(
    req: RecordPaymentRequest,
    current_user: User = Depends(get_current_user),
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": req.agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")

    txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "type": "payment",
        "amount": req.amount,
        "payment_method": req.payment_method,
        "reference": req.reference,
        "notes": req.notes,
        "recorded_by": current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.agency_transactions.insert_one(txn)
    txn.pop("_id", None)
    return {"success": True, "transaction": txn}


@router.get("/payment-plans")
async def list_payment_plans(
    agency_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    match: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if agency_id:
        match["agency_id"] = agency_id

    plans = await db.agency_payment_plans.find(match).sort("created_at", -1).to_list(200)
    for p in plans:
        p.pop("_id", None)

    return plans


@router.post("/payment-plans")
async def create_payment_plan(
    req: CreatePaymentPlanRequest,
    current_user: User = Depends(get_current_user),
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": req.agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")

    try:
        start = datetime.fromisoformat(req.start_date)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid start_date format")

    installment_amount = round(req.total_amount / req.installments, 2)
    installments = []
    for i in range(req.installments):
        due_date = start + timedelta(days=30 * i)
        amount = installment_amount if i < req.installments - 1 else round(req.total_amount - installment_amount * (req.installments - 1), 2)
        installments.append({
            "index": i,
            "due_date": due_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "paid": False,
            "paid_date": None,
            "payment_reference": "",
        })

    plan = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "agency_name": agency.get("name", ""),
        "total_amount": req.total_amount,
        "installment_count": req.installments,
        "installments": installments,
        "status": "active",
        "notes": req.notes,
        "created_by": current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.agency_payment_plans.insert_one(plan)
    plan.pop("_id", None)
    return {"success": True, "plan": plan}


@router.put("/payment-plans/installment")
async def update_installment(
    req: UpdatePaymentPlanInstallment,
    current_user: User = Depends(get_current_user),
):
    plan = await db.agency_payment_plans.find_one(
        {"tenant_id": current_user.tenant_id, "id": req.plan_id},
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Payment plan not found")

    installments = plan.get("installments", [])
    if req.installment_index >= len(installments):
        raise HTTPException(status_code=400, detail="Invalid installment index")

    was_already_paid = installments[req.installment_index].get("paid", False)

    if req.paid and was_already_paid:
        return {"success": True, "status": plan.get("status", "active"), "message": "Already paid"}

    installments[req.installment_index]["paid"] = req.paid
    installments[req.installment_index]["paid_date"] = datetime.now(UTC).strftime("%Y-%m-%d") if req.paid else None
    installments[req.installment_index]["payment_reference"] = req.payment_reference

    all_paid = all(inst["paid"] for inst in installments)
    new_status = "completed" if all_paid else "active"

    await db.agency_payment_plans.update_one(
        {"_id": plan["_id"]},
        {"$set": {"installments": installments, "status": new_status}},
    )

    if req.paid and not was_already_paid:
        txn = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "agency_id": plan["agency_id"],
            "type": "payment",
            "amount": installments[req.installment_index]["amount"],
            "payment_method": "payment_plan",
            "reference": req.payment_reference or f"Plan {req.plan_id[:8]} - Inst #{req.installment_index + 1}",
            "notes": f"Payment plan installment #{req.installment_index + 1}",
            "recorded_by": current_user.email,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.agency_transactions.insert_one(txn)

    return {"success": True, "status": new_status}


@router.get("/statement/{agency_id}")
async def get_agency_statement(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    ledger = await _get_agency_ledger(current_user.tenant_id, agency_id)
    if not ledger:
        raise HTTPException(status_code=404, detail="Agency not found")

    agency_data = ledger[0]

    txns = await db.agency_transactions.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
    ).sort("created_at", 1).to_list(1000)

    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
        {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(1000)

    commission_rate = agency_data["commission_rate"] / 100

    raw_lines = []

    for b in bookings:
        commission = round(b.get("total_amount", 0) * commission_rate, 2)
        raw_lines.append({
            "date": b.get("created_at", "")[:10],
            "sort_key": b.get("created_at", ""),
            "description": f"Commission: {b.get('guest_name', 'Guest')} ({b.get('check_in', '')} - {b.get('check_out', '')})",
            "debit": commission,
            "credit": 0,
            "type": "commission",
            "booking_id": b.get("id", ""),
        })

    for t in txns:
        t.pop("_id", None)
        if t.get("type") == "payment":
            raw_lines.append({
                "date": t.get("created_at", "")[:10],
                "sort_key": t.get("created_at", ""),
                "description": f"Payment: {t.get('payment_method', '')} - {t.get('reference', '')}",
                "debit": 0,
                "credit": t.get("amount", 0),
                "type": "payment",
                "reference": t.get("reference", ""),
            })
        elif t.get("type") == "adjustment":
            raw_lines.append({
                "date": t.get("created_at", "")[:10],
                "sort_key": t.get("created_at", ""),
                "description": f"Adjustment: {t.get('notes', '')}",
                "debit": t.get("amount", 0) if t.get("amount", 0) > 0 else 0,
                "credit": abs(t.get("amount", 0)) if t.get("amount", 0) < 0 else 0,
                "type": "adjustment",
            })

    raw_lines.sort(key=lambda x: x.get("sort_key", ""))

    statement_lines = []
    running_balance = 0
    for line in raw_lines:
        running_balance += line.get("debit", 0) - line.get("credit", 0)
        line["balance"] = round(running_balance, 2)
        line.pop("sort_key", None)
        statement_lines.append(line)

    return {
        **agency_data,
        "statement": statement_lines,
    }
