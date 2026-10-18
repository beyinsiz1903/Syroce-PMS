"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

from core.business_date_service import accounting_period_match, ensure_business_date_initialized
from core.database import db
from core.email import send_email
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.report_money import amounts_text, resolve_ledger_currencies
from modules.pms_core.report_money import currency_code as normalize_currency
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_collection
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import NON_COMMERCIAL_STATUSES, allocated_revenue_for_night, as_date, booking_nights, booking_occupies_night, load_stay_night_metrics, stay_day_match

try:
    from domains.pms.night_audit_module import AuditStatus, AutomaticPosting, NightAuditRecord
except ImportError:
    NightAuditRecord = None
    AuditStatus = None
    AutomaticPosting = None

from core.utils import (
    create_excel_workbook,
    excel_response,
)
from shared_kernel.migration_observability import migration_observability_service

try:
    from infra.logging_service import get_logging_service
except ImportError:
    get_logging_service = None

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)
sub_router = APIRouter()


def _flash_money(revenue, field, fallback_currency):
    from html import escape
    breakdown = revenue.get(field + "_by_currency")
    if field == "rev_par":
        breakdown = breakdown or revenue.get("revpar_by_currency")
    return escape(amounts_text(breakdown if breakdown else {fallback_currency: revenue.get(field) or 0}))

FNB_CATEGORIES = {
    "alcohol",
    "alcoholic_beverage",
    "appetizer",
    "bar",
    "beverage",
    "cafe",
    "dessert",
    "drink",
    "fb",
    "f&b",
    "fnb",
    "food",
    "food_and_beverage",
    "food_beverage",
    "restaurant",
    "room_service",
}


def _report_date(value: str | None, field: str = "date"):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} YYYY-MM-DD formatında olmalı") from exc


def _currency(row: dict) -> str:
    return normalize_currency(row.get("currency"))


def _add_currency(total: dict[str, float], currency: str, amount: float) -> None:
    total[currency] = total.get(currency, 0.0) + float(amount or 0)


def _rounded_currency(total: dict[str, float]) -> dict[str, float]:
    return {currency: round(amount, 2) for currency, amount in total.items()}


def _single_currency(total: dict[str, float]) -> float | None:
    values = [amount for amount in total.values() if amount != 0]
    return round(values[0], 2) if len(values) == 1 else (0.0 if not values else None)


@sub_router.get("/reports/migration-observability")
async def get_migration_observability(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    return await migration_observability_service.get_dashboard(current_user.tenant_id)


@sub_router.post("/reports/send-flash-now")
async def send_flash_report_now(
    recipients: list[str],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """Flash report'u şimdi gönder"""
    from modules.analytics_export.report_automation import get_report_automation
    from modules.messaging.email_service import email_service

    automation = get_report_automation(db, email_service)
    await automation.send_flash_report_email(current_user.tenant_id, recipients)

    return {"success": True, "message": f"Flash report {len(recipients)} alıcıya gönderildi"}


@sub_router.get("/reports/flash-report")
@cached(ttl=15, key_prefix="flash_report_v2")
async def get_flash_report(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    """Compatibility view over the same posted ledger as Daily Flash."""
    if date:
        target_day = _report_date(date)
    else:
        state = await ensure_business_date_initialized(db, current_user.tenant_id)
        target_day = as_date(state["business_date"])
    key = target_day.isoformat()
    canonical = await get_daily_flash_report.__wrapped__(key, current_user)
    metric, revenue = canonical["occupancy"], canonical["revenue"]
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, **stay_day_match(target_day)}, {"_id": 0}).to_list(None)
    active = [b for b in bookings if booking_occupies_night(b, target_day, actual_only=True)]
    no_shows = [b for b in bookings if as_date(b.get("check_in")) == target_day and str(b.get("status") or "").lower() in {"no_show", "noshow"}]
    cancellations = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": {"$in": ["cancelled", "canceled"]},
        "$or": [{"cancelled_at": {"$regex": f"^{key}"}},
            {"cancelled_at": {"$gte": datetime.combine(target_day, datetime.min.time(), tzinfo=UTC), "$lt": datetime.combine(target_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)}},
            {"cancelled_at": {"$in": [None, ""]}, "updated_at": {"$regex": f"^{key}"}},
            {"cancelled_at": {"$in": [None, ""]}, "updated_at": {"$gte": datetime.combine(target_day, datetime.min.time(), tzinfo=UTC), "$lt": datetime.combine(target_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)}}]},
        {"_id": 0, "id": 1, "booking_number": 1, "guest_name": 1, "room_number": 1,
         "check_in": 1, "check_out": 1, "cancelled_at": 1, "cancellation_reason": 1, "channel": 1}).to_list(None)
    from modules.pms_core.reporting_financials import report_payment_day_match

    payments = await db.payments.find({"tenant_id": current_user.tenant_id, **report_payment_day_match(key)},
        {"_id": 0}).to_list(None)
    payments = await resolve_ledger_currencies(payments, current_user.tenant_id, database=db)
    collected = {}
    for payment in deduplicate_report_payments(payments):
        _add_currency(collected, _currency(payment), effective_collection(payment))
    collected = _rounded_currency(collected)
    categories = revenue.get("category_revenue_by_currency", {})
    total = revenue["total_revenue_by_currency"]
    outstanding = {code: amount - collected.get(code, 0) for code, amount in total.items()}
    for code in collected.keys() - total.keys():
        outstanding[code] = -collected[code]
    fields = {"total": total, "room": revenue["room_revenue_by_currency"], "fb": revenue["fb_revenue_by_currency"],
        "spa": categories.get("spa", {}), "minibar": categories.get("minibar", {}), "laundry": categories.get("laundry", {}),
        "collected": collected, "outstanding": _rounded_currency(outstanding)}
    ancillary = ("room", "fb", "spa", "minibar", "laundry")
    fields["other"] = _rounded_currency({code: amount - sum(fields[field].get(code, 0) for field in ancillary) for code, amount in total.items()})
    room_ids = [b["room_id"] for b in active if b.get("room_id") and not b.get("room_number")]
    room_rows = await db.rooms.find({"tenant_id": current_user.tenant_id, "id": {"$in": room_ids}}, {"_id": 0, "id": 1, "room_number": 1}).to_list(None) if room_ids else []
    room_names = {row["id"]: row.get("room_number") for row in room_rows}
    breakdown = [{"guest_name": b.get("guest_name") or "Misafir", "room_number": b.get("room_number") or room_names.get(b.get("room_id")) or "?",
        "daily_rate": float(allocated_revenue_for_night(b, target_day)), "total_stay_amount": b.get("total_amount", 0),
        "currency": _currency(b), "nights": booking_nights(b)} for b in active]
    legacy_revenue = {field: _single_currency(values) for field, values in fields.items()}
    legacy_revenue.update({field + "_by_currency": values for field, values in fields.items()})
    legacy_revenue.update({"room_revenue_breakdown": breakdown, "basis": revenue["basis"], "mixed_currency": _single_currency(total) is None})
    return {"date": key,
        "occupancy": {"rate": metric["occupancy_rate"], "occupied": metric["occupied_rooms"], "total": metric["total_rooms"],
            "available": max(metric["total_rooms"] - metric["occupied_rooms"], 0)},
        "kpi": {"adr": revenue["adr"], "revpar": revenue["rev_par"], "adr_by_currency": revenue["adr_by_currency"], "revpar_by_currency": revenue["rev_par_by_currency"]},
        "revenue": legacy_revenue,
        "operations": {**canonical["movements"], "inhouse": metric["occupied_rooms"], "no_shows": len(no_shows),
            "cancellations": len(cancellations), "walk_ins": sum(1 for b in bookings if as_date(b.get("check_in")) == target_day and str(b.get("channel") or b.get("booking_source") or "").lower() in {"walk_in", "walkin"} and str(b.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES), "overstays": 0},
        "attention_details": {"cancellations": cancellations, "no_shows": no_shows},
        "scope": {"business_date": key, "occupancy": "Seçili iş gecesinde gerçekleşmiş oda doluluğu",
            "revenue": "İşlenmiş folyo, ek harcama ve doğrudan POS gelirleri; rezervasyon tahmini değil",
            "collections": "Seçili iş gününün tahsilatları; mevcut folyo bakiyesi değildir"},
        "departments": [{"name": label, "amount": _single_currency(fields[field]), "amount_by_currency": fields[field]}
            for field, label in (("room", "Oda Geliri"), ("fb", "Yiyecek & İçecek"), ("spa", "Spa & Wellness"), ("minibar", "Minibar"), ("laundry", "Çamaşırhane"), ("other", "Diğer"))]}


@sub_router.get("/reports/daily-flash-pdf")
async def get_daily_flash_pdf(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash GM/CFO
):
    """
    Export daily flash report as PDF
    """
    from fastapi.responses import Response

    try:
        flash_data = await get_daily_flash_report(None, current_user)
        from core.tenant_currency import get_tenant_currency

        currency_code, _ = await get_tenant_currency(current_user.tenant_id)

        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                h1 {{ color: #1e40af; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #1e40af; color: white; }}
                .metric {{ background-color: #f3f4f6; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Daily Flash Report</h1>
            <p><strong>Date:</strong> {flash_data["date"]}</p>

            <div class="metric">
                <h3>Occupancy</h3>
                <p>Occupied Rooms: {flash_data["occupancy"]["occupied_rooms"]}</p>
                <p>Total Rooms: {flash_data["occupancy"]["total_rooms"]}</p>
                <p>Occupancy %: {flash_data["occupancy"]["occupancy_rate"]:.1f}%</p>
            </div>

            <div class="metric">
                <h3>Revenue</h3>
                <p>Room Revenue: {_flash_money(flash_data["revenue"], "room_revenue", currency_code)}</p>
                <p>Total Revenue: {_flash_money(flash_data["revenue"], "total_revenue", currency_code)}</p>
                <p>ADR: {_flash_money(flash_data["revenue"], "adr", currency_code)}</p>
                <p>RevPAR: {_flash_money(flash_data["revenue"], "rev_par", currency_code)}</p>
            </div>

            <div class="metric">
                <h3>Arrivals &amp; Departures</h3>
                <p>Arrivals: {flash_data["movements"]["arrivals"]}</p>
                <p>Departures: {flash_data["movements"]["departures"]}</p>
                <p>Stayovers: {flash_data["movements"]["stayovers"]}</p>
            </div>
        </body>
        </html>
        """

        try:
            from weasyprint import HTML  # type: ignore
        except (ImportError, OSError) as exc:
            raise HTTPException(status_code=503, detail="PDF oluşturucu bu ortamda kullanılamıyor") from exc
        pdf_bytes = HTML(string=html_content).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="daily-flash-{flash_data["date"]}.pdf"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}") from e


@sub_router.post("/reports/email-daily-flash")
async def email_daily_flash(
    data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU follow-up: POST architect MEDIUM
):
    """
    Email daily flash report to recipients
    """
    recipients = data.get("recipients", [])

    if not recipients:
        raise HTTPException(status_code=400, detail="Recipients list is required")

    try:
        flash_data = await get_daily_flash_report(None, current_user)
        from core.tenant_currency import get_tenant_currency

        currency_code, _ = await get_tenant_currency(current_user.tenant_id)

        email_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .metric {{ background-color: #f3f4f6; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                h3 {{ color: #1e40af; }}
            </style>
        </head>
        <body>
            <h2>Daily Flash Report - {flash_data["date"]}</h2>

            <div class="metric">
                <h3>Occupancy</h3>
                <p>Occupied: {flash_data["occupancy"]["occupied_rooms"]} / {flash_data["occupancy"]["total_rooms"]} ({flash_data["occupancy"]["occupancy_rate"]:.1f}%)</p>
            </div>

            <div class="metric">
                <h3>Revenue</h3>
                <p>Room Revenue: {_flash_money(flash_data["revenue"], "room_revenue", currency_code)}</p>
                <p>Total Revenue: {_flash_money(flash_data["revenue"], "total_revenue", currency_code)}</p>
            </div>

            <div class="metric">
                <h3>Movements</h3>
                <p>Arrivals: {flash_data["movements"]["arrivals"]}</p>
                <p>Departures: {flash_data["movements"]["departures"]}</p>
            </div>

            <p><small>Generated by Syroce PMS</small></p>
        </body>
        </html>
        """

        subject = f'Daily Flash Report - {flash_data["date"]}'
        results = await asyncio.gather(
            *[send_email(to=r, subject=subject, html=email_html) for r in recipients],
            return_exceptions=True,
        )
        sent = [r for r, res in zip(recipients, results, strict=False) if isinstance(res, dict) and res.get("sent")]
        failed = [r for r in recipients if r not in sent]

        logger.info("Daily flash email: %d/%d delivered (failed=%s)", len(sent), len(recipients), failed)

        return {
            "success": len(sent) > 0,
            "message": f"Daily flash report sent to {len(sent)}/{len(recipients)} recipients",
            "recipients_sent": sent,
            "recipients_failed": failed,
            "provider": next(
                (r.get("provider") for r in results if isinstance(r, dict) and r.get("sent")),
                None,
            ),
        }

    except Exception as e:
        logger.exception("email_daily_flash failed")
        raise HTTPException(status_code=500, detail=f"Email sending failed: {str(e)}") from e


@sub_router.get("/reports/daily-flash")
@cached(ttl=15, key_prefix="report_daily_flash_v2")
async def get_daily_flash_report(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash GM/CFO
    _nocache: bool = Query(False, alias="nocache"),
):
    """Daily Flash Report - GM/CFO Dashboard"""
    if date_str:
        target_date = _report_date(date_str, "date_str")
    else:
        state = await ensure_business_date_initialized(db, current_user.tenant_id)
        target_date = datetime.fromisoformat(state["business_date"][:10]).date()
    day_key = target_date.isoformat()
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, target_date, target_date, actual_only=True)
    metric = metrics[0] if metrics else {"occupied_rooms": 0, "total_rooms": 0, "occupancy_rate": 0}
    total_rooms = metric["total_rooms"]
    occupied_rooms = metric["occupied_rooms"]
    sold_rooms = metric.get("sold_rooms", occupied_rooms)
    occupancy_rate = metric["occupancy_rate"]
    movement_bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, **stay_day_match(target_date, include_stayovers=False)},
        {"_id": 0, "check_in": 1, "check_out": 1, "status": 1},
    ).to_list(None)
    arrivals = sum(1 for booking in movement_bookings if as_date(booking.get("check_in")) == target_date and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)
    departures = sum(1 for booking in movement_bookings if as_date(booking.get("check_out")) == target_date and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)

    # Use the same ledger selection as the revenue screen: business-date first,
    # manual extras included, closed POS only, and transferred POS counted once.
    from routers.reports_pkg.standard_reports import _charge_amount, _charge_category, _posted_revenue_rows
    charges = await _posted_revenue_rows(current_user.tenant_id, target_date, target_date, database=db)

    total_by_currency: dict[str, float] = {}
    room_by_currency: dict[str, float] = {}
    fb_by_currency: dict[str, float] = {}
    category_by_currency = {}
    for charge in charges:
        amount = _charge_amount(charge)
        currency = _currency(charge)
        category = _charge_category(charge)
        _add_currency(category_by_currency.setdefault(category, {}), currency, amount)
        _add_currency(total_by_currency, currency, amount)
        if category in {"room", "accommodation", "room_charge"}:
            _add_currency(room_by_currency, currency, amount)
        if category in FNB_CATEGORIES:
            _add_currency(fb_by_currency, currency, amount)

    total_by_currency = _rounded_currency(total_by_currency)
    room_by_currency = _rounded_currency(room_by_currency)
    fb_by_currency = _rounded_currency(fb_by_currency)
    other_by_currency = _rounded_currency({
        currency: amount - room_by_currency.get(currency, 0) - fb_by_currency.get(currency, 0)
        for currency, amount in total_by_currency.items()
    })

    # Calculate ADR and RevPAR
    adr_by_currency = _rounded_currency({currency: amount / sold_rooms if sold_rooms else 0 for currency, amount in room_by_currency.items()})
    rev_par_by_currency = _rounded_currency({currency: amount / total_rooms if total_rooms else 0 for currency, amount in room_by_currency.items()})

    return {
        "date": day_key,
        "occupancy": {"occupied_rooms": occupied_rooms, "total_rooms": total_rooms, "occupancy_rate": occupancy_rate},
        "movements": {"arrivals": arrivals, "departures": departures, "stayovers": max(occupied_rooms - arrivals, 0)},
        "revenue": {
            "total_revenue": _single_currency(total_by_currency),
            "total_revenue_by_currency": total_by_currency,
            "room_revenue": _single_currency(room_by_currency),
            "room_revenue_by_currency": room_by_currency,
            "fb_revenue": _single_currency(fb_by_currency),
            "fb_revenue_by_currency": fb_by_currency,
            "other_revenue": _single_currency(other_by_currency),
            "other_revenue_by_currency": other_by_currency,
            "category_revenue_by_currency": {category: _rounded_currency(values) for category, values in category_by_currency.items()},
            "adr": _single_currency(adr_by_currency),
            "adr_by_currency": adr_by_currency,
            "rev_par": _single_currency(rev_par_by_currency),
            "rev_par_by_currency": rev_par_by_currency,
            "sold_rooms": sold_rooms,
            "basis": "posted_folio_charges_plus_untransferred_pos",
        },
    }


@sub_router.get("/reports/daily-flash/excel")
async def export_daily_flash_excel(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash excel
):
    """Export Daily Flash Report to Excel with professional formatting and dynamic currency"""
    report_data = await get_daily_flash_report.__wrapped__(date_str, current_user)
    target_date = report_data["date"]

    from core.tenant_currency import get_tenant_currency
    code, _ = await get_tenant_currency(current_user.tenant_id)
    data = [["Report Date", "", target_date]]
    for section in ("occupancy", "movements"):
        data.extend([[key, "", value] for key, value in report_data[section].items()])
    for field, label in (("total_revenue", "Total Revenue"), ("room_revenue", "Room Revenue"),
                         ("fb_revenue", "F&B Revenue"), ("other_revenue", "Other Revenue"),
                         ("adr", "ADR"), ("rev_par", "RevPAR")):
        totals = report_data["revenue"].get(field + "_by_currency") or {code: report_data["revenue"].get(field) or 0}
        data.extend([[label, currency, amount] for currency, amount in sorted(totals.items())])
    wb = create_excel_workbook(title=f"Daily Flash Report - {target_date}", headers=["Metric", "Currency", "Value"], data=data, sheet_name="Daily Flash")
    return excel_response(wb, f"daily_flash_report_{target_date}.xlsx")


@sub_router.post("/reports/send-weekly-email")
async def send_weekly_management_email(
    email_config: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_reports")),  # v92 DW
):
    """Send weekly management summary via email"""
    current_user = await get_current_user(credentials)

    state = await ensure_business_date_initialized(db, current_user.tenant_id)
    week_end = datetime.fromisoformat(state["business_date"][:10]).date()
    week_start = week_end - timedelta(days=6)
    start_key = week_start.isoformat()
    end_key = week_end.isoformat()
    next_key = (week_end + timedelta(days=1)).isoformat()

    total_bookings = await db.bookings.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"created_at": {"$gte": start_key, "$lt": next_key}},
                {"reservation_date": {"$gte": start_key, "$lt": next_key}},
            ],
            "status": {"$nin": list(NON_COMMERCIAL_STATUSES)},
        }
    )
    charges = await db.folio_charges.find(
        {
            "tenant_id": current_user.tenant_id,
            "voided": {"$ne": True},
            **accounting_period_match(
                start_key,
                end_key,
                {"date": {"$gte": start_key, "$lt": next_key}},
                {"created_at": {"$gte": start_key, "$lt": next_key}},
            ),
        },
        {"_id": 0, "total": 1, "amount": 1, "charge_category": 1, "charge_type": 1},
    ).to_list(20000)
    total_revenue = sum(float(charge.get("total") or charge.get("amount") or 0) for charge in charges)
    room_revenue = sum(
        float(charge.get("total") or charge.get("amount") or 0)
        for charge in charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").lower() in {"room", "accommodation", "room_charge"}
    )
    stay_metrics = await load_stay_night_metrics(db, current_user.tenant_id, week_start, week_end, actual_only=True)
    occupied_room_nights = sum(int(item.get("occupied_rooms") or 0) for item in stay_metrics)
    available_room_nights = sum(int(item.get("total_rooms") or 0) for item in stay_metrics)
    occupancy = round(occupied_room_nights / available_room_nights * 100, 2) if available_room_nights else 0.0
    adr = round(room_revenue / occupied_room_nights, 2) if occupied_room_nights else 0.0
    revpar = round(room_revenue / available_room_nights, 2) if available_room_nights else 0.0

    recipient = str(email_config.get("email") or current_user.email or "").strip()
    if not recipient:
        raise HTTPException(status_code=422, detail="Rapor alıcısı e-posta adresi gerekli")
    subject = f"Haftalık Yönetim Özeti - {start_key} / {end_key}"
    report_data = {
        "week_start": start_key,
        "week_ending": end_key,
        "total_bookings": total_bookings,
        "total_revenue": round(total_revenue, 2),
        "room_revenue": round(room_revenue, 2),
        "key_metrics": {"occupancy": occupancy, "adr": adr, "revpar": revpar},
    }
    html = f"""
    <h2>Haftalık Yönetim Özeti</h2>
    <p><strong>Dönem:</strong> {start_key} – {end_key}</p>
    <ul>
      <li>Yeni rezervasyon: {total_bookings}</li>
      <li>Toplam gelir: {total_revenue:,.2f}</li>
      <li>Oda geliri: {room_revenue:,.2f}</li>
      <li>Doluluk: %{occupancy:.2f}</li>
      <li>ADR: {adr:,.2f}</li>
      <li>RevPAR: {revpar:,.2f}</li>
    </ul>
    """
    delivery = await send_email(to=recipient, subject=subject, html=html)
    delivered = isinstance(delivery, dict) and bool(delivery.get("sent"))

    email_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "recipient_email": recipient,
        "subject": subject,
        "report_type": "weekly_summary",
        "report_data": report_data,
        "status": "sent" if delivered else "failed",
        "sent_at": datetime.now(UTC).isoformat() if delivered else None,
        "sent_by": current_user.name,
        "provider": delivery.get("provider") if isinstance(delivery, dict) else None,
    }

    await db.email_reports.insert_one(email_record)

    if not delivered:
        raise HTTPException(status_code=502, detail="Haftalık rapor e-postası gönderilemedi")
    return {"message": "Haftalık yönetim özeti gönderildi", "email_id": email_record["id"], "recipient": recipient}


@sub_router.get("/reports/email-history")
async def get_email_report_history(
    limit: int = Query(20, ge=1, le=100),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_reports")),
):
    """Get email report history"""
    current_user = await get_current_user(credentials)

    emails = []
    async for email in db.email_reports.find({"tenant_id": current_user.tenant_id}).sort("sent_at", -1).limit(limit):
        email.pop("_id", None)
        emails.append(email)

    return {"emails": emails, "count": len(emails)}


@sub_router.get("/reports/weekly-management-summary")
async def get_weekly_management_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Get weekly management summary report"""
    state = await ensure_business_date_initialized(db, current_user.tenant_id)
    week_end = datetime.fromisoformat(str(state["business_date"])[:10]).date()
    week_start = week_end - timedelta(days=6)
    end_exclusive = week_end + timedelta(days=1)

    # Get key metrics for the week
    total_bookings = await db.bookings.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "created_at": {"$gte": week_start.isoformat(), "$lt": end_exclusive.isoformat()},
            "status": {"$nin": list(NON_COMMERCIAL_STATUSES)},
        }
    )
    charges = await db.folio_charges.find(
        {
            "tenant_id": current_user.tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": week_start.isoformat(), "$lte": week_end.isoformat()}},
                {"business_date": {"$exists": False}, "date": {"$gte": week_start.isoformat(), "$lt": end_exclusive.isoformat()}},
                {"business_date": None, "date": {"$gte": week_start.isoformat(), "$lt": end_exclusive.isoformat()}},
            ],
        },
        {"_id": 0, "total": 1, "amount": 1},
    ).to_list(50000)
    total_revenue = sum(float(charge.get("total") or charge.get("amount") or 0) for charge in charges)
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, week_start, week_end, actual_only=True)
    occupied_room_nights = sum(int(row.get("occupied_rooms") or 0) for row in metrics)
    available_room_nights = sum(int(row.get("total_rooms") or 0) for row in metrics)
    occupied_avg = occupied_room_nights / available_room_nights * 100 if available_room_nights else 0

    # Get maintenance tasks completed
    completed_tasks = await db.maintenance_tasks.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "status": "completed",
            "completed_at": {"$gte": week_start.isoformat(), "$lt": end_exclusive.isoformat()},
        }
    )

    # B: gerçek misafir memnuniyeti (haftalık review rating ortalaması); review yoksa fail-closed (null)
    sat_docs = await db.reviews.find(
        {"tenant_id": current_user.tenant_id, "created_at": {"$gte": week_start.isoformat(), "$lt": end_exclusive.isoformat()}},
        {"_id": 0, "rating": 1},
    ).to_list(2000)
    sat_ratings = [r.get("rating") for r in sat_docs if isinstance(r.get("rating"), (int, float))]
    guest_satisfaction = round(sum(sat_ratings) / len(sat_ratings), 2) if sat_ratings else None

    return {
        "week_start": week_start.isoformat(),
        "week_ending": week_end.isoformat(),
        "total_bookings": total_bookings,
        "total_revenue": round(total_revenue, 2),
        "revenue_basis": "posted_folio_charges",
        "avg_occupancy_pct": round(occupied_avg, 2),
        "completed_maintenance": completed_tasks,
        "guest_satisfaction": guest_satisfaction,
        "guest_satisfaction_available": guest_satisfaction is not None,
        "guest_satisfaction_reviews": len(sat_ratings),
        # top_performers: gerçek haftalık personel-performans kaynağı yok -> fail-closed (sahte personel kaldırıldı)
        "top_performers": [],
        "top_performers_available": False,
    }
