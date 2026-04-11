"""
B2B Analytics Dashboard — Acente & API Kullanim Analitikleri
============================================================
Endpoints:
  GET /api/b2b-analytics/summary          — KPI özeti (booking, gelir, aktif acente, API çağrısı)
  GET /api/b2b-analytics/agency-breakdown  — Acente bazlı metrik tablosu
  GET /api/b2b-analytics/booking-trends    — Zaman serisi (çizgi/bar grafik)
  GET /api/b2b-analytics/api-usage         — API kullanım dağılımı (event_type bazlı)
  GET /api/b2b-analytics/top-endpoints     — En çok kullanılan B2B endpoint'leri
  GET /api/b2b-analytics/export            — CSV dışa aktarma
"""
import csv
import io
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.database import db
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/b2b-analytics", tags=["B2B Analytics"])

HOTEL_ROLES = {
    UserRole.SUPER_ADMIN, UserRole.ADMIN,
    "super_admin", "admin", "manager", "staff",
}


def _require_hotel_role(user: User):
    if user.role not in HOTEL_ROLES:
        raise HTTPException(status_code=403, detail="Bu sayfaya erisim yetkiniz yok.")


def _date_range(start_date: str | None, end_date: str | None, period: str = "30d"):
    now = datetime.now(UTC)
    if start_date and end_date:
        return start_date, end_date + "T23:59:59"

    days_map = {"7d": 7, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
    days = days_map.get(period, 30)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%dT23:59:59")


B2B_EVENT_TYPES = [
    "api_call", "reservation_created", "reservation_cancelled",
    "channel_sync", "webhook_received",
]


@router.get("/summary")
async def get_b2b_summary(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    usage_pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": sd, "$lte": ed}}},
        {"$group": {"_id": "$event_type", "total": {"$sum": "$count"}}},
    ]
    usage_results = await db.usage_daily.aggregate(usage_pipeline).to_list(100)
    usage_map = {r["_id"]: r["total"] for r in usage_results}

    booking_match = {"tenant_id": tenant_id, "created_at": {"$gte": sd, "$lte": ed}}
    total_bookings = await db.agency_booking_requests.count_documents(booking_match)

    approved_match = {**booking_match, "status": "approved"}
    approved_bookings = await db.agency_booking_requests.count_documents(approved_match)

    revenue_pipeline = [
        {"$match": {**booking_match, "status": "approved"}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$total_amount"}, "total_commission": {"$sum": "$commission_amount"}}},
    ]
    revenue_result = await db.agency_booking_requests.aggregate(revenue_pipeline).to_list(1)
    revenue_data = revenue_result[0] if revenue_result else {"total_revenue": 0, "total_commission": 0}

    active_agencies = await db.agencies.count_documents({"tenant_id": tenant_id, "status": "active"})
    total_agencies = await db.agencies.count_documents({"tenant_id": tenant_id})

    conversion_rate = (approved_bookings / total_bookings * 100) if total_bookings > 0 else 0

    return {
        "period": {"start": sd, "end": ed},
        "kpis": {
            "total_bookings": total_bookings,
            "approved_bookings": approved_bookings,
            "conversion_rate": round(conversion_rate, 1),
            "total_revenue": revenue_data.get("total_revenue", 0) or 0,
            "total_commission": revenue_data.get("total_commission", 0) or 0,
            "net_revenue": (revenue_data.get("total_revenue", 0) or 0) - (revenue_data.get("total_commission", 0) or 0),
            "active_agencies": active_agencies,
            "total_agencies": total_agencies,
            "api_calls": usage_map.get("api_call", 0),
            "webhook_events": usage_map.get("webhook_received", 0),
            "channel_syncs": usage_map.get("channel_sync", 0),
        },
    }


@router.get("/agency-breakdown")
async def get_agency_breakdown(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    agencies = await db.agencies.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "commission_rate": 1, "contact_name": 1},
    ).to_list(200)

    result = []
    for agency in agencies:
        aid = agency.get("id", "")
        match = {"tenant_id": tenant_id, "agency_id": aid, "created_at": {"$gte": sd, "$lte": ed}}

        booking_count = await db.agency_booking_requests.count_documents(match)
        approved_count = await db.agency_booking_requests.count_documents({**match, "status": "approved"})

        rev_pipeline = [
            {"$match": {**match, "status": "approved"}},
            {"$group": {"_id": None, "revenue": {"$sum": "$total_amount"}, "commission": {"$sum": "$commission_amount"}}},
        ]
        rev_result = await db.agency_booking_requests.aggregate(rev_pipeline).to_list(1)
        rev = rev_result[0] if rev_result else {"revenue": 0, "commission": 0}

        result.append({
            "agency_id": aid,
            "agency_name": agency.get("name", ""),
            "status": agency.get("status", ""),
            "contact_name": agency.get("contact_name", ""),
            "commission_rate": agency.get("commission_rate", 0),
            "total_bookings": booking_count,
            "approved_bookings": approved_count,
            "conversion_rate": round(approved_count / booking_count * 100, 1) if booking_count > 0 else 0,
            "revenue": rev.get("revenue", 0) or 0,
            "commission": rev.get("commission", 0) or 0,
            "net_revenue": (rev.get("revenue", 0) or 0) - (rev.get("commission", 0) or 0),
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return {"period": {"start": sd, "end": ed}, "agencies": result}


@router.get("/booking-trends")
async def get_booking_trends(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    agency_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    match_q: dict = {"tenant_id": tenant_id, "created_at": {"$gte": sd, "$lte": ed}}
    if agency_id:
        match_q["agency_id"] = agency_id

    pipeline = [
        {"$match": match_q},
        {"$addFields": {"date_key": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {
            "_id": {"date": "$date_key", "status": "$status"},
            "count": {"$sum": 1},
            "revenue": {"$sum": "$total_amount"},
        }},
        {"$sort": {"_id.date": 1}},
    ]
    results = await db.agency_booking_requests.aggregate(pipeline).to_list(2000)

    date_map: dict = {}
    for r in results:
        d = r["_id"]["date"]
        if d not in date_map:
            date_map[d] = {"date": d, "total": 0, "approved": 0, "rejected": 0, "pending": 0, "revenue": 0}
        date_map[d]["total"] += r["count"]
        status = r["_id"]["status"]
        if status == "approved":
            date_map[d]["approved"] += r["count"]
            date_map[d]["revenue"] += r.get("revenue", 0) or 0
        elif status in ("rejected", "expired"):
            date_map[d]["rejected"] += r["count"]
        else:
            date_map[d]["pending"] += r["count"]

    trends = sorted(date_map.values(), key=lambda x: x["date"])
    return {"period": {"start": sd, "end": ed}, "trends": trends}


@router.get("/api-usage")
async def get_api_usage(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": sd, "$lte": ed}}},
        {"$group": {
            "_id": {"date": "$date", "event_type": "$event_type"},
            "count": {"$sum": "$count"},
        }},
        {"$sort": {"_id.date": 1}},
    ]
    results = await db.usage_daily.aggregate(pipeline).to_list(5000)

    date_map: dict = {}
    for r in results:
        d = r["_id"]["date"]
        et = r["_id"]["event_type"]
        if d not in date_map:
            date_map[d] = {"date": d}
        date_map[d][et] = r["count"]

    timeline = sorted(date_map.values(), key=lambda x: x["date"])

    totals_pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": sd, "$lte": ed}}},
        {"$group": {"_id": "$event_type", "total": {"$sum": "$count"}}},
        {"$sort": {"total": -1}},
    ]
    totals_result = await db.usage_daily.aggregate(totals_pipeline).to_list(50)
    totals = [{"event_type": r["_id"], "total": r["total"]} for r in totals_result]

    return {"period": {"start": sd, "end": ed}, "timeline": timeline, "totals": totals}


@router.get("/top-endpoints")
async def get_top_endpoints(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": sd, "$lte": ed}}},
        {"$group": {"_id": "$event_type", "total_calls": {"$sum": "$count"}}},
        {"$sort": {"total_calls": -1}},
        {"$limit": limit},
    ]
    results = await db.usage_daily.aggregate(pipeline).to_list(limit)

    grand_total = sum(r["total_calls"] for r in results) or 1
    endpoints = []
    for r in results:
        endpoints.append({
            "event_type": r["_id"],
            "total_calls": r["total_calls"],
            "percentage": round(r["total_calls"] / grand_total * 100, 1),
        })

    return {"period": {"start": sd, "end": ed}, "endpoints": endpoints}


@router.get("/export")
async def export_b2b_data(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    period: str = Query("30d"),
    export_type: str = Query("bookings", regex="^(bookings|agencies|usage)$"),
    current_user: User = Depends(get_current_user),
):
    _require_hotel_role(current_user)
    tenant_id = current_user.tenant_id
    sd, ed = _date_range(start_date, end_date, period)

    output = io.StringIO()

    if export_type == "bookings":
        writer = csv.writer(output)
        writer.writerow(["Tarih", "Acente", "Durum", "Tutar", "Komisyon", "Net"])

        cursor = db.agency_booking_requests.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": sd, "$lte": ed}},
            {"_id": 0, "created_at": 1, "agency_name": 1, "status": 1, "total_amount": 1, "commission_amount": 1},
        ).sort("created_at", -1)
        async for doc in cursor:
            total = doc.get("total_amount", 0) or 0
            commission = doc.get("commission_amount", 0) or 0
            writer.writerow([
                doc.get("created_at", ""),
                doc.get("agency_name", ""),
                doc.get("status", ""),
                total,
                commission,
                total - commission,
            ])

    elif export_type == "agencies":
        writer = csv.writer(output)
        writer.writerow(["Acente", "Durum", "Komisyon %", "Toplam Rez.", "Onaylanan", "Gelir"])

        agencies = await db.agencies.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "id": 1, "name": 1, "status": 1, "commission_rate": 1},
        ).to_list(500)

        for ag in agencies:
            match = {"tenant_id": tenant_id, "agency_id": ag.get("id", ""), "created_at": {"$gte": sd, "$lte": ed}}
            total = await db.agency_booking_requests.count_documents(match)
            approved = await db.agency_booking_requests.count_documents({**match, "status": "approved"})
            rev_pipeline = [
                {"$match": {**match, "status": "approved"}},
                {"$group": {"_id": None, "revenue": {"$sum": "$total_amount"}}},
            ]
            rev = await db.agency_booking_requests.aggregate(rev_pipeline).to_list(1)
            revenue = rev[0]["revenue"] if rev else 0
            writer.writerow([ag.get("name", ""), ag.get("status", ""), ag.get("commission_rate", 0), total, approved, revenue])

    elif export_type == "usage":
        writer = csv.writer(output)
        writer.writerow(["Tarih", "Olay Tipi", "Adet"])

        cursor = db.usage_daily.find(
            {"tenant_id": tenant_id, "date": {"$gte": sd, "$lte": ed}},
            {"_id": 0, "date": 1, "event_type": 1, "count": 1},
        ).sort("date", -1)
        async for doc in cursor:
            writer.writerow([doc.get("date", ""), doc.get("event_type", ""), doc.get("count", 0)])

    output.seek(0)
    filename = f"b2b_{export_type}_{sd}_{ed}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
