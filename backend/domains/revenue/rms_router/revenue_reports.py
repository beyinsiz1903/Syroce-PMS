"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from core.tenant_currency import get_tenant_currency
from models.schemas import User
from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.reporting_dates import date_period_match
from modules.pms_core.reporting_ledger import charge_amount, posted_revenue_rows
from modules.pms_core.reservation_reporting import reservation_value
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import OCCUPYING_STATUSES, as_date, booking_nights, load_stay_night_metrics

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: revenue_reports) ───


@router.get("/revenue/pickup-report")
@cached(ttl=300, key_prefix="rev_pickup_report_v3")
async def get_pickup_report(
    start_date: str | None = None, end_date: str | None = None, format: str = "json",
    current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_executive_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    """Current valid reservations by arrival day/window, not net movement pickup."""
    try:
        first = date.fromisoformat(start_date) if start_date else datetime.now(UTC).date().replace(day=1)
        last = date.fromisoformat(end_date) if end_date else first + timedelta(days=29)
        if (start_date and first.isoformat() != start_date) or (end_date and last.isoformat() != end_date) or last == date.max:
            raise ValueError("Noncanonical report date")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(422, "Tarih YYYY-MM-DD formatında olmalıdır") from exc
    if last < first or (last - first).days >= 366 or format not in {"json", "csv"}:
        raise HTTPException(422, "Geçerli en fazla 366 günlük aralık ve json/csv formatını seçin")
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id,
        **date_period_match("check_in", first, last), "status": {"$in": sorted(OCCUPYING_STATUSES)}}, {"_id": 0}).to_list(None)
    by_day = defaultdict(list)
    invalid_stays = 0
    for booking in bookings:
        if not booking_nights(booking):
            invalid_stays += 1
            continue
        by_day[as_date(booking.get("check_in"))].append(booking)
    result, totals = [], {}
    invalid_amounts = 0
    windows_template = {"0-7_days": 0, "8-14_days": 0, "15-30_days": 0, "31-60_days": 0, "61+_days": 0, "unknown": 0}
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        rows = by_day[day]
        values, rooms, windows, currency_windows, bad = {}, {}, dict(windows_template), {}, {}
        for booking in rows:
            code = currency_code(booking.get("currency"), currency)
            rooms[code] = rooms.get(code, 0) + 1
            created = as_date(booking.get("created_at"))
            days_before = (day - created).days if created else -1
            bucket = next((key for limit, key in [(7, "0-7_days"), (14, "8-14_days"), (30, "15-30_days"), (60, "31-60_days")] if 0 <= days_before <= limit), "61+_days" if days_before >= 0 else "unknown")
            windows[bucket] += 1
            currency_windows.setdefault(code, dict(windows_template))[bucket] += 1
            value = reservation_value(booking)
            if value is None:
                invalid_amounts += 1
                bad[code] = bad.get(code, 0) + 1
            else:
                add_amount(values, code, value)
                add_amount(totals, code, value)
        result.append({"arrival_date": day.isoformat(), "total_rooms": len(rows), "total_room_nights": sum(booking_nights(booking) for booking in rows),
            "total_revenue": None if bad and not values else single_amount(values), "total_revenue_by_currency": rounded_totals(values),
            "booking_windows": windows, "rooms_by_currency": rooms, "booking_windows_by_currency": currency_windows, "invalid_amounts_by_currency": bad})
    metadata = {"currency": currency, "date_range": {"start": first.isoformat(), "end": last.isoformat()},
        "basis": "arrival_cohort_current_valid_booking_value_not_net_pickup_or_posted_revenue",
        "data_quality": {"invalid_amounts": invalid_amounts, "invalid_stays": invalid_stays}}
    if format == "csv":
        csv_data = []
        for row in result:
            for code in (row["rooms_by_currency"] or {currency: 0}):
                windows = row["booking_windows_by_currency"].get(code, dict(windows_template))
                csv_data.append({"Arrival Date": row["arrival_date"], "Total Rooms": row["rooms_by_currency"].get(code, 0),
                    "Currency": code, "Total Revenue": row["total_revenue_by_currency"].get(code, None if row["rooms_by_currency"].get(code) else 0),
                    "0-7 Days": windows["0-7_days"], "8-14 Days": windows["8-14_days"], "15-30 Days": windows["15-30_days"],
                    "31-60 Days": windows["31-60_days"], "61+ Days": windows["61+_days"], "Unknown": windows["unknown"],
                    "Invalid Amounts": row["invalid_amounts_by_currency"].get(code, 0), "Value Basis": metadata["basis"]})
        return {"format": "csv", "data": csv_data, "filename": f"pickup_report_{first}_{last}.csv", **metadata}
    return {"format": "json", "pickup_report": result, **metadata,
        "summary": {"total_rooms": sum(row["total_rooms"] for row in result), "total_room_nights": sum(row["total_room_nights"] for row in result),
            "total_revenue": None if invalid_amounts and not totals else single_amount(totals), "total_revenue_by_currency": rounded_totals(totals)}}


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
