"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from modules.pms_core.role_permission_service import require_op  # v99 DW
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import (
    AutoPricingRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: pricing_strategy) ───


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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
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
                'reason': a.get('reasoning', a.get('reason', 'Automatic pricing recommendation applied')),
                'old_rate': a.get('current_rate', 0),
                'new_rate': a.get('suggested_rate', 0),
                'room_type': a.get('room_type', ''),
                'applied_at': a.get('applied_at', ''),
            }
            for a in applied
        ]

    return {'adjustments': adjustments, 'count': len(adjustments)}




@router.post("/rms/apply-recommendations")
async def apply_all_recommendations(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Apply all pending pricing recommendations"""
    pending = await db.rms_pricing_recommendations.find(
        {'tenant_id': current_user.tenant_id, 'status': 'pending'},
        {'_id': 0}
    ).to_list(100)

    if not pending:
        return {'message': 'No pending recommendations to apply', 'applied_count': 0}

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
            'reason': rec.get('reasoning', 'Bulk recommendation applied'),
            'old_rate': rec.get('current_rate', 0),
            'new_rate': rec.get('suggested_rate', 0),
            'room_type': rec.get('room_type', ''),
            'applied_at': now,
            'applied_by': current_user.id,
        })

        applied_count += 1

    return {'message': f'{applied_count} recommendation(s) applied', 'applied_count': applied_count}




@router.post("/rms/auto-pricing")
async def generate_auto_pricing(
    request: AutoPricingRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
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

