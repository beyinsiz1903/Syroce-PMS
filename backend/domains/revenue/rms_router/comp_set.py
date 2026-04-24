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
    AddCompetitorRequest,
    ScrapePricesRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: comp_set) ───


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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
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

