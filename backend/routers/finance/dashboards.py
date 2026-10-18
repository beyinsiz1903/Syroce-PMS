"""Auto-split from finance.py — section: dashboards."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.business_date_service import ensure_business_date_initialized
from core.database import db
from core.security import get_current_user
from models.schemas import (
    User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from modules.pms_core.report_money import add_amount, rounded_totals, single_amount
from modules.pms_core.role_permission_service import require_op

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter()
security = HTTPBearer()
folio_balance_read_service = FolioBalanceReadService()
open_folio_service = OpenFolioService()


@router.get("/finance/expense-summary")
async def get_expense_summary(
    date: str | None = None,  # YYYY-MM-DD
    period: str = "today",  # today, week, month
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """
    Get expense summary with categories
    Categories: F&B costs, housekeeping, maintenance, staff, utilities, procurement
    """
    try:
        if date:
            target_date = datetime.fromisoformat(date).date()
        else:
            state = await ensure_business_date_initialized(db, current_user.tenant_id)
            target_date = datetime.fromisoformat(str(state["business_date"])[:10]).date()

        # Calculate date range
        if period == "today":
            start_date = target_date
            end_date = target_date
        elif period == "week":
            start_date = target_date - timedelta(days=6)
            end_date = target_date
        elif period == "month":
            start_date = target_date.replace(day=1)
            end_date = target_date
        else:
            raise HTTPException(422, "Dönem today, week veya month olmalıdır")

        from core.tenant_currency import get_tenant_currency
        from modules.pms_core.reporting_financials import report_payment_period_match

        tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
        rows = await db.expenses.find({"tenant_id": current_user.tenant_id,
            **report_payment_period_match(start_date.isoformat(), end_date.isoformat(), date_fields=("date", "expense_date", "created_at"))}, {"_id": 0}).to_list(None)
        totals, categories = {}, {}
        for row in rows:
            amount = row.get("total_amount", row.get("amount", 0))
            category = str(row.get("category") or "other")
            add_amount(totals, row.get("currency") or tenant_currency, amount)
            add_amount(categories.setdefault(category, {}), row.get("currency") or tenant_currency, amount)
        expenses = {key: {"category": key, "amount": single_amount(values), "by_currency": rounded_totals(values), "breakdown": {}} for key, values in categories.items()}
        total_expenses = single_amount(totals)

        # Calculate daily average for the period
        days_in_period = (end_date - start_date).days + 1
        daily_avg = total_expenses / days_in_period if total_expenses is not None else None

        return {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_expenses": total_expenses,
            "by_currency": rounded_totals(totals),
            "daily_average": round(daily_avg, 2) if daily_avg is not None else None,
            "categories": expenses,
            "top_expense": max(expenses.values(), key=lambda item: item["amount"])["category"] if expenses and len(totals) <= 1 else None,
            "source": "expense_accruals",
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, "Geçersiz tarih veya tutar") from exc


@router.get("/finance/cash-flow-dashboard")
@cached(ttl=180, key_prefix="finance_cash_flow_dashboard")  # Tur 3: was 5.5s, cache 3 min
async def get_cash_flow_dashboard(current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_finance_reports"))):
    """
    Comprehensive cash flow dashboard for Finance Manager
    Shows: today's cash in/out, weekly plan, bank balances, risk alerts
    """
    from routers.finance.mobile import get_cash_flow_summary_mobile

    payload = await get_cash_flow_summary_mobile.__wrapped__(current_user=current_user)
    today = payload["today"]
    banks = [{"bank": row["bank_name"], "account": row["account_number"], "balance": row["current_balance"], "currency": row["currency"],
              "last_sync": row["last_sync"]} for row in payload["bank_balances"]]
    bank_totals = {}
    for bank in banks:
        add_amount(bank_totals, bank["currency"], bank["balance"])
    return {
        "today": {**today, "net_cash_flow": today["net_flow"]},
        "weekly_forecast": [{**day, "expected_inflow": day["expected_collections"], "expected_outflow": day["expected_payments"],
                             "net": single_amount({code: day["collections_by_currency"].get(code, 0) - day["payments_by_currency"].get(code, 0)
                                                   for code in set(day["collections_by_currency"]) | set(day["payments_by_currency"])})} for day in payload["weekly_plan"]],
        "bank_balances": {"accounts": banks, "total": single_amount(bank_totals), "by_currency": rounded_totals(bank_totals), "available": bool(banks)},
        "status": "mixed_currency" if today["net_flow"] is None else "positive" if today["net_flow"] > 0 else "negative" if today["net_flow"] < 0 else "balanced",
        "source": "payment_and_cash_flow_ledgers",
    }


@router.get("/finance/risk-alerts")
async def get_risk_alerts(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v103 DX alias drift fix
):
    """
    Financial risk monitoring: overdue accounts, credit limits, suspicious receivables
    """
    try:
        today = datetime.now(UTC).date()

        # Get all folios with outstanding balance
        folios = await db.folios.find({"tenant_id": current_user.tenant_id, "status": {"$in": ["open", "closed"]}}, {"_id": 0}).to_list(1000)

        overdue_accounts = []
        over_limit_accounts = []
        suspicious_accounts = []

        for folio in folios:
            outstanding = folio.get("total_amount", 0) - folio.get("paid_amount", 0)

            if outstanding > 0:
                # Get booking info
                booking = await db.bookings.find_one({"id": folio.get("booking_id")}, {"_id": 0})

                if booking:
                    # Calculate days overdue
                    checkout_date = datetime.fromisoformat(booking["check_out"]).date()
                    days_overdue = (today - checkout_date).days

                    account_info = {
                        "folio_id": folio["id"],
                        "booking_id": booking["id"],
                        "guest_name": booking.get("guest_name"),
                        "room_number": booking.get("room_number"),
                        "outstanding_amount": round(outstanding, 2),
                        "checkout_date": booking["check_out"],
                        "days_overdue": days_overdue,
                    }

                    # Risk Categories
                    if days_overdue > 7:
                        account_info["risk_level"] = "high" if days_overdue > 30 else "medium"
                        overdue_accounts.append(account_info)

                    # Credit limit check (sample: 10000 TL limit)
                    if outstanding > 10000:
                        account_info["risk_level"] = "critical"
                        account_info["limit"] = 10000
                        over_limit_accounts.append(account_info)

                    # Suspicious accounts (multiple unpaid bookings or high amount)
                    if outstanding > 20000 or days_overdue > 60:
                        account_info["risk_level"] = "critical"
                        account_info["reason"] = "High amount" if outstanding > 20000 else "Long overdue"
                        suspicious_accounts.append(account_info)

        # Sort by risk
        overdue_accounts.sort(key=lambda x: x["days_overdue"], reverse=True)
        over_limit_accounts.sort(key=lambda x: x["outstanding_amount"], reverse=True)
        suspicious_accounts.sort(key=lambda x: x["outstanding_amount"], reverse=True)

        # Calculate totals
        total_overdue_amount = sum(acc["outstanding_amount"] for acc in overdue_accounts)
        total_at_risk = sum(acc["outstanding_amount"] for acc in suspicious_accounts)

        # Create notifications for critical cases
        for acc in suspicious_accounts[:5]:  # Top 5 critical
            existing_notif = await db.notifications.find_one({"related_id": acc["folio_id"], "type": "financial_risk", "tenant_id": current_user.tenant_id}, {"_id": 0})

            if not existing_notif:
                await db.notifications.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": current_user.tenant_id,
                        "user_role": "finance",
                        "title": f"🚨 Yüksek Riskli Hesap - {acc['guest_name']}",
                        "message": f"₺{acc['outstanding_amount']:,.2f} ödenmemiş bakiye",
                        "type": "financial_risk",
                        "priority": "urgent",
                        "related_id": acc["folio_id"],
                        "read": False,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )

        return {
            "overdue_accounts": overdue_accounts,
            "over_limit_accounts": over_limit_accounts,
            "suspicious_accounts": suspicious_accounts,
            "summary": {
                "total_overdue_count": len(overdue_accounts),
                "total_overdue_amount": round(total_overdue_amount, 2),
                "over_limit_count": len(over_limit_accounts),
                "suspicious_count": len(suspicious_accounts),
                "total_at_risk": round(total_at_risk, 2),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get risk alerts: {str(e)}")


@router.get("/finance/folios-filtered")
@cached(ttl=300, key_prefix="finance_folios_filtered")  # Cache for 5 min
async def get_folios_filtered(
    customer_type: str | None = None,  # vip, corporate, individual
    room_number: str | None = None,
    status: str | None = None,  # open, closed, cancelled
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: finance folios filtered
):
    """
    Get filtered folios with customer type and room filters
    """
    try:
        filter_dict = {"tenant_id": current_user.tenant_id}

        if status:
            filter_dict["status"] = status

        folios = await db.folios.find(filter_dict, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)

        # Bulk-fetch related bookings and guests (Tur 3 perf fix: was N+1, ~53s → <1s)
        booking_ids = list({f["booking_id"] for f in folios if f.get("booking_id")})
        bookings_by_id = {}
        if booking_ids:
            async for b in db.bookings.find({"tenant_id": current_user.tenant_id, "id": {"$in": booking_ids}}, {"_id": 0}):
                bookings_by_id[b.get("id")] = b

        guest_ids = list({b.get("guest_id") for b in bookings_by_id.values() if b.get("guest_id")})
        guests_by_id = {}
        if guest_ids:
            from security.encrypted_lookup import decrypt_guest_doc

            async for g in db.guests.find({"tenant_id": current_user.tenant_id, "id": {"$in": guest_ids}}, {"_id": 0}):
                guests_by_id[g.get("id")] = decrypt_guest_doc(g)

        # Enrich with booking and guest data (in-memory)
        enriched_folios = []
        for folio in folios:
            booking = bookings_by_id.get(folio.get("booking_id"))
            if booking:
                folio["guest_name"] = booking.get("guest_name")
                folio["room_number"] = booking.get("room_number")
                folio["check_in"] = booking.get("check_in")
                folio["check_out"] = booking.get("check_out")
                guest = guests_by_id.get(booking.get("guest_id"))
                if guest:
                    folio["customer_type"] = guest.get("customer_type", "individual")
                    folio["guest_email"] = guest.get("email")
                    folio["guest_phone"] = guest.get("phone")

            # Apply filters
            if customer_type and folio.get("customer_type") != customer_type:
                continue

            if room_number and folio.get("room_number") != room_number:
                continue

            if date_from and folio.get("check_in", "") < date_from:
                continue

            if date_to and folio.get("check_out", "") > date_to:
                continue

            enriched_folios.append(folio)

        return {
            "folios": enriched_folios,
            "count": len(enriched_folios),
            "filters": {"customer_type": customer_type, "room_number": room_number, "status": status, "date_from": date_from, "date_to": date_to},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filtered folios: {str(e)}")


@router.get("/finance/folio/{folio_id}/detail")
async def get_folio_detail(folio_id: str, current_user: User = Depends(get_current_user)):
    """
    Get complete folio details with all charges and payments
    """
    try:
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")

        # Get booking details
        if folio.get("booking_id"):
            booking = await db.bookings.find_one({"id": folio["booking_id"]}, {"_id": 0})
            folio["booking"] = booking

        # Calculate outstanding
        folio["outstanding"] = folio.get("total_amount", 0) - folio.get("paid_amount", 0)

        return folio

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get folio detail: {str(e)}")


@router.post("/finance/mobile-payment")
async def process_mobile_payment(
    folio_id: str,
    amount: float,
    payment_method: str,  # cash, card, bank_transfer
    notes: str = "",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    """
    Process payment from mobile device
    """
    try:
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")

        # Create payment record
        payment_id = str(uuid.uuid4())
        payment = {
            "id": payment_id,
            "folio_id": folio_id,
            "amount": amount,
            "payment_method": payment_method,
            "notes": notes,
            "processed_by": current_user.id,
            "processed_by_name": current_user.name,
            "processed_at": datetime.now(UTC).isoformat(),
            "tenant_id": current_user.tenant_id,
        }

        # Update folio
        new_paid_amount = folio.get("paid_amount", 0) + amount
        await db.folios.update_one({"id": folio_id}, {"$set": {"paid_amount": new_paid_amount, "updated_at": datetime.now(UTC).isoformat()}, "$push": {"payments": payment}})

        # Create audit log
        await db.audit_logs.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "user_id": current_user.id,
                "user_name": current_user.name,
                "user_role": current_user.role,
                "action": "MOBILE_PAYMENT",
                "entity_type": "folio",
                "entity_id": folio_id,
                "changes": {"amount": amount, "method": payment_method},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        return {"message": "Ödeme başarıyla işlendi", "payment_id": payment_id, "folio_id": folio_id, "amount": amount, "new_balance": round(folio.get("total_amount", 0) - new_paid_amount, 2)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process payment: {str(e)}")
