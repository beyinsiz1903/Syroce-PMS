"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import (
    AddCompetitorRequest,
    AutoPricingRequest,
    DemandForecastRequest,
    ScrapePricesRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================

@router.get("/rms/comp-set")
async def get_comp_set(current_user: User = Depends(get_current_user)):
    """Get competitor set data with pricing metrics"""
    comp_set = await db.comp_set.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    # Enrich with latest pricing data
    for comp in comp_set:
        latest_pricing = await db.comp_pricing.find_one(
            {'tenant_id': current_user.tenant_id, 'competitor_id': comp.get('id')},
            {'_id': 0},
            sort=[('date', -1)]
        )
        if latest_pricing:
            comp['avg_rate'] = latest_pricing.get('standard_rate', 0)
        if 'avg_rate' not in comp:
            comp['avg_rate'] = 0
        if 'occupancy_rate' not in comp:
            comp['occupancy_rate'] = 0
        if 'revpar' not in comp:
            comp['revpar'] = round(comp['avg_rate'] * comp['occupancy_rate'] / 100, 2) if comp['avg_rate'] else 0
        if 'distance_km' not in comp:
            comp['distance_km'] = 0

    return {'competitors': comp_set, 'comp_set': comp_set, 'count': len(comp_set)}

@router.post("/rms/comp-set")
async def add_competitor(
    request: AddCompetitorRequest,
    current_user: User = Depends(get_current_user)
):
    """Add competitor to comp set"""
    competitor = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': request.name,
        'location': request.location,
        'star_rating': request.star_rating,
        'url': request.url,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat()
    }

    competitor_copy = competitor.copy()
    await db.comp_set.insert_one(competitor_copy)
    return competitor

@router.get("/rms/comp-pricing")
async def get_competitor_pricing(
    date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get competitor pricing for specific date"""
    query = {'tenant_id': current_user.tenant_id}
    if date:
        query['date'] = date

    pricing = await db.comp_pricing.find(
        query,
        {'_id': 0}
    ).sort('date', -1).limit(100).to_list(100)

    return {'pricing': pricing, 'count': len(pricing)}

@router.post("/rms/scrape-comp-prices")
async def scrape_competitor_prices(
    request: ScrapePricesRequest,
    current_user: User = Depends(get_current_user)
):
    """Scrape competitor prices for specific date"""
    date = request.date
    # Get all active competitors
    competitors = await db.comp_set.find(
        {'tenant_id': current_user.tenant_id, 'status': 'active'},
        {'_id': 0}
    ).to_list(100)

    scraped_prices = []
    for comp in competitors:
        price_data = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'competitor_id': comp['id'],
            'competitor_name': comp['name'],
            'date': date,
            'lowest_rate': 120.00 + (hash(comp['id']) % 50),  # Mock pricing
            'standard_rate': 150.00 + (hash(comp['id']) % 80),
            'scraped_at': datetime.now(UTC).isoformat()
        }
        await db.comp_pricing.insert_one(price_data.copy())
        scraped_prices.append(price_data)

    return {
        'message': f'Scraped prices for {len(scraped_prices)} competitors',
        'prices': scraped_prices
    }


# ── PRICING STRATEGY ──

@router.get("/rms/pricing-strategy")
async def get_pricing_strategy(current_user: User = Depends(get_current_user)):
    """Get current pricing strategy with computed metrics"""
    strategy = await db.rms_pricing_strategy.find_one(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    )

    # Compute current ADR from recent bookings
    recent_bookings = await db.bookings.find(
        {
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        },
        {'_id': 0, 'total_price': 1, 'nights': 1}
    ).sort('created_at', -1).to_list(100)

    total_revenue = sum(b.get('total_price', 0) for b in recent_bookings)
    total_nights = sum(b.get('nights', 1) for b in recent_bookings)
    current_adr = round(total_revenue / total_nights, 2) if total_nights > 0 else 0

    # Get pending recommendations for suggested rate
    pending_recs = await db.rms_pricing_recommendations.find(
        {'tenant_id': current_user.tenant_id, 'status': 'pending'},
        {'_id': 0, 'suggested_rate': 1}
    ).to_list(50)
    avg_suggested = round(
        sum(r.get('suggested_rate', 0) for r in pending_recs) / len(pending_recs), 2
    ) if pending_recs else current_adr

    # Compute market position from comp-set
    comp_avg = 0
    comp_set = await db.comp_pricing.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0, 'standard_rate': 1}
    ).sort('date', -1).to_list(20)
    if comp_set:
        comp_avg = round(sum(c.get('standard_rate', 0) for c in comp_set) / len(comp_set), 2)

    if comp_avg > 0 and current_adr > 0:
        ratio = current_adr / comp_avg
        if ratio > 1.15:
            market_position = "Premium"
        elif ratio > 0.95:
            market_position = "Mid-Range"
        elif ratio > 0.75:
            market_position = "Economy"
        else:
            market_position = "Budget"
    else:
        market_position = "N/A"

    auto_enabled = strategy.get('auto_pricing_enabled', False) if strategy else False

    return {
        'current_rate': current_adr,
        'recommended_rate': avg_suggested,
        'auto_pricing_enabled': auto_enabled,
        'market_position': market_position,
        'comp_avg_rate': comp_avg,
        'pending_recommendations': len(pending_recs),
    }


class PricingStrategyUpdateRequest(BaseModel):
    auto_pricing_enabled: bool


@router.put("/rms/pricing-strategy")
async def update_pricing_strategy(
    request: PricingStrategyUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update pricing strategy settings"""
    await db.rms_pricing_strategy.update_one(
        {'tenant_id': current_user.tenant_id},
        {'$set': {
            'tenant_id': current_user.tenant_id,
            'auto_pricing_enabled': request.auto_pricing_enabled,
            'updated_at': datetime.now(UTC).isoformat(),
            'updated_by': current_user.id,
        }},
        upsert=True
    )
    return {'message': 'Pricing strategy updated', 'auto_pricing_enabled': request.auto_pricing_enabled}


@router.get("/rms/price-adjustments")
async def get_price_adjustments(
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get recent price adjustments history"""
    adjustments = await db.rms_price_adjustments.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('date', -1).to_list(limit)

    # If no dedicated adjustments, pull from applied recommendations
    if not adjustments:
        applied = await db.rms_pricing_recommendations.find(
            {'tenant_id': current_user.tenant_id, 'status': 'applied'},
            {'_id': 0}
        ).sort('applied_at', -1).to_list(limit)
        adjustments = [
            {
                'id': a.get('id', ''),
                'date': a.get('date', ''),
                'reason': a.get('reasoning', a.get('reason', 'Otomatik fiyat önerisi uygulandı')),
                'old_rate': a.get('current_rate', 0),
                'new_rate': a.get('suggested_rate', 0),
                'room_type': a.get('room_type', ''),
                'applied_at': a.get('applied_at', ''),
            }
            for a in applied
        ]

    return {'adjustments': adjustments, 'count': len(adjustments)}


@router.post("/rms/apply-recommendations")
async def apply_all_recommendations(current_user: User = Depends(get_current_user)):
    """Apply all pending pricing recommendations"""
    pending = await db.rms_pricing_recommendations.find(
        {'tenant_id': current_user.tenant_id, 'status': 'pending'},
        {'_id': 0}
    ).to_list(100)

    if not pending:
        return {'message': 'Uygulanacak öneri bulunamadı', 'applied_count': 0}

    applied_count = 0
    now = datetime.now(UTC).isoformat()

    for rec in pending:
        # Update rate calendar
        await db.rate_calendar.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'date': rec.get('date'),
                'room_type': rec.get('room_type', 'Standard')
            },
            {'$set': {
                'rate': rec.get('suggested_rate'),
                'updated_at': now,
                'updated_by': current_user.id
            }},
            upsert=True
        )

        # Mark recommendation as applied
        await db.rms_pricing_recommendations.update_one(
            {'id': rec.get('id'), 'tenant_id': current_user.tenant_id},
            {'$set': {'status': 'applied', 'applied_at': now, 'applied_by': current_user.id}}
        )

        # Save to price adjustments history
        await db.rms_price_adjustments.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'date': rec.get('date', now),
            'reason': rec.get('reasoning', 'Toplu öneri uygulaması'),
            'old_rate': rec.get('current_rate', 0),
            'new_rate': rec.get('suggested_rate', 0),
            'room_type': rec.get('room_type', ''),
            'applied_at': now,
            'applied_by': current_user.id,
        })

        applied_count += 1

    return {'message': f'{applied_count} öneri uygulandı', 'applied_count': applied_count}


@router.post("/rms/auto-pricing")
async def generate_auto_pricing(
    request: AutoPricingRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate automatic pricing recommendations with advanced confidence scoring"""
    # Parse dates
    start = datetime.fromisoformat(request.start_date)
    end = datetime.fromisoformat(request.end_date)
    room_type = request.room_type
    days = (end - start).days + 1

    # Get room types
    room_types_query = {'tenant_id': current_user.tenant_id}
    if room_type:
        room_types_query['name'] = room_type

    room_types = await db.room_types.find(room_types_query, {'_id': 0}).to_list(100)

    # Get competitor pricing for comparison
    comp_avg_prices = {}
    comp_pricing = await db.comp_pricing.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(1000)

    for price in comp_pricing:
        date = price.get('date')
        if date:
            if date not in comp_avg_prices:
                comp_avg_prices[date] = []
            comp_avg_prices[date].append(price.get('standard_rate', 0))

    recommendations = []
    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()
        date_obj = datetime.fromisoformat(current_date)

        for rt in room_types:
            # Get bookings for this date
            bookings = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_type': rt['name'],
                'check_in_date': {'$lte': current_date},
                'check_out_date': {'$gt': current_date},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            })

            # Get total rooms
            total_rooms = await db.rooms.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_type': rt['name']
            })

            occupancy = (bookings / total_rooms * 100) if total_rooms > 0 else 0
            base_rate = rt.get('base_rate', 100.0)

            # Get booking pace (bookings in last 7 days for this date)
            recent_bookings = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_type': rt['name'],
                'check_in_date': {'$lte': current_date},
                'check_out_date': {'$gt': current_date},
                'created_at': {'$gte': (datetime.now(UTC) - timedelta(days=7)).isoformat()}
            })

            booking_pace = recent_bookings / 7 if recent_bookings > 0 else 0

            # Get competitor average price for this date
            comp_avg = sum(comp_avg_prices.get(current_date, [])) / len(comp_avg_prices.get(current_date, [1])) if comp_avg_prices.get(current_date) else base_rate

            # Day of week factor
            day_of_week = date_obj.weekday()
            is_weekend = day_of_week in [4, 5]  # Friday, Saturday

            # Seasonal factor
            month = date_obj.month
            is_peak_season = month in [6, 7, 8, 12]

            # ENHANCED PRICING ALGORITHM with multiple factors
            price_multiplier = 1.0
            reasoning_factors = []

            # Factor 1: Current Occupancy (40% weight)
            if occupancy > 90:
                price_multiplier *= 1.25
                reasoning_factors.append(f"Very high occupancy ({occupancy:.0f}%): +25%")
            elif occupancy > 75:
                price_multiplier *= 1.15
                reasoning_factors.append(f"High occupancy ({occupancy:.0f}%): +15%")
            elif occupancy > 50:
                price_multiplier *= 1.05
                reasoning_factors.append(f"Moderate occupancy ({occupancy:.0f}%): +5%")
            elif occupancy > 30:
                price_multiplier *= 0.95
                reasoning_factors.append(f"Low occupancy ({occupancy:.0f}%): -5%")
            else:
                price_multiplier *= 0.85
                reasoning_factors.append(f"Very low occupancy ({occupancy:.0f}%): -15%")

            # Factor 2: Booking Pace (20% weight)
            if booking_pace > 2:
                price_multiplier *= 1.08
                reasoning_factors.append(f"Strong booking pace ({booking_pace:.1f}/day): +8%")
            elif booking_pace > 1:
                price_multiplier *= 1.03
                reasoning_factors.append(f"Good booking pace ({booking_pace:.1f}/day): +3%")
            elif booking_pace < 0.5 and occupancy < 60:
                price_multiplier *= 0.95
                reasoning_factors.append(f"Slow booking pace ({booking_pace:.1f}/day): -5%")

            # Factor 3: Day of Week (15% weight)
            if is_weekend:
                price_multiplier *= 1.10
                reasoning_factors.append("Weekend demand: +10%")

            # Factor 4: Seasonality (15% weight)
            if is_peak_season:
                price_multiplier *= 1.12
                reasoning_factors.append("Peak season: +12%")

            # Factor 5: Competitor Pricing (10% weight)
            if comp_avg > 0:
                price_position = (base_rate / comp_avg) * 100
                if price_position < 85:
                    price_multiplier *= 1.05
                    reasoning_factors.append(f"Below market (${comp_avg:.0f}): +5%")
                elif price_position > 115:
                    price_multiplier *= 0.97
                    reasoning_factors.append(f"Above market (${comp_avg:.0f}): -3%")
                else:
                    reasoning_factors.append(f"Market aligned (${comp_avg:.0f})")

            suggested_rate = base_rate * price_multiplier

            # DYNAMIC CONFIDENCE SCORING
            confidence_factors = []
            confidence_score = 0.0

            # Historical data availability
            if bookings > 0:
                confidence_score += 0.25
                confidence_factors.append("Has booking history")

            # Booking pace reliability
            if booking_pace > 0.5:
                confidence_score += 0.20
                confidence_factors.append("Active booking pace")

            # Competitor data availability
            if comp_avg > 0 and len(comp_avg_prices.get(current_date, [])) >= 2:
                confidence_score += 0.25
                confidence_factors.append("Multiple competitor prices")
            elif comp_avg > 0:
                confidence_score += 0.15
                confidence_factors.append("Limited competitor data")

            # Time to arrival
            days_to_arrival = (date_obj - datetime.now(UTC)).days
            if days_to_arrival < 30:
                confidence_score += 0.20
                confidence_factors.append("Near-term forecast")
            elif days_to_arrival < 90:
                confidence_score += 0.10
                confidence_factors.append("Medium-term forecast")

            # Room type data quality
            if total_rooms >= 5:
                confidence_score += 0.10
                confidence_factors.append("Adequate room inventory")

            # Cap confidence at 0.95
            confidence_score = min(confidence_score, 0.95)

            # Determine confidence level
            if confidence_score >= 0.75:
                confidence_level = "High"
            elif confidence_score >= 0.50:
                confidence_level = "Medium"
            else:
                confidence_level = "Low"

            # Determine strategy
            if price_multiplier >= 1.15:
                strategy = 'Premium Pricing'
            elif price_multiplier >= 1.05:
                strategy = 'Demand-Based Pricing'
            elif price_multiplier >= 0.95:
                strategy = 'Market Rate'
            elif price_multiplier >= 0.85:
                strategy = 'Competitive Pricing'
            else:
                strategy = 'Promotional Pricing'

            recommendation = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'date': current_date,
                'room_type': rt['name'],
                'current_rate': base_rate,
                'suggested_rate': round(suggested_rate, 2),
                'occupancy': round(occupancy, 1),
                'booking_pace': round(booking_pace, 2),
                'competitor_avg': round(comp_avg, 2) if comp_avg > 0 else None,
                'strategy': strategy,
                'confidence': round(confidence_score, 2),
                'confidence_level': confidence_level,
                'confidence_factors': confidence_factors,
                'reasoning': ' | '.join(reasoning_factors),
                'reasoning_breakdown': reasoning_factors,
                'is_weekend': is_weekend,
                'is_peak_season': is_peak_season,
                'price_change_pct': round((price_multiplier - 1) * 100, 1),
                'generated_at': datetime.now(UTC).isoformat()
            }
            recommendations.append(recommendation)

    # Save recommendations
    if recommendations:
        await db.rms_pricing_recommendations.insert_many([r.copy() for r in recommendations])

    return {
        'message': f'Generated {len(recommendations)} pricing recommendations',
        'recommendations': recommendations,
        'summary': {
            'total_recommendations': len(recommendations),
            'avg_confidence': round(sum(r['confidence'] for r in recommendations) / len(recommendations), 2) if recommendations else 0,
            'high_confidence_count': sum(1 for r in recommendations if r['confidence_level'] == 'High'),
            'date_range': f"{request.start_date} to {request.end_date}"
        }
    }

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
    current_user: User = Depends(get_current_user)
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

@router.get("/rms/pricing-recommendations")
async def get_pricing_recommendations(
    date: str = None,
    status: str = 'pending',
    current_user: User = Depends(get_current_user)
):
    """Get pricing recommendations"""
    query = {'tenant_id': current_user.tenant_id}
    if date:
        query['date'] = date
    if status:
        query['status'] = status

    recommendations = await db.rms_pricing_recommendations.find(
        query,
        {'_id': 0}
    ).sort('date', 1).to_list(1000)

    return {'recommendations': recommendations, 'count': len(recommendations)}

@router.post("/rms/apply-pricing/{recommendation_id}")
async def apply_pricing_recommendation(
    recommendation_id: str,
    current_user: User = Depends(get_current_user)
):
    """Apply pricing recommendation"""
    recommendation = await db.rms_pricing_recommendations.find_one({
        'id': recommendation_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Update rate in rate calendar
    await db.rate_calendar.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'date': recommendation['date'],
            'room_type': recommendation['room_type']
        },
        {
            '$set': {
                'rate': recommendation['suggested_rate'],
                'updated_at': datetime.now(UTC).isoformat(),
                'updated_by': current_user.id
            }
        },
        upsert=True
    )

    # Mark recommendation as applied
    await db.rms_pricing_recommendations.update_one(
        {'id': recommendation_id},
        {
            '$set': {
                'status': 'applied',
                'applied_at': datetime.now(UTC).isoformat(),
                'applied_by': current_user.id
            }
        }
    )

    return {'message': 'Pricing recommendation applied successfully'}


# ENHANCED RMS ENDPOINTS FOR VISUALIZATION
@router.get("/rms/comp-set-comparison")
async def get_comp_set_price_comparison(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get competitor pricing comparison with your hotel rates"""
    # Default to next 30 days if not specified
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()

    # Get all competitors
    competitors = await db.comp_set.find({
        'tenant_id': current_user.tenant_id,
        'status': 'active'
    }, {'_id': 0}).to_list(100)

    # Get competitor pricing
    comp_pricing = await db.comp_pricing.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_date, '$lte': end_date}
    }, {'_id': 0}).to_list(1000)

    # Get your hotel's rates
    room_types = await db.room_types.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(100)

    # Organize data by date
    comparison_data = {}

    # Process each date
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1

    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()

        # Get competitor prices for this date
        date_comp_prices = [p for p in comp_pricing if p.get('date') == current_date]

        comp_data = []
        for comp in competitors:
            comp_price = next((p for p in date_comp_prices if p.get('competitor_id') == comp['id']), None)
            if comp_price:
                comp_data.append({
                    'competitor_name': comp['name'],
                    'rate': comp_price.get('standard_rate', 0),
                    'star_rating': comp.get('star_rating', 0)
                })

        # Get your hotel's average rate
        your_avg_rate = sum(rt.get('base_rate', 0) for rt in room_types) / len(room_types) if room_types else 100

        comp_avg = sum(c['rate'] for c in comp_data) / len(comp_data) if comp_data else 0
        comp_min = min([c['rate'] for c in comp_data]) if comp_data else 0
        comp_max = max([c['rate'] for c in comp_data]) if comp_data else 0

        comparison_data[current_date] = {
            'date': current_date,
            'your_rate': round(your_avg_rate, 2),
            'comp_avg': round(comp_avg, 2),
            'comp_min': round(comp_min, 2),
            'comp_max': round(comp_max, 2),
            'competitors': comp_data,
            'price_index': round((your_avg_rate / comp_avg * 100), 1) if comp_avg > 0 else 100,
            'position': 'Above Market' if your_avg_rate > comp_avg and comp_avg > 0 else ('Below Market' if your_avg_rate < comp_avg and comp_avg > 0 else 'At Market')
        }

    # Convert to list
    comparison_list = list(comparison_data.values())

    # Calculate summary
    avg_price_index = sum(d['price_index'] for d in comparison_list) / len(comparison_list) if comparison_list else 100
    days_above_market = sum(1 for d in comparison_list if d['position'] == 'Above Market')
    days_below_market = sum(1 for d in comparison_list if d['position'] == 'Below Market')

    return {
        'comparison': comparison_list,
        'summary': {
            'total_days': len(comparison_list),
            'competitor_count': len(competitors),
            'avg_price_index': round(avg_price_index, 1),
            'days_above_market': days_above_market,
            'days_at_market': len(comparison_list) - days_above_market - days_below_market,
            'days_below_market': days_below_market,
            'date_range': f"{start_date} to {end_date}"
        }
    }

@router.get("/rms/pricing-insights")
async def get_pricing_insights(
    date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get detailed pricing insights and breakdown for specific date"""
    if not date:
        date = datetime.now(UTC).date().isoformat()

    # Get recommendations for this date
    recommendations = await db.rms_pricing_recommendations.find({
        'tenant_id': current_user.tenant_id,
        'date': date
    }, {'_id': 0}).to_list(100)

    if not recommendations:
        return {
            'date': date,
            'message': 'No pricing recommendations available for this date',
            'insights': []
        }

    # Aggregate insights
    insights = []
    for rec in recommendations:
        insight = {
            'room_type': rec.get('room_type'),
            'current_rate': rec.get('current_rate'),
            'suggested_rate': rec.get('suggested_rate'),
            'price_change': rec.get('suggested_rate', 0) - rec.get('current_rate', 0),
            'price_change_pct': rec.get('price_change_pct', 0),
            'occupancy': rec.get('occupancy'),
            'booking_pace': rec.get('booking_pace'),
            'competitor_avg': rec.get('competitor_avg'),
            'confidence': rec.get('confidence'),
            'confidence_level': rec.get('confidence_level'),
            'strategy': rec.get('strategy'),
            'reasoning': rec.get('reasoning'),
            'reasoning_breakdown': rec.get('reasoning_breakdown', []),
            'confidence_factors': rec.get('confidence_factors', [])
        }
        insights.append(insight)

    # Calculate aggregate metrics
    avg_confidence = sum(i['confidence'] for i in insights) / len(insights) if insights else 0
    total_price_change = sum(i['price_change'] for i in insights)

    return {
        'date': date,
        'insights': insights,
        'summary': {
            'total_recommendations': len(insights),
            'avg_confidence': round(avg_confidence, 2),
            'total_rate_adjustment': round(total_price_change, 2),
            'high_confidence_count': sum(1 for i in insights if i['confidence_level'] == 'High'),
            'recommended_increase': sum(1 for i in insights if i['price_change'] > 0),
            'recommended_decrease': sum(1 for i in insights if i['price_change'] < 0)
        }
    }


# ============================================================================

# --------------------------------------------------------------------------
# Sales & Marketing - Group Sales, Corporate Contracts, OTA Promotions
# --------------------------------------------------------------------------

@router.get("/sales/group-bookings")
@cached(ttl=300, key_prefix="sales_group_bookings")  # Cache for 5 min
async def get_group_bookings(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get group bookings (weddings, meetings, conferences)"""
    current_user = await get_current_user(credentials)

    query = {
        'tenant_id': current_user.tenant_id,
        'booking_type': 'group'
    }

    if status:
        query['status'] = status

    group_bookings = []
    async for booking in db.group_bookings.find(query).sort('event_date', 1):
        group_bookings.append({
            'id': booking.get('id'),
            'group_name': booking.get('group_name'),
            'group_type': booking.get('group_type'),  # wedding, meeting, conference
            'event_date': booking.get('event_date').date().isoformat() if booking.get('event_date') else None,
            'start_date': booking.get('start_date').date().isoformat() if booking.get('start_date') else None,
            'end_date': booking.get('end_date').date().isoformat() if booking.get('end_date') else None,
            'total_rooms': booking.get('total_rooms', 0),
            'total_guests': booking.get('total_guests', 0),
            'total_revenue': booking.get('total_revenue', 0),
            'status': booking.get('status'),
            'contact_person': booking.get('contact_person'),
            'contact_email': booking.get('contact_email'),
        })

    return group_bookings

class GroupBookingCreate(BaseModel):
    group_name: str
    group_type: str  # wedding, meeting, conference
    event_date: str
    start_date: str
    end_date: str
    total_rooms: int
    total_guests: int
    contact_person: str
    contact_email: str
    contact_phone: str
    special_requirements: str | None = None
    notes: str | None = None

@router.post("/sales/group-booking")
async def create_group_booking(
    booking: GroupBookingCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new group booking"""
    current_user = await get_current_user(credentials)

    booking_id = str(uuid.uuid4())
    group_booking = {
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'booking_type': 'group',
        'group_name': booking.group_name,
        'group_type': booking.group_type,
        'event_date': datetime.fromisoformat(booking.event_date),
        'start_date': datetime.fromisoformat(booking.start_date),
        'end_date': datetime.fromisoformat(booking.end_date),
        'total_rooms': booking.total_rooms,
        'total_guests': booking.total_guests,
        'contact_person': booking.contact_person,
        'contact_email': booking.contact_email,
        'contact_phone': booking.contact_phone,
        'special_requirements': booking.special_requirements,
        'notes': booking.notes,
        'status': 'inquiry',
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.group_bookings.insert_one(group_booking)

    return {
        'message': 'Group booking created',
        'booking_id': booking_id,
        'group_name': booking.group_name
    }


@router.get("/sales/corporate-contracts")
async def get_corporate_contracts(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get corporate contracts"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    contracts = []
    async for contract in db.corporate_contracts.find(query).sort('start_date', -1):
        contracts.append({
            'id': contract.get('id'),
            'company_name': contract.get('company_name'),
            'contract_type': contract.get('contract_type'),  # direct, negotiated, corporate_rate
            'rate_code': contract.get('rate_code'),
            'negotiated_rate': contract.get('negotiated_rate'),
            'discount_percentage': contract.get('discount_percentage', 0),
            'start_date': contract.get('start_date').date().isoformat() if contract.get('start_date') else None,
            'end_date': contract.get('end_date').date().isoformat() if contract.get('end_date') else None,
            'allotment': contract.get('allotment', 0),
            'blackout_dates': contract.get('blackout_dates', []),
            'status': contract.get('status'),
            'total_bookings': contract.get('total_bookings', 0),
            'total_room_nights': contract.get('total_room_nights', 0),
            'total_revenue': contract.get('total_revenue', 0),
            'contact_person': contract.get('contact_person'),
            'notes': contract.get('notes', '')
        })

    return {
        'contracts': contracts,
        'count': len(contracts),
        'active_contracts': len([c for c in contracts if c['status'] == 'active'])
    }


class CorporateContractCreate(BaseModel):
    company_name: str
    contract_type: str
    rate_code: str
    negotiated_rate: float | None = None
    discount_percentage: float | None = 0
    start_date: str
    end_date: str
    allotment: int | None = 0
    blackout_dates: list[str] | None = []
    contact_person: str
    contact_email: str
    contact_phone: str
    notes: str | None = None

@router.post("/sales/corporate-contract")
async def create_corporate_contract(
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new corporate contract"""
    current_user = await get_current_user(credentials)

    contract_id = str(uuid.uuid4())
    corporate_contract = {
        'id': contract_id,
        'tenant_id': current_user.tenant_id,
        'company_name': contract.company_name,
        'contract_type': contract.contract_type,
        'rate_code': contract.rate_code,
        'negotiated_rate': contract.negotiated_rate,
        'discount_percentage': contract.discount_percentage,
        'start_date': datetime.fromisoformat(contract.start_date),
        'end_date': datetime.fromisoformat(contract.end_date),
        'allotment': contract.allotment,
        'blackout_dates': contract.blackout_dates,
        'contact_person': contract.contact_person,
        'contact_email': contract.contact_email,
        'contact_phone': contract.contact_phone,
        'notes': contract.notes,
        'status': 'active',
        'total_bookings': 0,
        'total_room_nights': 0,
        'total_revenue': 0,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.corporate_contracts.insert_one(corporate_contract)

    return {
        'message': 'Corporate contract created',
        'contract_id': contract_id,
        'company_name': contract.company_name
    }


@router.put("/sales/corporate-contract/{contract_id}")
async def update_corporate_contract(
    contract_id: str,
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update a corporate contract"""
    current_user = await get_current_user(credentials)

    existing = await db.corporate_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    await db.corporate_contracts.update_one(
        {'id': contract_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'company_name': contract.company_name,
                'contract_type': contract.contract_type,
                'rate_code': contract.rate_code,
                'negotiated_rate': contract.negotiated_rate,
                'discount_percentage': contract.discount_percentage,
                'start_date': datetime.fromisoformat(contract.start_date),
                'end_date': datetime.fromisoformat(contract.end_date),
                'allotment': contract.allotment,
                'blackout_dates': contract.blackout_dates,
                'contact_person': contract.contact_person,
                'contact_email': contract.contact_email,
                'contact_phone': contract.contact_phone,
                'notes': contract.notes,
                'updated_at': datetime.now(UTC),
                'updated_by': current_user.username
            }
        }
    )

    return {
        'message': 'Contract updated',
        'contract_id': contract_id
    }


@router.get("/sales/ota-promotions")
async def get_ota_promotions(
    active_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get OTA promotions"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if active_only:
        today = datetime.now(UTC)
        query['start_date'] = {'$lte': today}
        query['end_date'] = {'$gte': today}
        query['is_active'] = True

    promotions = []
    async for promo in db.ota_promotions.find(query).sort('start_date', -1):
        promotions.append({
            'id': promo.get('id'),
            'promotion_name': promo.get('promotion_name'),
            'ota_channel': promo.get('ota_channel'),  # booking.com, expedia, airbnb
            'promotion_type': promo.get('promotion_type'),  # discount, free_night, upgrade
            'discount_percentage': promo.get('discount_percentage', 0),
            'discount_amount': promo.get('discount_amount', 0),
            'start_date': promo.get('start_date').date().isoformat() if promo.get('start_date') else None,
            'end_date': promo.get('end_date').date().isoformat() if promo.get('end_date') else None,
            'min_stay_nights': promo.get('min_stay_nights', 1),
            'max_bookings': promo.get('max_bookings', 0),
            'current_bookings': promo.get('current_bookings', 0),
            'is_active': promo.get('is_active', True),
            'terms': promo.get('terms', ''),
            'created_at': promo.get('created_at').isoformat() if promo.get('created_at') else None
        })

    return {
        'promotions': promotions,
        'count': len(promotions),
        'active_count': len([p for p in promotions if p['is_active']])
    }


class OTAPromotionCreate(BaseModel):
    promotion_name: str
    ota_channel: str
    promotion_type: str
    discount_percentage: float | None = 0
    discount_amount: float | None = 0
    start_date: str
    end_date: str
    min_stay_nights: int | None = 1
    max_bookings: int | None = 0
    terms: str | None = None

@router.post("/sales/ota-promotion")
async def create_ota_promotion(
    promotion: OTAPromotionCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new OTA promotion"""
    current_user = await get_current_user(credentials)

    promo_id = str(uuid.uuid4())
    ota_promotion = {
        'id': promo_id,
        'tenant_id': current_user.tenant_id,
        'promotion_name': promotion.promotion_name,
        'ota_channel': promotion.ota_channel,
        'promotion_type': promotion.promotion_type,
        'discount_percentage': promotion.discount_percentage,
        'discount_amount': promotion.discount_amount,
        'start_date': datetime.fromisoformat(promotion.start_date),
        'end_date': datetime.fromisoformat(promotion.end_date),
        'min_stay_nights': promotion.min_stay_nights,
        'max_bookings': promotion.max_bookings,
        'current_bookings': 0,
        'is_active': True,
        'terms': promotion.terms,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.ota_promotions.insert_one(ota_promotion)

    return {
        'message': 'OTA promotion created',
        'promotion_id': promo_id,
        'promotion_name': promotion.promotion_name
    }


# --------------------------------------------------------------------------
# Revenue Management - Pickup Report, CompSet, Market Share
# --------------------------------------------------------------------------

@router.get("/revenue/pickup-report")
async def get_pickup_report(
    start_date: str | None = None,
    end_date: str | None = None,
    format: str = 'json',
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pickup report with export capability (JSON, CSV ready)"""
    current_user = await get_current_user(credentials)

    if not start_date:
        start_date = datetime.now(UTC).replace(day=1)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        end_date = start_date + timedelta(days=30)
    else:
        end_date = datetime.fromisoformat(end_date)

    # Get booking pace by arrival date
    pickup_report = []

    # Iterate through each day in range
    current_date = start_date
    while current_date <= end_date:
        # Get bookings for this arrival date
        day_bookings = []

        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': {
                '$gte': current_date,
                '$lt': current_date + timedelta(days=1)
            },
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }):
            days_before = (current_date - booking.get('created_at')).days if booking.get('created_at') else 0
            day_bookings.append({
                'booking_id': booking.get('id'),
                'created_at': booking.get('created_at').date().isoformat() if booking.get('created_at') else None,
                'days_before_arrival': days_before,
                'room_nights': booking.get('nights', 1),
                'revenue': booking.get('total_amount', 0)
            })

        # Aggregate data
        total_rooms = len(day_bookings)
        total_revenue = sum(b['revenue'] for b in day_bookings)

        # Group by booking window
        booking_windows = {
            '0-7_days': 0,
            '8-14_days': 0,
            '15-30_days': 0,
            '31-60_days': 0,
            '61+_days': 0
        }

        for booking in day_bookings:
            days = booking['days_before_arrival']
            if days <= 7:
                booking_windows['0-7_days'] += 1
            elif days <= 14:
                booking_windows['8-14_days'] += 1
            elif days <= 30:
                booking_windows['15-30_days'] += 1
            elif days <= 60:
                booking_windows['31-60_days'] += 1
            else:
                booking_windows['61+_days'] += 1

        pickup_report.append({
            'arrival_date': current_date.date().isoformat(),
            'total_rooms': total_rooms,
            'total_revenue': total_revenue,
            'booking_windows': booking_windows
        })

        current_date += timedelta(days=1)

    # If CSV format requested, prepare for export
    if format == 'csv':
        # Return data in CSV-friendly format
        csv_data = []
        for row in pickup_report:
            csv_data.append({
                'Arrival Date': row['arrival_date'],
                'Total Rooms': row['total_rooms'],
                'Total Revenue': row['total_revenue'],
                '0-7 Days': row['booking_windows']['0-7_days'],
                '8-14 Days': row['booking_windows']['8-14_days'],
                '15-30 Days': row['booking_windows']['15-30_days'],
                '31-60 Days': row['booking_windows']['31-60_days'],
                '61+ Days': row['booking_windows']['61+_days']
            })

        return {
            'format': 'csv',
            'data': csv_data,
            'filename': f"pickup_report_{start_date.date()}_{end_date.date()}.csv"
        }

    return {
        'format': 'json',
        'date_range': {
            'start': start_date.date().isoformat(),
            'end': end_date.date().isoformat()
        },
        'pickup_report': pickup_report,
        'summary': {
            'total_rooms': sum(r['total_rooms'] for r in pickup_report),
            'total_revenue': sum(r['total_revenue'] for r in pickup_report)
        }
    }


@router.get("/revenue/compset-analysis")
async def get_compset_analysis(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get competitive set analysis"""
    current_user = await get_current_user(credentials)

    # Get competitor data (would be manually entered or API integrated)
    competitors = []

    async for comp in db.competitors.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }):
        # Get their rates (if available)
        latest_rate = await db.competitor_rates.find_one(
            {
                'competitor_id': comp.get('id'),
                'tenant_id': current_user.tenant_id
            },
            sort=[('date', -1)]
        )

        competitors.append({
            'competitor_id': comp.get('id'),
            'competitor_name': comp.get('name'),
            'star_rating': comp.get('star_rating'),
            'location': comp.get('location'),
            'distance_km': comp.get('distance_km'),
            'current_adr': latest_rate.get('adr') if latest_rate else 0,
            'current_occupancy': latest_rate.get('occupancy_pct') if latest_rate else 0,
            'last_updated': latest_rate.get('date').isoformat() if latest_rate and latest_rate.get('date') else None
        })

    # Get own property data
    today = datetime.now(UTC)
    own_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    })

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    own_occupancy = (own_bookings / total_rooms * 100) if total_rooms > 0 else 0

    # Calculate own ADR
    own_adr = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today - timedelta(days=30)},
        'status': {'$in': ['checked_in', 'checked_out']}
    }):
        own_adr += booking.get('room_rate', 0)

    booking_count = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today - timedelta(days=30)},
        'status': {'$in': ['checked_in', 'checked_out']}
    })

    own_adr = own_adr / booking_count if booking_count > 0 else 0

    return {
        'own_property': {
            'adr': own_adr,
            'occupancy': own_occupancy,
            'revpar': own_adr * (own_occupancy / 100)
        },
        'competitors': competitors,
        'compset_count': len(competitors),
        'analysis_date': today.date().isoformat()
    }


@router.get("/revenue/market-share")
async def get_market_share(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get market share analysis"""
    current_user = await get_current_user(credentials)

    # Calculate market share based on bookings and revenue
    today = datetime.now(UTC)
    last_30_days = today - timedelta(days=30)

    # Own performance
    own_rooms = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': last_30_days},
        'status': {'$in': ['checked_in', 'checked_out']}
    })

    own_revenue = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': last_30_days},
        'status': {'$in': ['checked_in', 'checked_out']}
    }):
        own_revenue += booking.get('total_amount', 0)

    # Market data (would need competitor API or manual entry)
    # For now, estimating based on competitor count and average
    total_market_rooms = own_rooms  # Base
    total_market_revenue = own_revenue  # Base

    competitor_count = await db.competitors.count_documents({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    })

    # Estimate market (assuming similar performance)
    if competitor_count > 0:
        total_market_rooms += (own_rooms * competitor_count)
        total_market_revenue += (own_revenue * competitor_count)

    room_share = (own_rooms / total_market_rooms * 100) if total_market_rooms > 0 else 0
    revenue_share = (own_revenue / total_market_revenue * 100) if total_market_revenue > 0 else 0

    # Calculate fair share (1 / number of properties in compset)
    fair_share = 100 / (competitor_count + 1) if competitor_count >= 0 else 100

    return {
        'period': '30_days',
        'own_performance': {
            'room_nights': own_rooms,
            'revenue': own_revenue
        },
        'market_totals': {
            'room_nights': total_market_rooms,
            'revenue': total_market_revenue
        },
        'market_share': {
            'room_share_pct': room_share,
            'revenue_share_pct': revenue_share,
            'fair_share_pct': fair_share
        },
        'performance_index': {
            'room_mpi': (room_share / fair_share * 100) if fair_share > 0 else 100,
            'revenue_rgi': (revenue_share / fair_share * 100) if fair_share > 0 else 100
        }
    }


# --------------------------------------------------------------------------
# IT & Security - User Activity Logs, API Rate Limits
# --------------------------------------------------------------------------

@router.get("/security/user-activity-logs")
async def get_user_activity_logs(
    user_id: str | None = None,
    action_type: str | None = None,
    limit: int = 100,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get user activity logs for security monitoring"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if user_id:
        query['user_id'] = user_id
    if action_type:
        query['action'] = action_type

    logs = []
    async for log in db.audit_logs.find(query).sort('timestamp', -1).limit(limit):
        logs.append({
            'log_id': log.get('id'),
            'user_id': log.get('user_id'),
            'user_name': log.get('user_name'),
            'action': log.get('action'),
            'entity_type': log.get('entity_type'),
            'entity_id': log.get('entity_id'),
            'ip_address': log.get('ip_address'),
            'user_agent': log.get('user_agent'),
            'timestamp': log.get('timestamp').isoformat() if log.get('timestamp') else None,
            'changes': log.get('changes', {})
        })

    # Get activity summary
    activity_summary = {}
    for log in logs:
        action = log['action']
        activity_summary[action] = activity_summary.get(action, 0) + 1

    return {
        'logs': logs,
        'total_count': len(logs),
        'activity_summary': activity_summary
    }


@router.get("/security/api-rate-limits")
async def get_api_rate_limits(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get API rate limit monitoring data"""
    current_user = await get_current_user(credentials)

    # Track API calls per endpoint
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)

    # Get API access logs
    endpoint_stats = {}

    async for log in db.api_access_logs.find({
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': today}
    }):
        endpoint = log.get('endpoint', 'unknown')

        if endpoint not in endpoint_stats:
            endpoint_stats[endpoint] = {
                'endpoint': endpoint,
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'avg_response_time_ms': [],
                'rate_limit_hits': 0
            }

        endpoint_stats[endpoint]['total_requests'] += 1

        if log.get('status_code', 200) < 400:
            endpoint_stats[endpoint]['successful_requests'] += 1
        else:
            endpoint_stats[endpoint]['failed_requests'] += 1

        if log.get('status_code') == 429:  # Too Many Requests
            endpoint_stats[endpoint]['rate_limit_hits'] += 1

        if log.get('response_time_ms'):
            endpoint_stats[endpoint]['avg_response_time_ms'].append(log.get('response_time_ms'))

    # Calculate averages
    for endpoint in endpoint_stats.values():
        if endpoint['avg_response_time_ms']:
            endpoint['avg_response_time_ms'] = sum(endpoint['avg_response_time_ms']) / len(endpoint['avg_response_time_ms'])
        else:
            endpoint['avg_response_time_ms'] = 0

    return {
        'date': today.date().isoformat(),
        'endpoint_stats': list(endpoint_stats.values()),
        'total_api_calls': sum(s['total_requests'] for s in endpoint_stats.values()),
        'total_rate_limit_hits': sum(s['rate_limit_hits'] for s in endpoint_stats.values())
    }


# --------------------------------------------------------------------------
# Housekeeping - Inventory & Stock Management
# --------------------------------------------------------------------------

@router.get("/housekeeping/inventory")
async def get_inventory(
    category: str | None = None,
    low_stock_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get housekeeping inventory"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if category:
        query['category'] = category

    if low_stock_only:
        query['$expr'] = {'$lte': ['$current_stock', '$minimum_stock']}

    inventory_items = []
    async for item in db.housekeeping_inventory.find(query).sort('name', 1):
        inventory_items.append({
            'id': item.get('id'),
            'name': item.get('name'),
            'category': item.get('category'),  # linen, amenities, cleaning_supplies
            'unit': item.get('unit'),  # pieces, bottles, kg
            'current_stock': item.get('current_stock', 0),
            'minimum_stock': item.get('minimum_stock', 0),
            'maximum_stock': item.get('maximum_stock', 0),
            'unit_cost': item.get('unit_cost', 0),
            'supplier': item.get('supplier', ''),
            'last_restock_date': item.get('last_restock_date').isoformat() if item.get('last_restock_date') else None,
            'is_low_stock': item.get('current_stock', 0) <= item.get('minimum_stock', 0)
        })

    return {
        'inventory_items': inventory_items,
        'total_items': len(inventory_items),
        'low_stock_items': len([i for i in inventory_items if i['is_low_stock']]),
        'categories': list({i['category'] for i in inventory_items})
    }


class InventoryItemCreate(BaseModel):
    name: str
    category: str
    unit: str
    current_stock: int
    minimum_stock: int
    maximum_stock: int
    unit_cost: float
    supplier: str | None = None

@router.post("/housekeeping/inventory/item")
async def create_inventory_item(
    item: InventoryItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new inventory item"""
    current_user = await get_current_user(credentials)

    item_id = str(uuid.uuid4())
    inventory_item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'name': item.name,
        'category': item.category,
        'unit': item.unit,
        'current_stock': item.current_stock,
        'minimum_stock': item.minimum_stock,
        'maximum_stock': item.maximum_stock,
        'unit_cost': item.unit_cost,
        'supplier': item.supplier,
        'last_restock_date': datetime.now(UTC),
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.housekeeping_inventory.insert_one(inventory_item)

    return {
        'message': 'Inventory item created',
        'item_id': item_id,
        'name': item.name
    }


class InventoryUsage(BaseModel):
    quantity: int
    used_by: str
    notes: str | None = None

@router.put("/housekeeping/inventory/item/{item_id}/usage")
async def record_inventory_usage(
    item_id: str,
    usage: InventoryUsage,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Record inventory usage"""
    current_user = await get_current_user(credentials)

    item = await db.housekeeping_inventory.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    new_stock = item.get('current_stock', 0) - usage.quantity

    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    # Update stock
    await db.housekeeping_inventory.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'current_stock': new_stock}}
    )

    # Log usage
    await db.inventory_usage_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'item_id': item_id,
        'item_name': item.get('name'),
        'quantity': usage.quantity,
        'used_by': usage.used_by,
        'notes': usage.notes,
        'timestamp': datetime.now(UTC)
    })

    return {
        'message': 'Usage recorded',
        'item_id': item_id,
        'new_stock': new_stock,
        'is_low_stock': new_stock <= item.get('minimum_stock', 0)
    }

@router.get("/notifications/mobile/finance")
async def get_finance_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []
    today = datetime.now(UTC)

    # Overdue receivables
    overdue_count = 0
    overdue_amount = 0.0

    async for folio in db.folios.find({
        'tenant_id': current_user.tenant_id,
        'status': 'open',
        'balance': {'$gt': 0}
    }):
        booking = await db.bookings.find_one({
            'id': folio.get('booking_id'),
            'tenant_id': current_user.tenant_id
        })

        if booking:
            checkout = booking.get('check_out')
            if checkout:
                # Convert string date to datetime for comparison
                try:
                    if isinstance(checkout, str):
                        checkout_date = datetime.fromisoformat(checkout).replace(tzinfo=UTC)
                    else:
                        checkout_date = checkout if checkout.tzinfo else checkout.replace(tzinfo=UTC)

                    if checkout_date < today - timedelta(days=7):
                        overdue_count += 1
                        overdue_amount += folio.get('balance', 0)
                except (ValueError, AttributeError):
                    pass  # Skip invalid dates

    if overdue_count > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'overdue_receivables',
            'title': 'Vadesi Geçen Alacaklar',
            'message': f"{overdue_count} adet gecikmiş alacak - Toplam: ₺{overdue_amount:.2f}",
            'priority': 'high',
            'created_at': today.isoformat()
        })

    # Large payment approvals needed (> 10000 TL)
    async for payment in db.payment_approvals.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending',
        'amount': {'$gt': 10000}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'large_payment_approval',
            'title': 'Büyük Ödeme Onayı',
            'message': f"₺{payment.get('amount', 0):.2f} tutarında ödeme onay bekliyor",
            'priority': 'medium',
            'created_at': payment.get('created_at').isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Finance Mobile - New Enhancements (Cash Flow, Risk Management, Expenses)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Security/IT Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------

@router.get("/security/mobile/system-status")
async def get_system_status_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get system status for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Check various system components
    system_status = {
        'database': 'operational',
        'pms': 'operational',
        'pos': 'operational',
        'channel_manager': 'operational',
        'payment_gateway': 'operational'
    }

    # Check for recent errors in logs
    recent_errors = []
    last_hour = datetime.now(UTC) - timedelta(hours=1)

    async for log in db.system_logs.find({
        'tenant_id': current_user.tenant_id,
        'log_level': 'error',
        'created_at': {'$gte': last_hour}
    }).limit(10):
        recent_errors.append({
            'component': log.get('component', 'unknown'),
            'message': log.get('message', ''),
            'timestamp': log.get('created_at').isoformat()
        })

        # Update system status if errors found
        component = log.get('component', 'unknown')
        if component in system_status:
            system_status[component] = 'degraded'

    # Overall health score
    operational_count = sum(1 for status in system_status.values() if status == 'operational')
    health_score = (operational_count / len(system_status)) * 100

    return {
        'overall_status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'critical',
        'health_score': health_score,
        'components': system_status,
        'recent_errors': recent_errors,
        'last_check': datetime.now(UTC).isoformat()
    }


@router.get("/security/mobile/connection-status")
async def get_connection_status_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get POS and Channel Manager connection status"""
    current_user = await get_current_user(credentials)

    connections = {}

    # Check POS connection (last successful transaction)
    last_pos_transaction = await db.pos_transactions.find_one(
        {'tenant_id': current_user.tenant_id},
        sort=[('created_at', -1)]
    )

    if last_pos_transaction:
        last_activity = last_pos_transaction.get('created_at')
        minutes_ago = (datetime.now(UTC) - last_activity).total_seconds() / 60

        connections['pos'] = {
            'status': 'connected' if minutes_ago < 60 else 'idle' if minutes_ago < 240 else 'disconnected',
            'last_activity': last_activity.isoformat(),
            'minutes_since_activity': int(minutes_ago)
        }
    else:
        connections['pos'] = {
            'status': 'no_data',
            'last_activity': None,
            'minutes_since_activity': None
        }

    # Check Channel Manager sync (last successful sync)
    last_cm_sync = await db.channel_manager_syncs.find_one(
        {'tenant_id': current_user.tenant_id},
        sort=[('sync_timestamp', -1)]
    )

    if last_cm_sync:
        last_sync = last_cm_sync.get('sync_timestamp')
        minutes_ago = (datetime.now(UTC) - last_sync).total_seconds() / 60

        connections['channel_manager'] = {
            'status': 'connected' if minutes_ago < 15 else 'idle' if minutes_ago < 60 else 'disconnected',
            'last_sync': last_sync.isoformat(),
            'minutes_since_sync': int(minutes_ago),
            'sync_status': last_cm_sync.get('status', 'unknown')
        }
    else:
        connections['channel_manager'] = {
            'status': 'no_data',
            'last_sync': None,
            'minutes_since_sync': None
        }

    return {
        'connections': connections,
        'timestamp': datetime.now(UTC).isoformat()
    }


@router.get("/security/mobile/security-alerts")
async def get_security_alerts_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get security alerts for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    alerts = []

    # Check for unauthorized access attempts
    failed_logins = await db.auth_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'action': 'login_failed',
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if failed_logins > 5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'unauthorized_access',
            'title': 'Yetkisiz Erişim Denemesi',
            'message': f"Son 1 saatte {failed_logins} başarısız giriş denemesi",
            'severity': 'high',
            'timestamp': datetime.now(UTC).isoformat()
        })

    # Check for unusual data access patterns
    async for log in db.audit_logs.find({
        'tenant_id': current_user.tenant_id,
        'action': {'$in': ['DATA_EXPORT', 'BULK_DELETE']},
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=24)}
    }):
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'data_access',
            'title': 'Olağandışı Veri Erişimi',
            'message': f"{log.get('user_name')} tarafından {log.get('action')}",
            'severity': 'medium',
            'timestamp': log.get('timestamp').isoformat()
        })

    # GDPR compliance alerts (guest data older than retention period)
    retention_period = 365 * 2  # 2 years
    old_data_cutoff = datetime.now(UTC) - timedelta(days=retention_period)

    old_guest_count = await db.guests.count_documents({
        'tenant_id': current_user.tenant_id,
        'last_stay_date': {'$lt': old_data_cutoff}
    })

    if old_guest_count > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'gdpr_compliance',
            'title': 'GDPR Uyarısı',
            'message': f"{old_guest_count} misafirin verileri saklama süresini aştı",
            'severity': 'low',
            'timestamp': datetime.now(UTC).isoformat()
        })

    return {
        'alerts': alerts,
        'alert_count': len(alerts)
    }


@router.get("/notifications/mobile/security")
async def get_security_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []

    # System errors in last hour
    error_count = await db.system_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'log_level': 'error',
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if error_count > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'system_error',
            'title': 'Sistem Hataları',
            'message': f"Son 1 saatte {error_count} sistem hatası kaydedildi",
            'priority': 'high',
            'created_at': datetime.now(UTC).isoformat()
        })

    # Connection failures
    async for error in db.system_logs.find({
        'tenant_id': current_user.tenant_id,
        'log_type': {'$in': ['pos_error', 'cm_sync_error']},
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    }).limit(5):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'connection_failure',
            'title': 'Bağlantı Hatası',
            'message': error.get('message', 'Bağlantı sorunu tespit edildi'),
            'priority': 'medium',
            'created_at': error.get('created_at').isoformat()
        })

    # Security alerts
    failed_logins = await db.auth_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'action': 'login_failed',
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if failed_logins > 5:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'security_alert',
            'title': 'Güvenlik Uyarısı',
            'message': f"Çok sayıda başarısız giriş denemesi ({failed_logins})",
            'priority': 'urgent',
            'created_at': datetime.now(UTC).isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }




# ============================================================================
# NEW RMS: Internal-Data-Driven Dashboard, Yield Rules, Seasonal Calendar
# ============================================================================

@router.get("/rms/dashboard-kpis")
async def get_rms_dashboard_kpis(
    period: str = "30",
    current_user: User = Depends(get_current_user)
):
    """Comprehensive RMS dashboard KPIs based on internal hotel data only."""
    days = int(period)
    now = datetime.now(UTC)
    period_start = (now - timedelta(days=days)).isoformat()
    prev_period_start = (now - timedelta(days=days * 2)).isoformat()
    prev_period_end = period_start
    tid = current_user.tenant_id

    total_rooms = await db.rooms.count_documents({"tenant_id": tid})
    if total_rooms == 0:
        total_rooms = 30

    # Current period bookings
    current_bookings = await db.bookings.find(
        {"tenant_id": tid, "check_in": {"$gte": period_start},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "total_amount": 1, "nights": 1, "base_rate": 1, "channel": 1,
         "source_channel": 1, "status": 1, "check_in": 1, "room_type": 1}
    ).to_list(10000)

    # Previous period bookings (for YoY-like comparison)
    prev_bookings = await db.bookings.find(
        {"tenant_id": tid, "check_in": {"$gte": prev_period_start, "$lt": prev_period_end},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "total_amount": 1, "nights": 1}
    ).to_list(10000)

    # Cancelled bookings
    cancelled = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": period_start}, "status": "cancelled"}
    )
    total_with_cancelled = len(current_bookings) + cancelled

    # Calculate KPIs
    total_revenue = sum(b.get("total_amount", 0) for b in current_bookings)
    total_nights = sum(b.get("nights", 1) for b in current_bookings)
    sold_room_nights = total_nights
    total_room_nights = total_rooms * days

    adr = round(total_revenue / sold_room_nights, 0) if sold_room_nights > 0 else 0
    occupancy = round(sold_room_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0
    revpar = round(total_revenue / total_room_nights, 0) if total_room_nights > 0 else 0
    cancel_rate = round(cancelled / total_with_cancelled * 100, 1) if total_with_cancelled > 0 else 0

    # Previous period KPIs
    prev_revenue = sum(b.get("total_amount", 0) for b in prev_bookings)
    prev_nights = sum(b.get("nights", 1) for b in prev_bookings)
    prev_adr = round(prev_revenue / prev_nights, 0) if prev_nights > 0 else 0
    prev_revpar = round(prev_revenue / (total_rooms * days), 0) if total_rooms > 0 else 0
    prev_occ = round(prev_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0

    # Pickup: new bookings in last 7 days
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    pickup_count = await db.bookings.count_documents(
        {"tenant_id": tid, "created_at": {"$gte": seven_days_ago},
         "status": {"$in": ["confirmed", "guaranteed"]}}
    )
    pickup_rate = round(pickup_count / 7, 1)

    # Channel breakdown
    channel_map = {}
    for b in current_bookings:
        ch = b.get("channel") or b.get("source_channel") or "direct"
        if ch not in channel_map:
            channel_map[ch] = {"count": 0, "revenue": 0, "nights": 0}
        channel_map[ch]["count"] += 1
        channel_map[ch]["revenue"] += b.get("total_amount", 0)
        channel_map[ch]["nights"] += b.get("nights", 1)

    channel_labels = {"direct": "Direkt", "booking_com": "Booking.com",
                      "expedia": "Expedia", "airbnb": "Airbnb", "own_website": "Web Sitesi"}
    channels = []
    for ch, data in channel_map.items():
        channels.append({
            "channel": ch,
            "label": channel_labels.get(ch, ch),
            "bookings": data["count"],
            "revenue": round(data["revenue"], 0),
            "nights": data["nights"],
            "share_pct": round(data["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0,
        })
    channels.sort(key=lambda x: x["revenue"], reverse=True)

    # Room type breakdown
    rt_map = {}
    for b in current_bookings:
        rt = b.get("room_type", "Standard")
        if rt not in rt_map:
            rt_map[rt] = {"count": 0, "revenue": 0}
        rt_map[rt]["count"] += 1
        rt_map[rt]["revenue"] += b.get("total_amount", 0)

    room_type_perf = [{"room_type": rt, **data} for rt, data in rt_map.items()]

    # Daily occupancy trend (last N days)
    daily_trend = []
    for d in range(min(days, 30)):
        day_date = (now - timedelta(days=d)).date().isoformat()
        day_bookings = await db.bookings.count_documents({
            "tenant_id": tid,
            "check_in": {"$lte": day_date},
            "check_out": {"$gt": day_date},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
        })
        day_occ = round(day_bookings / total_rooms * 100, 1) if total_rooms > 0 else 0
        daily_trend.append({"date": day_date, "occupancy": day_occ, "rooms_sold": day_bookings})
    daily_trend.reverse()

    return {
        "kpis": {
            "occupancy": occupancy,
            "occupancy_prev": prev_occ,
            "adr": adr,
            "adr_prev": prev_adr,
            "revpar": revpar,
            "revpar_prev": prev_revpar,
            "total_revenue": round(total_revenue, 0),
            "total_bookings": len(current_bookings),
            "cancel_rate": cancel_rate,
            "pickup_rate": pickup_rate,
            "pickup_count_7d": pickup_count,
            "sold_room_nights": sold_room_nights,
            "total_room_nights": total_room_nights,
        },
        "channels": channels,
        "room_type_performance": room_type_perf,
        "daily_trend": daily_trend,
        "period_days": days,
    }


@router.get("/rms/channel-performance")
async def get_channel_performance(
    months: int = 6,
    current_user: User = Depends(get_current_user)
):
    """Monthly channel performance breakdown."""
    tid = current_user.tenant_id
    now = datetime.now(UTC)
    result = []

    for m in range(months):
        month_start = (now - timedelta(days=30 * (m + 1)))
        month_end = (now - timedelta(days=30 * m))
        month_label = month_start.strftime("%Y-%m")

        bookings = await db.bookings.find(
            {"tenant_id": tid,
             "check_in": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()},
             "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
            {"_id": 0, "channel": 1, "source_channel": 1, "total_amount": 1}
        ).to_list(5000)

        ch_data = {}
        for b in bookings:
            ch = b.get("channel") or b.get("source_channel") or "direct"
            if ch not in ch_data:
                ch_data[ch] = {"count": 0, "revenue": 0}
            ch_data[ch]["count"] += 1
            ch_data[ch]["revenue"] += b.get("total_amount", 0)

        result.append({"month": month_label, "channels": ch_data, "total_bookings": len(bookings)})

    result.reverse()
    return {"monthly_performance": result}


# ── YIELD RULES CRUD ──

class YieldRuleCreate(BaseModel):
    name: str
    description: str = ""
    condition_type: str
    condition_value: float | str
    action_type: str
    action_value: float
    is_active: bool = True
    priority: int = 10
    room_types: list[str] = []


@router.get("/rms/yield-rules")
async def get_yield_rules(current_user: User = Depends(get_current_user)):
    rules = await db.yield_rules.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("priority", 1).to_list(100)
    return {"rules": rules, "count": len(rules)}


@router.post("/rms/yield-rules")
async def create_yield_rule(
    rule: YieldRuleCreate,
    current_user: User = Depends(get_current_user)
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **rule.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }
    await db.yield_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/rms/yield-rules/{rule_id}")
async def update_yield_rule(
    rule_id: str,
    rule: YieldRuleCreate,
    current_user: User = Depends(get_current_user)
):
    result = await db.yield_rules.update_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id},
        {"$set": {**rule.model_dump(), "updated_at": datetime.now(UTC).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Kural guncellendi", "id": rule_id}


@router.delete("/rms/yield-rules/{rule_id}")
async def delete_yield_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.yield_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Kural silindi"}


# ── SEASONAL CALENDAR CRUD ──

class SeasonCreate(BaseModel):
    name: str
    season_type: str
    start_date: str
    end_date: str
    rate_multiplier: float = 1.0
    min_stay: int = 1
    color: str = "#3b82f6"
    is_active: bool = True


@router.get("/rms/seasonal-calendar")
async def get_seasonal_calendar(current_user: User = Depends(get_current_user)):
    seasons = await db.seasonal_calendar.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("start_date", 1).to_list(100)
    return {"seasons": seasons, "count": len(seasons)}


@router.post("/rms/seasonal-calendar")
async def create_season(
    season: SeasonCreate,
    current_user: User = Depends(get_current_user)
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **season.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.seasonal_calendar.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/rms/seasonal-calendar/{season_id}")
async def update_season(
    season_id: str,
    season: SeasonCreate,
    current_user: User = Depends(get_current_user)
):
    result = await db.seasonal_calendar.update_one(
        {"id": season_id, "tenant_id": current_user.tenant_id},
        {"$set": {**season.model_dump(), "updated_at": datetime.now(UTC).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Season not found")
    return {"message": "Sezon guncellendi", "id": season_id}


@router.delete("/rms/seasonal-calendar/{season_id}")
async def delete_season(
    season_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.seasonal_calendar.delete_one(
        {"id": season_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Season not found")
    return {"message": "Sezon silindi"}


# ── REWRITTEN AUTO-PRICING (7 Internal Factors) ──

@router.post("/rms/generate-pricing")
async def generate_internal_pricing(
    request: AutoPricingRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate pricing recommendations using 7 internal data factors (no competitor dependency)."""
    start = datetime.fromisoformat(request.start_date)
    end = datetime.fromisoformat(request.end_date)
    days_count = (end - start).days + 1
    tid = current_user.tenant_id
    now = datetime.now(UTC)

    room_types_query = {"tenant_id": tid}
    if request.room_type:
        room_types_query["name"] = request.room_type
    room_types = await db.room_types.find(room_types_query, {"_id": 0}).to_list(100)
    if not room_types:
        room_types = [{"name": "Standard", "base_rate": 4500, "min_rate": 2500, "max_rate": 9000}]

    total_rooms = await db.rooms.count_documents({"tenant_id": tid})
    if total_rooms == 0:
        total_rooms = 30

    # Load yield rules
    yield_rules = await db.yield_rules.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).sort("priority", 1).to_list(100)

    # Load seasonal calendar
    seasons = await db.seasonal_calendar.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).to_list(50)

    # Historical cancellation rate (last 90 days)
    ninety_days_ago = (now - timedelta(days=90)).isoformat()
    total_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}}
    )
    cancelled_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}, "status": "cancelled"}
    )
    hist_cancel_rate = cancelled_hist / total_hist if total_hist > 0 else 0.1

    # Channel performance (last 30 days)
    thirty_days = (now - timedelta(days=30)).isoformat()
    recent_bookings = await db.bookings.find(
        {"tenant_id": tid, "created_at": {"$gte": thirty_days},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "channel": 1, "total_amount": 1, "nights": 1}
    ).to_list(5000)

    channel_adr = {}
    for b in recent_bookings:
        ch = b.get("channel", "direct")
        if ch not in channel_adr:
            channel_adr[ch] = {"revenue": 0, "nights": 0}
        channel_adr[ch]["revenue"] += b.get("total_amount", 0)
        channel_adr[ch]["nights"] += b.get("nights", 1)

    # YoY comparison data
    year_ago_start = (start - timedelta(days=365)).isoformat()
    year_ago_end = (end - timedelta(days=365)).isoformat()
    yoy_bookings = await db.bookings.count_documents({
        "tenant_id": tid,
        "check_in": {"$gte": year_ago_start, "$lte": year_ago_end},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    })

    recommendations = []

    for day_offset in range(days_count):
        current_date = (start + timedelta(days=day_offset)).date().isoformat()
        date_obj = datetime.fromisoformat(current_date).replace(tzinfo=UTC)
        day_of_week = date_obj.weekday()
        month = date_obj.month
        days_to_arrival = (date_obj - now).days

        for rt in room_types:
            base_rate = rt.get("base_rate", 4500)
            min_rate = rt.get("min_rate", base_rate * 0.5)
            max_rate = rt.get("max_rate", base_rate * 2)

            # Current occupancy for this date
            occ_count = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$lte": current_date},
                "check_out": {"$gt": current_date},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            rt_rooms = await db.rooms.count_documents({"tenant_id": tid, "room_type": rt["name"]})
            if rt_rooms == 0:
                rt_rooms = rt.get("total_rooms", 5)
            occupancy_pct = (occ_count / rt_rooms * 100) if rt_rooms > 0 else 0

            # Booking pace (last 7 days for this target date)
            seven_ago = (now - timedelta(days=7)).isoformat()
            pace_count = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$lte": current_date},
                "check_out": {"$gt": current_date},
                "created_at": {"$gte": seven_ago},
            })
            daily_pace = pace_count / 7

            multiplier = 1.0
            reasons = []

            # FACTOR 1: Occupancy (25%)
            if occupancy_pct > 90:
                multiplier *= 1.25
                reasons.append(f"Cok yuksek doluluk ({occupancy_pct:.0f}%): +25%")
            elif occupancy_pct > 75:
                multiplier *= 1.15
                reasons.append(f"Yuksek doluluk ({occupancy_pct:.0f}%): +15%")
            elif occupancy_pct > 50:
                multiplier *= 1.05
                reasons.append(f"Orta doluluk ({occupancy_pct:.0f}%): +5%")
            elif occupancy_pct > 25:
                multiplier *= 0.95
                reasons.append(f"Dusuk doluluk ({occupancy_pct:.0f}%): -5%")
            else:
                multiplier *= 0.85
                reasons.append(f"Cok dusuk doluluk ({occupancy_pct:.0f}%): -15%")

            # FACTOR 2: Booking Pace / Pickup (20%)
            if daily_pace > 2:
                multiplier *= 1.10
                reasons.append(f"Guclu rez. hizi ({daily_pace:.1f}/gun): +10%")
            elif daily_pace > 1:
                multiplier *= 1.05
                reasons.append(f"Iyi rez. hizi ({daily_pace:.1f}/gun): +5%")
            elif daily_pace < 0.3 and occupancy_pct < 50:
                multiplier *= 0.92
                reasons.append(f"Yavas rez. hizi ({daily_pace:.1f}/gun): -8%")

            # FACTOR 3: Lead Time (15%)
            if days_to_arrival <= 3:
                if occupancy_pct < 50:
                    multiplier *= 0.90
                    reasons.append("Son dakika + dusuk doluluk: -10%")
                else:
                    multiplier *= 1.08
                    reasons.append("Son dakika + yuksek doluluk: +8%")
            elif days_to_arrival <= 14:
                multiplier *= 1.03
                reasons.append("Kisa vadeli talep: +3%")
            elif days_to_arrival > 60:
                multiplier *= 0.95
                reasons.append("Erken rezervasyon: -5%")

            # FACTOR 4: Day of Week & Seasonality (15%)
            is_weekend = day_of_week in [4, 5]
            if is_weekend:
                multiplier *= 1.12
                reasons.append("Hafta sonu talebi: +12%")

            # Check seasonal calendar
            season_applied = False
            for s in seasons:
                if s.get("start_date", "") <= current_date <= s.get("end_date", ""):
                    sm = s.get("rate_multiplier", 1.0)
                    multiplier *= sm
                    reasons.append(f"{s['name']} ({sm:.0%})")
                    season_applied = True
                    break
            if not season_applied:
                if month in [6, 7, 8]:
                    multiplier *= 1.20
                    reasons.append("Yaz sezonu: +20%")
                elif month in [12, 1]:
                    multiplier *= 1.10
                    reasons.append("Kis tatili: +10%")

            # FACTOR 5: Cancellation Rate (10%)
            if hist_cancel_rate > 0.2:
                multiplier *= 1.05
                reasons.append(f"Yuksek iptal orani ({hist_cancel_rate:.0%}): +5% (telafi)")
            elif hist_cancel_rate < 0.05:
                multiplier *= 0.98
                reasons.append("Dusuk iptal orani: -2%")

            # FACTOR 6: Channel Performance (10%)
            best_ch = max(channel_adr.items(), key=lambda x: x[1]["revenue"] / max(x[1]["nights"], 1), default=None)
            if best_ch and best_ch[1]["nights"] > 0:
                best_adr = best_ch[1]["revenue"] / best_ch[1]["nights"]
                if best_adr > base_rate * 1.1:
                    multiplier *= 1.03
                    reasons.append("Kanallar yuksek ADR sagliyor: +3%")

            # FACTOR 7: YoY Comparison (5%)
            if yoy_bookings > 0:
                yoy_ratio = len(recent_bookings) / max(yoy_bookings, 1)
                if yoy_ratio > 1.2:
                    multiplier *= 1.04
                    reasons.append("Gecen yila gore talep artisi: +4%")
                elif yoy_ratio < 0.8:
                    multiplier *= 0.97
                    reasons.append("Gecen yila gore talep dususu: -3%")

            # Apply yield rules
            for yr in yield_rules:
                if yr.get("room_types") and rt["name"] not in yr["room_types"]:
                    continue
                ct = yr["condition_type"]
                cv = yr["condition_value"]
                at = yr["action_type"]
                av = yr["action_value"]

                rule_applies = False
                if ct == "occupancy_above" and occupancy_pct > float(cv):
                    rule_applies = True
                elif ct == "occupancy_below" and occupancy_pct < float(cv):
                    rule_applies = True
                elif ct == "lead_time_below" and days_to_arrival < float(cv) and occupancy_pct < 60:
                    rule_applies = True
                elif ct == "lead_time_above" and days_to_arrival > float(cv):
                    rule_applies = True
                elif ct == "day_of_week":
                    dow_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    if dow_names[day_of_week] in str(cv).lower():
                        rule_applies = True

                if rule_applies:
                    if at == "increase_percent":
                        multiplier *= (1 + av / 100)
                        reasons.append(f"Kural '{yr['name']}': +{av}%")
                    elif at == "decrease_percent":
                        multiplier *= (1 - av / 100)
                        reasons.append(f"Kural '{yr['name']}': -{av}%")

            suggested_rate = round(base_rate * multiplier)
            suggested_rate = max(min_rate, min(suggested_rate, max_rate))

            # Confidence scoring
            conf = 0.3
            if occ_count > 0:
                conf += 0.2
            if pace_count > 0:
                conf += 0.15
            if days_to_arrival < 30:
                conf += 0.15
            if len(recent_bookings) > 20:
                conf += 0.1
            if season_applied:
                conf += 0.1
            conf = min(conf, 0.95)

            rec = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "date": current_date,
                "room_type": rt["name"],
                "current_rate": base_rate,
                "suggested_rate": suggested_rate,
                "change_pct": round((multiplier - 1) * 100, 1),
                "occupancy": round(occupancy_pct, 1),
                "booking_pace": round(daily_pace, 2),
                "confidence": round(conf, 2),
                "confidence_level": "Yuksek" if conf >= 0.7 else ("Orta" if conf >= 0.45 else "Dusuk"),
                "reasoning": " | ".join(reasons),
                "reasons": reasons,
                "is_weekend": is_weekend,
                "lead_time_days": days_to_arrival,
                "status": "pending",
                "generated_at": now.isoformat(),
            }
            recommendations.append(rec)

    if recommendations:
        await db.rms_pricing_recommendations.insert_many([r.copy() for r in recommendations])

    return {
        "message": f"{len(recommendations)} fiyat onerisi uretildi",
        "recommendations": recommendations,
        "summary": {
            "total": len(recommendations),
            "avg_change": round(sum(r["change_pct"] for r in recommendations) / len(recommendations), 1) if recommendations else 0,
            "increases": sum(1 for r in recommendations if r["change_pct"] > 0),
            "decreases": sum(1 for r in recommendations if r["change_pct"] < 0),
            "avg_confidence": round(sum(r["confidence"] for r in recommendations) / len(recommendations), 2) if recommendations else 0,
        },
    }
