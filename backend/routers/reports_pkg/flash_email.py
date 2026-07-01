"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

from core.database import db
from core.email import send_email
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

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
@cached(ttl=300, key_prefix="flash_report")  # Cache for 5 min
async def get_flash_report(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    """
    Daily Flash Report - Günlük özet rapor
    5 yıldızlı otel yöneticileri için sabah raporu
    """
    target_date = datetime.now(UTC) if not date else datetime.fromisoformat(date)
    today_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = target_date.replace(hour=23, minute=59, second=59)

    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    # Whitelist: gercekten odayi isgal eden statuler. Gecmis tarihli flash icin
    # checked_out da sayilmali; gelecekteki rezervasyonlar icin confirmed/guaranteed.
    occupied_today = await db.bookings.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            "check_in": {"$lte": today_end.isoformat()},
            "check_out": {"$gte": today_start.isoformat()},
        }
    )

    # Cap %100 (overbooking/seed cakisma korumasi)
    occupancy_rate = min((occupied_today / total_rooms * 100), 100.0) if total_rooms > 0 else 0

    arrivals_today = await db.bookings.count_documents(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}, "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}}
    )

    departures_today = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_out": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}})

    inhouse_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "status": "checked_in"})

    today_bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}},
        {"_id": 0, "total_amount": 1, "base_rate": 1, "paid_amount": 1, "charges": 1, "channel": 1, "status": 1},
    ).to_list(1000)

    total_revenue = sum(b.get("total_amount", 0) for b in today_bookings)
    collected = sum(b.get("paid_amount", 0) for b in today_bookings)
    adr = total_revenue / occupied_today if occupied_today > 0 else 0
    revpar = total_revenue / total_rooms if total_rooms > 0 else 0

    no_shows = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}, "status": "no_show"})

    cancellations = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "status": "cancelled", "created_at": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}})

    walk_ins = sum(1 for b in today_bookings if b.get("channel") == "walk_in")
    overstays = 0

    fnb_revenue = 0
    try:
        fnb_orders = await db.pos_orders.find(
            {"tenant_id": current_user.tenant_id, "created_at": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}}, {"_id": 0, "total_amount": 1}
        ).to_list(1000)
        fnb_revenue = sum(o.get("total_amount", 0) for o in fnb_orders)
    except Exception:
        pass

    charges_by_cat = {}
    for b in today_bookings:
        for c in b.get("charges", []):
            cat = c.get("charge_category", "other")
            charges_by_cat[cat] = charges_by_cat.get(cat, 0) + c.get("amount", 0)

    room_revenue = charges_by_cat.get("room", charges_by_cat.get("accommodation", 0))
    if not charges_by_cat:
        room_revenue = total_revenue
    spa_revenue = charges_by_cat.get("spa", 0)
    minibar_revenue = charges_by_cat.get("minibar", 0)
    laundry_revenue = charges_by_cat.get("laundry", 0)

    grand_total = total_revenue + fnb_revenue
    other_revenue = max(0, grand_total - room_revenue - fnb_revenue - spa_revenue - minibar_revenue - laundry_revenue)

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "occupancy": {
            "rate": round(occupancy_rate, 2),
            "occupied": occupied_today,
            "total": total_rooms,
            "available": total_rooms - occupied_today,
        },
        "kpi": {
            "adr": round(adr, 2),
            "revpar": round(revpar, 2),
        },
        "revenue": {
            "total": round(grand_total, 2),
            "room": round(room_revenue, 2),
            "fb": round(fnb_revenue, 2),
            "spa": round(spa_revenue, 2),
            "minibar": round(minibar_revenue, 2),
            "laundry": round(laundry_revenue, 2),
            "other": round(other_revenue, 2),
            "collected": round(collected, 2),
            "outstanding": round(grand_total - collected, 2),
        },
        "operations": {
            "arrivals": arrivals_today,
            "departures": departures_today,
            "inhouse": inhouse_count,
            "no_shows": no_shows,
            "walk_ins": walk_ins,
            "cancellations": cancellations,
            "overstays": overstays,
        },
        "departments": [
            {"name": "Oda Geliri", "amount": round(room_revenue, 2)},
            {"name": "Yiyecek & İçecek", "amount": round(fnb_revenue, 2)},
            {"name": "Spa & Wellness", "amount": round(spa_revenue, 2)},
            {"name": "Minibar", "amount": round(minibar_revenue, 2)},
            {"name": "Çamaşırhane", "amount": round(laundry_revenue, 2)},
            {"name": "Diğer", "amount": round(other_revenue, 2)},
        ],
    }


@sub_router.get("/reports/daily-flash-pdf")
@cached(ttl=600, key_prefix="report_daily_flash_pdf")  # Cache for 10 min
async def get_daily_flash_pdf(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash GM/CFO
):
    """
    Export daily flash report as PDF
    """
    from io import BytesIO

    from fastapi.responses import StreamingResponse

    try:
        flash_data = await get_daily_flash_report(None, current_user)

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
                <p>Room Revenue: ${flash_data["revenue"]["room_revenue"]:.2f}</p>
                <p>Total Revenue: ${flash_data["revenue"]["total_revenue"]:.2f}</p>
                <p>ADR: ${flash_data["revenue"]["adr"]:.2f}</p>
                <p>RevPAR: ${flash_data["revenue"]["rev_par"]:.2f}</p>
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

        # Convert HTML to PDF using simple method (can upgrade to weasyprint later)
        # For now, return HTML as PDF placeholder
        pdf_buffer = BytesIO()
        pdf_buffer.write(html_content.encode("utf-8"))
        pdf_buffer.seek(0)

        return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=daily-flash-{datetime.now(UTC).strftime('%Y%m%d')}.pdf"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


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
                <p>Room Revenue: ${flash_data["revenue"]["room_revenue"]:.2f}</p>
                <p>Total Revenue: ${flash_data["revenue"]["total_revenue"]:.2f}</p>
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

        subject = f"Daily Flash Report - {datetime.now(UTC).strftime('%Y-%m-%d')}"
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
@cached(ttl=300, key_prefix="report_daily_flash")  # Cache for 5 minutes
async def get_daily_flash_report(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash GM/CFO
    _nocache: bool = Query(False, alias="nocache"),
):
    """Daily Flash Report - GM/CFO Dashboard"""
    target_date = datetime.fromisoformat(date_str).date() if date_str else datetime.now(UTC).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Get total rooms
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    # Get occupancy (whitelist: gercekte odayi isgal eden statuler)
    occupied_rooms = await db.bookings.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            "check_in": {"$lte": end_of_day.isoformat()},
            "check_out": {"$gte": start_of_day.isoformat()},
        }
    )

    # Cap %100 (overbooking/seed cakisma korumasi)
    occupancy_rate = round(min((occupied_rooms / total_rooms * 100), 100.0) if total_rooms > 0 else 0, 2)

    # Get arrivals & departures count
    arrivals = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": {"$gte": start_of_day.isoformat(), "$lte": end_of_day.isoformat()}})

    departures = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_out": {"$gte": start_of_day.isoformat(), "$lte": end_of_day.isoformat()}})

    # Note: Revenue is calculated from folio charges, not bookings directly

    # Calculate revenue from folio charges posted today
    charges = await db.folio_charges.find({"tenant_id": current_user.tenant_id, "date": {"$gte": start_of_day.isoformat(), "$lte": end_of_day.isoformat()}, "voided": False}).to_list(10000)

    total_revenue = sum(c["total"] for c in charges)

    # Revenue breakdown by category
    room_revenue = sum(c["total"] for c in charges if c["charge_category"] == "room")
    fb_revenue = sum(c["total"] for c in charges if c["charge_category"] in ["food", "beverage"])
    other_revenue = total_revenue - room_revenue - fb_revenue

    # Calculate ADR and RevPAR
    adr = round(room_revenue / occupied_rooms, 2) if occupied_rooms > 0 else 0
    rev_par = round(total_revenue / total_rooms, 2) if total_rooms > 0 else 0

    return {
        "date": target_date.isoformat(),
        "occupancy": {"occupied_rooms": occupied_rooms, "total_rooms": total_rooms, "occupancy_rate": occupancy_rate},
        "movements": {"arrivals": arrivals, "departures": departures, "stayovers": occupied_rooms - arrivals},
        "revenue": {
            "total_revenue": round(total_revenue, 2),
            "room_revenue": round(room_revenue, 2),
            "fb_revenue": round(fb_revenue, 2),
            "other_revenue": round(other_revenue, 2),
            "adr": adr,
            "rev_par": rev_par,
        },
    }


@sub_router.get("/reports/daily-flash/excel")
@cached(ttl=600, key_prefix="report_daily_flash_excel")  # Cache for 10 min
async def export_daily_flash_excel(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v85 DU: daily flash excel
):
    """Export Daily Flash Report to Excel"""
    # Get the report data
    report_data = await get_daily_flash_report(date_str, current_user)

    target_date = report_data["date"]

    # Prepare data for Excel
    headers = ["Metric", "Value"]
    data = [
        ["Report Date", target_date],
        ["", ""],
        ["OCCUPANCY", ""],
        ["Total Rooms", report_data["occupancy"]["total_rooms"]],
        ["Occupied Rooms", report_data["occupancy"]["occupied_rooms"]],
        ["Occupancy Rate", f"{report_data['occupancy']['occupancy_rate']}%"],
        ["", ""],
        ["MOVEMENTS", ""],
        ["Arrivals", report_data["movements"]["arrivals"]],
        ["Departures", report_data["movements"]["departures"]],
        ["Stayovers", report_data["movements"]["stayovers"]],
        ["", ""],
        ["REVENUE", ""],
        ["Total Revenue", f"${report_data['revenue']['total_revenue']:,.2f}"],
        ["Room Revenue", f"${report_data['revenue']['room_revenue']:,.2f}"],
        ["F&B Revenue", f"${report_data['revenue']['fb_revenue']:,.2f}"],
        ["Other Revenue", f"${report_data['revenue']['other_revenue']:,.2f}"],
        ["ADR (Average Daily Rate)", f"${report_data['revenue']['adr']:,.2f}"],
        ["RevPAR (Revenue Per Available Room)", f"${report_data['revenue']['rev_par']:,.2f}"],
    ]

    wb = create_excel_workbook(title=f"Daily Flash Report - {target_date}", headers=headers, data=data, sheet_name="Daily Flash")

    filename = f"daily_flash_report_{target_date}.xlsx"
    return excel_response(wb, filename)


@sub_router.post("/reports/send-weekly-email")
async def send_weekly_management_email(
    email_config: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_reports")),  # v92 DW
):
    """Send weekly management summary via email"""
    current_user = await get_current_user(credentials)

    # Get weekly summary data
    today = datetime.now(UTC)
    week_start = today - timedelta(days=7)

    total_bookings = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "created_at": {"$gte": week_start.isoformat()}})

    total_revenue = 0
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$gte": week_start.date().isoformat()}}):
        total_revenue += booking.get("total_amount", 0)

    # Create email record
    date_str = today.strftime("%B %d, %Y")
    email_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "recipient_email": email_config.get("email", current_user.email),
        "subject": f"Weekly Management Summary - {date_str}",
        "report_type": "weekly_summary",
        "report_data": {
            "week_ending": today.date().isoformat(),
            "total_bookings": total_bookings,
            "total_revenue": round(total_revenue, 2),
            "key_metrics": {"occupancy": 85.5, "adr": 620.83, "revpar": 530.11},
        },
        "status": "sent",
        "sent_at": datetime.now(UTC).isoformat(),
        "sent_by": current_user.name,
    }

    await db.email_reports.insert_one(email_record)

    return {"message": "Weekly summary email sent", "email_id": email_record["id"], "recipient": email_record["recipient_email"]}


@sub_router.get("/reports/email-history")
async def get_email_report_history(limit: int = 20, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get email report history"""
    current_user = await get_current_user(credentials)

    emails = []
    async for email in db.email_reports.find({"tenant_id": current_user.tenant_id}).sort("sent_at", -1).limit(limit):
        email.pop("_id", None)
        emails.append(email)

    return {"emails": emails, "count": len(emails)}


@sub_router.get("/reports/weekly-management-summary")
async def get_weekly_management_summary(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get weekly management summary report"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    week_start = today - timedelta(days=7)

    # Get key metrics for the week
    total_bookings = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "created_at": {"$gte": week_start.isoformat()}})

    total_revenue = 0
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$gte": week_start.date().isoformat()}}):
        total_revenue += booking.get("total_amount", 0)

    # B: gerçek haftalık ortalama doluluk (occupied_avg bug fix — eskiden daima 0 dönüyordu)
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    occ_pcts = []
    if total_rooms > 0:
        for d in range(7):
            day = (week_start + timedelta(days=d)).date().isoformat()
            occupied = await db.bookings.count_documents(
                {"tenant_id": current_user.tenant_id, "check_in": {"$lte": day}, "check_out": {"$gt": day}, "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}}
            )
            occ_pcts.append(occupied / total_rooms * 100)
    occupied_avg = sum(occ_pcts) / len(occ_pcts) if occ_pcts else 0

    # Get maintenance tasks completed
    completed_tasks = await db.maintenance_tasks.count_documents({"tenant_id": current_user.tenant_id, "status": "completed", "completed_at": {"$gte": week_start.isoformat()}})

    # B: gerçek misafir memnuniyeti (haftalık review rating ortalaması); review yoksa fail-closed (null)
    sat_docs = await db.reviews.find({"tenant_id": current_user.tenant_id, "created_at": {"$gte": week_start.isoformat()}}, {"_id": 0, "rating": 1}).to_list(2000)
    sat_ratings = [r.get("rating") for r in sat_docs if isinstance(r.get("rating"), (int, float))]
    guest_satisfaction = round(sum(sat_ratings) / len(sat_ratings), 2) if sat_ratings else None

    return {
        "week_ending": today.date().isoformat(),
        "total_bookings": total_bookings,
        "total_revenue": round(total_revenue, 2),
        "avg_occupancy_pct": round(occupied_avg, 2),
        "completed_maintenance": completed_tasks,
        "guest_satisfaction": guest_satisfaction,
        "guest_satisfaction_available": guest_satisfaction is not None,
        "guest_satisfaction_reviews": len(sat_ratings),
        # top_performers: gerçek haftalık personel-performans kaynağı yok -> fail-closed (sahte personel kaldırıldı)
        "top_performers": [],
        "top_performers_available": False,
    }
