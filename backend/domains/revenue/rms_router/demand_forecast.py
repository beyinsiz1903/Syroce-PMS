"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from modules.pms_core.role_permission_service import require_op  # v99 DW
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import (
    DemandForecastRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: demand_forecast) ───


@router.get("/rms/demand-forecast")
async def get_demand_forecast(
    start_date: str = None,
    end_date: str = None,
    days: int = None,
    current_user: User = Depends(get_current_user)
):
    """Get demand forecast (supports days param or start_date/end_date)"""
    query = {'tenant_id': current_user.tenant_id}

    if days and not start_date:
        start_date = datetime.now(UTC).date().isoformat()
        end_date = (datetime.now(UTC) + timedelta(days=days)).date().isoformat()

    if start_date and end_date:
        query['date'] = {'$gte': start_date, '$lte': end_date}

    forecasts = await db.demand_forecasts.find(
        query,
        {'_id': 0}
    ).sort('date', 1).to_list(365)

    # If no stored forecasts, generate basic ones from bookings
    if not forecasts and days:
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        if total_rooms == 0:
            total_rooms = 50
        for d in range(days):
            cur_date = (datetime.now(UTC) + timedelta(days=d)).date()
            booked = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'check_in_date': {'$lte': cur_date.isoformat()},
                'check_out_date': {'$gt': cur_date.isoformat()},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            })
            occ = round(booked / total_rooms * 100, 1) if total_rooms else 0
            dow = cur_date.weekday()
            base_demand = 50 + (15 if dow in [4, 5] else 0) + (occ * 0.3)
            forecasts.append({
                'date': cur_date.isoformat(),
                'demand_index': round(min(base_demand, 100), 1),
                'occupancy_pct': occ
            })

    return {'forecast': forecasts, 'forecasts': forecasts, 'count': len(forecasts)}



@router.post("/rms/demand-forecast")
async def generate_demand_forecast(
    request: DemandForecastRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Generate advanced demand forecast with ML-inspired algorithm (90-day capable)"""
    start = datetime.fromisoformat(request.start_date)
    end = datetime.fromisoformat(request.end_date)
    days = (end - start).days + 1

    # Get historical booking data for trend analysis
    historical_start = datetime.now(UTC) - timedelta(days=365)
    historical_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': historical_start.isoformat()}
    }, {'_id': 0, 'check_in_date': 1, 'check_out_date': 1, 'created_at': 1}).to_list(10000)

    # Calculate historical occupancy patterns
    historical_occupancy_by_dow = {i: [] for i in range(7)}  # Day of week
    historical_occupancy_by_month = {i: [] for i in range(1, 13)}  # Month

    for booking in historical_bookings:
        try:
            checkin = datetime.fromisoformat(booking['check_in_date'])
            dow = checkin.weekday()
            month = checkin.month
            historical_occupancy_by_dow[dow].append(1)
            historical_occupancy_by_month[month].append(1)
        except Exception:
            pass

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    if total_rooms == 0:
        total_rooms = 100  # Default for demo

    forecasts = []
    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()
        date_obj = datetime.fromisoformat(current_date).replace(tzinfo=UTC)

        # Advanced forecast model with multiple factors
        day_of_week = date_obj.weekday()
        month = date_obj.month
        days_from_now = (date_obj - datetime.now(UTC)).days

        # 1. Day of Week Pattern (30% weight)
        dow_historical_count = len(historical_occupancy_by_dow.get(day_of_week, []))
        if dow_historical_count > 10:
            dow_factor = min(dow_historical_count / 50, 1.0)  # Normalize
        else:
            # Default pattern if no history
            if day_of_week in [4, 5]:  # Friday, Saturday
                dow_factor = 0.85
            elif day_of_week in [6]:  # Sunday
                dow_factor = 0.70
            else:
                dow_factor = 0.60

        # 2. Seasonal Pattern (25% weight)
        month_historical_count = len(historical_occupancy_by_month.get(month, []))
        if month_historical_count > 20:
            seasonal_factor = min(month_historical_count / 100, 1.3)
        else:
            # Default seasonal pattern
            if month in [6, 7, 8]:  # Summer
                seasonal_factor = 1.25
            elif month in [12, 1]:  # Winter holidays
                seasonal_factor = 1.15
            elif month in [3, 4, 5]:  # Spring
                seasonal_factor = 1.05
            else:
                seasonal_factor = 0.95

        # 3. Lead Time Factor (20% weight)
        if days_from_now < 7:
            lead_factor = 1.15  # Last minute bookings boost
        elif days_from_now < 30:
            lead_factor = 1.05
        elif days_from_now < 60:
            lead_factor = 1.00
        else:
            lead_factor = 0.92  # Far future less certain

        # 4. Current Booking Trend (15% weight)
        recent_booking_count = len([b for b in historical_bookings if b.get('created_at') and (datetime.now(UTC) - datetime.fromisoformat(b['created_at']).replace(tzinfo=UTC)).days < 30])
        if recent_booking_count > 50:
            trend_factor = 1.10  # Strong recent trend
        elif recent_booking_count > 20:
            trend_factor = 1.05
        else:
            trend_factor = 1.00

        # 5. Special Events (10% weight) - Can be enhanced with event calendar
        # Check if weekend or holiday
        is_friday_saturday = day_of_week in [4, 5]
        event_factor = 1.12 if is_friday_saturday else 1.0

        # Combine all factors
        base_demand = 0.65  # Base occupancy
        forecasted_demand = base_demand * dow_factor * (seasonal_factor / 1.1) * lead_factor * (trend_factor / 1.05) * event_factor

        # Cap at realistic bounds
        forecasted_demand = min(max(forecasted_demand, 0.15), 0.98)

        forecasted_rooms = int(total_rooms * forecasted_demand)
        forecasted_occupancy = round(forecasted_demand * 100, 1)

        # Dynamic confidence based on factors
        confidence = 0.0
        confidence_factors = []

        # Historical data quality
        if dow_historical_count > 20:
            confidence += 0.25
            confidence_factors.append("Strong day-of-week history")
        elif dow_historical_count > 5:
            confidence += 0.15
            confidence_factors.append("Moderate day-of-week history")
        else:
            confidence += 0.05
            confidence_factors.append("Limited day-of-week history")

        # Seasonal data quality
        if month_historical_count > 30:
            confidence += 0.25
            confidence_factors.append("Strong seasonal pattern")
        elif month_historical_count > 10:
            confidence += 0.15
            confidence_factors.append("Moderate seasonal pattern")
        else:
            confidence += 0.05
            confidence_factors.append("Limited seasonal data")

        # Lead time certainty
        if days_from_now < 30:
            confidence += 0.30
            confidence_factors.append("Near-term forecast (high certainty)")
        elif days_from_now < 60:
            confidence += 0.20
            confidence_factors.append("Medium-term forecast")
        else:
            confidence += 0.10
            confidence_factors.append("Long-term forecast (lower certainty)")

        # Recent booking trend
        if recent_booking_count > 30:
            confidence += 0.20
            confidence_factors.append("Strong recent booking trend")
        elif recent_booking_count > 10:
            confidence += 0.10
            confidence_factors.append("Moderate booking activity")

        confidence = min(confidence, 0.95)

        # Confidence level
        if confidence >= 0.70:
            confidence_level = "High"
        elif confidence >= 0.45:
            confidence_level = "Medium"
        else:
            confidence_level = "Low"

        # Forecast trend
        if forecasted_occupancy > 80:
            trend = "High Demand"
        elif forecasted_occupancy > 60:
            trend = "Strong Demand"
        elif forecasted_occupancy > 40:
            trend = "Moderate Demand"
        else:
            trend = "Low Demand"

        forecast = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'date': current_date,
            'forecasted_occupancy': forecasted_occupancy,
            'forecasted_rooms': forecasted_rooms,
            'total_rooms': total_rooms,
            'day_of_week': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day_of_week],
            'is_weekend': day_of_week in [4, 5, 6],
            'confidence': round(confidence, 2),
            'confidence_level': confidence_level,
            'confidence_factors': confidence_factors,
            'trend': trend,
            'seasonal_factor': round(seasonal_factor, 2),
            'lead_time_days': days_from_now,
            'model_version': '2.0-advanced',
            'generated_at': datetime.now(UTC).isoformat()
        }
        forecasts.append(forecast)

    # Calculate summary statistics
    avg_occupancy = sum(f['forecasted_occupancy'] for f in forecasts) / len(forecasts) if forecasts else 0
    high_demand_days = sum(1 for f in forecasts if f['forecasted_occupancy'] > 75)
    low_demand_days = sum(1 for f in forecasts if f['forecasted_occupancy'] < 40)

    # Save forecasts
    if forecasts:
        await db.demand_forecasts.insert_many([f.copy() for f in forecasts])

    return {
        'message': f'Generated {len(forecasts)} demand forecasts',
        'forecasts': forecasts,
        'summary': {
            'total_days': len(forecasts),
            'avg_forecasted_occupancy': round(avg_occupancy, 1),
            'high_demand_days': high_demand_days,
            'moderate_demand_days': len(forecasts) - high_demand_days - low_demand_days,
            'low_demand_days': low_demand_days,
            'date_range': f"{request.start_date} to {request.end_date}",
            'model_version': '2.0-advanced'
        }
    }

