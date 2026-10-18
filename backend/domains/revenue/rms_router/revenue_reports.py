"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.reporting_ledger import charge_amount, posted_revenue_rows
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import NON_COMMERCIAL_STATUSES, as_date, load_stay_night_metrics

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: revenue_reports) ───


@router.get("/revenue/pickup-report")
@cached(ttl=300, key_prefix="rev_pickup_report_v2")
async def get_pickup_report(start_date: str | None = None, end_date: str | None = None, format: str = "json", credentials: HTTPAuthorizationCredentials = Depends(security), _perm=Depends(require_op("view_executive_reports"))):
    """Get pickup report with export capability (JSON, CSV ready)"""
    current_user = await get_current_user(credentials)

    try:
        start_date = datetime.combine(as_date(start_date) if start_date else datetime.now(UTC).date().replace(day=1), datetime.min.time(), UTC)
        end_date = datetime.combine(as_date(end_date), datetime.min.time(), UTC) if end_date else start_date + timedelta(days=29)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Tarih YYYY-MM-DD formatında olmalıdır") from exc
    if end_date < start_date or (end_date - start_date).days > 365 or format not in {"json", "csv"}:
        raise HTTPException(422, "Geçerli en fazla 366 günlük aralık ve json/csv formatını seçin")

    # Get booking pace by arrival date
    pickup_report = []

    # Iterate through each day in range
    current_date = start_date
    while current_date <= end_date:
        # Get bookings for this arrival date
        day_bookings = []

        async for booking in db.bookings.find(
            {"tenant_id": current_user.tenant_id, "$or": [
                {"check_in": {"$gte": current_date, "$lt": current_date + timedelta(days=1)}},
                {"check_in": {"$gte": current_date.date().isoformat(), "$lt": (current_date + timedelta(days=1)).date().isoformat()}}],
                "status": {"$nin": sorted(NON_COMMERCIAL_STATUSES)}}
        ):
            created = as_date(booking.get("created_at"))
            days_before = (current_date.date() - created).days if created else None
            day_bookings.append(
                {
                    "booking_id": booking.get("id"),
                    "created_at": created.isoformat() if created else None,
                    "days_before_arrival": days_before,
                    "room_nights": booking.get("nights", 1),
                    "revenue": booking.get("total_amount", 0),
                    "currency": currency_code(booking.get("currency")),
                }
            )

        # Aggregate data
        total_rooms = len(day_bookings)
        revenue_by_currency = {}
        for booking in day_bookings:
            add_amount(revenue_by_currency, booking.get("currency"), booking["revenue"])
        total_revenue = single_amount(revenue_by_currency)

        # Group by booking window
        booking_windows = {"0-7_days": 0, "8-14_days": 0, "15-30_days": 0, "31-60_days": 0, "61+_days": 0, "unknown": 0}
        windows_by_currency = {}
        rooms_by_currency = {}

        for booking in day_bookings:
            days = booking["days_before_arrival"]
            if days is None or days < 0:
                bucket = "unknown"
            elif days <= 7:
                bucket = "0-7_days"
            elif days <= 14:
                bucket = "8-14_days"
            elif days <= 30:
                bucket = "15-30_days"
            elif days <= 60:
                bucket = "31-60_days"
            else:
                bucket = "61+_days"
            booking_windows[bucket] += 1
            code = booking["currency"]
            windows_by_currency.setdefault(code, dict.fromkeys(booking_windows, 0))[bucket] += 1
            rooms_by_currency[code] = rooms_by_currency.get(code, 0) + 1

        pickup_report.append({"arrival_date": current_date.date().isoformat(), "total_rooms": total_rooms, "total_revenue": total_revenue,
            "total_revenue_by_currency": rounded_totals(revenue_by_currency), "booking_windows": booking_windows,
            "rooms_by_currency": rooms_by_currency, "booking_windows_by_currency": windows_by_currency})

        current_date += timedelta(days=1)

    # If CSV format requested, prepare for export
    if format == "csv":
        # Return data in CSV-friendly format
        csv_data = []
        for row in pickup_report:
            for currency, amount in (row["total_revenue_by_currency"] or {"TRY": 0}).items():
                windows = row["booking_windows_by_currency"].get(currency, dict.fromkeys(row["booking_windows"], 0))
                csv_data.append(
                    {
                        "Arrival Date": row["arrival_date"],
                        "Total Rooms": row["rooms_by_currency"].get(currency, 0),
                        "Currency": currency,
                        "Total Revenue": amount,
                        "0-7 Days": windows["0-7_days"],
                        "8-14 Days": windows["8-14_days"],
                        "15-30 Days": windows["15-30_days"],
                        "31-60 Days": windows["31-60_days"],
                        "61+ Days": windows["61+_days"],
                        "Unknown": windows["unknown"],
                    }
                )

        return {"format": "csv", "data": csv_data, "filename": f"pickup_report_{start_date.date()}_{end_date.date()}.csv"}

    revenue_totals = {}
    for row in pickup_report:
        for currency, amount in row["total_revenue_by_currency"].items():
            add_amount(revenue_totals, currency, amount)
    return {
        "format": "json",
        "date_range": {"start": start_date.date().isoformat(), "end": end_date.date().isoformat()},
        "pickup_report": pickup_report,
        "summary": {"total_rooms": sum(r["total_rooms"] for r in pickup_report), "total_revenue": single_amount(revenue_totals), "total_revenue_by_currency": rounded_totals(revenue_totals)},
    }


@router.get("/revenue/compset-analysis")
async def get_compset_analysis(credentials: HTTPAuthorizationCredentials = Depends(security), _perm=Depends(require_op("view_executive_reports"))):
    """Get competitive set analysis"""
    current_user = await get_current_user(credentials)

    # Get competitor data (would be manually entered or API integrated)
    competitors = []

    async for comp in db.competitors.find({"tenant_id": current_user.tenant_id, "is_active": True}):
        # Get their rates (if available)
        latest_rate = await db.competitor_rates.find_one({"competitor_id": comp.get("id"), "tenant_id": current_user.tenant_id}, sort=[("date", -1)])

        competitors.append(
            {
                "competitor_id": comp.get("id"),
                "competitor_name": comp.get("name"),
                "star_rating": comp.get("star_rating"),
                "location": comp.get("location"),
                "distance_km": comp.get("distance_km"),
                "current_adr": latest_rate.get("adr") if latest_rate else None,
                "current_occupancy": latest_rate.get("occupancy_pct") if latest_rate else None,
                "currency": latest_rate.get("currency") if latest_rate else None,
                "last_updated": str(latest_rate.get("date")) if latest_rate and latest_rate.get("date") else None,
            }
        )

    # Get own property data
    today = datetime.now(UTC)

    metrics = await load_stay_night_metrics(db, current_user.tenant_id, today.date() - timedelta(days=29), today.date(), actual_only=True)
    nights = sum(row.get("sold_rooms", row.get("occupied_rooms", 0)) for row in metrics)
    capacity = sum(row.get("total_rooms", 0) for row in metrics)
    revenues = {}
    for metric in metrics:
        for currency, amount in metric.get("revenue_by_currency", {}).items():
            add_amount(revenues, currency, amount)
    adr = {currency: round(float(amount) / nights, 2) if nights else 0 for currency, amount in revenues.items()}
    revpar = {currency: round(float(amount) / capacity, 2) if capacity else 0 for currency, amount in revenues.items()}
    return {
        "own_property": {"adr": single_amount(adr), "adr_by_currency": adr,
            "occupancy": metrics[-1]["occupancy_rate"] if metrics else 0,
            "revpar": single_amount(revpar), "revpar_by_currency": revpar,
            "basis": "30_day_actual_stay_values", "comparison_note": "Doluluk seçili gün; ADR/RevPAR son 30 gün. Rakip fiyatları kendi gözlem tarihi ve döviziyle gösterilir."},
        "competitors": competitors,
        "compset_count": len(competitors),
        "analysis_date": today.date().isoformat(),
    }


@router.get("/revenue/market-share")
async def get_market_share(credentials: HTTPAuthorizationCredentials = Depends(security), _perm=Depends(require_op("view_executive_reports"))):
    """Get market share analysis"""
    current_user = await get_current_user(credentials)

    # Calculate market share based on bookings and revenue
    today = datetime.now(UTC)
    last_30_days = today.date() - timedelta(days=29)

    # Own performance
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, last_30_days, today.date(), actual_only=True)
    own_rooms = sum(row.get("occupied_rooms", 0) for row in metrics)
    own_revenue = {}
    for row in await posted_revenue_rows(current_user.tenant_id, last_30_days, today.date(), database=db):
        add_amount(own_revenue, row.get("currency"), charge_amount(row))

    # Competitor count is not market sales. Do not manufacture MPI/RGI=100
    # by multiplying this hotel's sales by its number of competitors.

    competitor_count = await db.competitors.count_documents({"tenant_id": current_user.tenant_id, "is_active": True})

    return {
        "period": "30_days",
        "available": False,
        "reason": "competitor_market_totals_missing",
        "competitor_count": competitor_count,
        "own_performance": {"room_nights": own_rooms, "revenue": single_amount(own_revenue), "revenue_by_currency": rounded_totals(own_revenue)},
        "market_totals": {"room_nights": None, "revenue": None},
        "market_share": {"room_share_pct": None, "revenue_share_pct": None, "fair_share_pct": None},
        "performance_index": {"room_mpi": None, "revenue_rgi": None},
    }


# --------------------------------------------------------------------------
# IT & Security - User Activity Logs, API Rate Limits
# --------------------------------------------------------------------------
