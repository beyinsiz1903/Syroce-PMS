"""
guest_intel

Auto-split sub-router (shared imports/classes inlined).
"""
"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.security import (
    get_current_user,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)


class GuestPersona(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(
    tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str
) -> None:
    try:
        await db.maintenance_tasks.insert_one({
            'id': uuid.uuid4().hex,
            'tenant_id': tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'title': title,
            'severity': severity,
            'source_alert_id': alert_id,
            'status': 'pending',
            'source': 'predictive_ai',
            'created_at': datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.exception('[ai] failed to create predictive maintenance task')


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == 'checkout' else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append({
            'staff_id': member.get('id') or member.get('staff_id'),
            'staff_name': member.get('name') or member.get('staff_name') or 'Staff',
            'task': {
                'room_id': room.get('id') or room.get('room_id'),
                'type': task_type,
                'priority': 'high' if task_type == 'checkout' else 'normal',
                'estimated_minutes': minutes_per_task,
            },
            'estimated_minutes': minutes_per_task,
        })
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append('Schedule additional housekeeping staff or extend shifts.')
    elif capacity_pct >= 90:
        recs.append('Capacity is tight — monitor task completion closely.')
    else:
        recs.append('Workload is healthy.')
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append('Consider rebalancing room-to-staff ratio.')
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        'silver': ['Welcome drink', 'Late checkout 1h'],
        'gold': ['Room upgrade subject to availability', 'Late checkout 2h', '10% F&B discount'],
        'platinum': ['Guaranteed upgrade', 'Late checkout 4h', '20% F&B discount', 'Lounge access'],
    }
    return matrix.get((tier or '').lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator








# ============= AI DYNAMIC PRICING (MARKET LEADER FEATURE) =============







# ============= WHATSAPP BUSINESS INTEGRATION =============














# ============= HOUSEKEEPING AI PREDICTIONS =============







# ============= PREDICTIVE ANALYTICS (GAME-CHANGER #2) =============










# ============= SOCIAL MEDIA COMMAND CENTER (GAME-CHANGER #3) =============










# ============= REVENUE AUTOPILOT (GAME-CHANGER #4) =============










# ============= GUEST DNA PROFILE (GAME-CHANGER #5) =============




# ============= DYNAMIC STAFFING AI (GAME-CHANGER #6) =============



















# ============= DELUXE+ ENTERPRISE FEATURES =============





# ============= MAINTENANCE WORK ORDERS =============













# ============= LOYALTY PROGRAM ENHANCEMENTS =============

















# ============= AI HOUSEKEEPING SCHEDULER =============

































# ============= MONITORING & LOGGING ENDPOINTS =============





# ============= NEW ENHANCEMENTS: OTA, GUEST PROFILE, HK MOBILE, RMS, MESSAGING, POS =============

# ===== 1. OTA RESERVATION DETAILS ENHANCEMENTS =====

# Extra charges model
# Multi-room reservation tracking

router = APIRouter(prefix="/api", tags=["AI / ML"])


# ── GET /guest-dna/{guest_id} ──
@router.get("/guest-dna/{guest_id}")
async def get_guest_dna_profile(guest_id: str, current_user: User = Depends(get_current_user)):
    """Get comprehensive guest DNA profile"""
    # Mock implementation
    return {
        'guest_id': guest_id,
        'personality_type': 'Business Traveler',
        'spending_pattern': 'High Value',
        'preferences': {
            'room_type': 'Executive',
            'floor': 'High',
            'amenities': ['Gym', 'Business Center']
        },
        'behavior_score': 8.5,
        'lifetime_value': 15000.0,
        'churn_risk': 'low'
    }
# ── POST /ai/guest-persona/analyze/{guest_id} ──
@router.post("/ai/guest-persona/analyze/{guest_id}")
async def analyze_guest_persona(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """
    AI Guest Persona Analysis
    - Analyzes booking history, spending patterns, reviews
    - Assigns persona categories
    - Provides actionable recommendations
    """
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Get guest's booking history
    bookings = []
    async for booking in db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }).sort('created_at', -1):
        bookings.append(booking)

    # Get spending data
    total_spent = 0
    ota_bookings = 0
    direct_bookings = 0
    avg_lead_time = []

    for booking in bookings:
        total_spent += booking.get('total_amount', 0)
        if booking.get('channel') in ['booking_com', 'expedia', 'airbnb']:
            ota_bookings += 1
        elif booking.get('channel') == 'direct':
            direct_bookings += 1

        # Calculate lead time
        created = datetime.fromisoformat(booking.get('created_at'))
        checkin = datetime.fromisoformat(booking.get('check_in'))
        lead_time = (checkin - created).days
        avg_lead_time.append(lead_time)

    # Get reviews/feedback
    reviews = []
    async for review in db.department_feedback.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }):
        reviews.append(review)

    negative_reviews = sum(1 for r in reviews if r.get('rating', 0) < 3)

    # Get upsell history
    upsells_accepted = 0
    async for charge in db.folio_charges.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'charge_category': {'$in': ['spa', 'upgrade', 'minibar']}
    }):
        upsells_accepted += 1

    # AI Persona Analysis
    personas = []

    # 1. Price Sensitive
    if len(bookings) > 0:
        avg_spend = total_spent / len(bookings)
        if avg_spend < 100 and avg_lead_time and sum(avg_lead_time) / len(avg_lead_time) > 30:
            personas.append({
                'type': 'price_sensitive',
                'confidence': 0.85,
                'indicators': [
                    f'Low average spend: ${avg_spend:.2f} per booking',
                    f'Long booking lead time: {sum(avg_lead_time) / len(avg_lead_time):.0f} days',
                    'Likely shops for best rates'
                ],
                'recommendations': [
                    'Offer early bird discounts',
                    'Send promotional emails for off-season',
                    'Avoid premium upsells',
                    'Focus on value packages'
                ]
            })

    # 2. Experience Seeker
    if upsells_accepted > 3:
        personas.append({
            'type': 'experience_seeker',
            'confidence': 0.90,
            'indicators': [
                f'Accepted {upsells_accepted} upsells/add-ons',
                'High engagement with hotel services',
                'Values experiences over price'
            ],
            'recommendations': [
                'Offer room upgrade at check-in',
                'Suggest spa packages',
                'Promote exclusive experiences',
                'VIP treatment opportunities'
            ]
        })

    # 3. Complainer
    if negative_reviews >= 2:
        personas.append({
            'type': 'complainer',
            'confidence': 0.80,
            'indicators': [
                f'{negative_reviews} negative reviews/feedback',
                'High expectations, difficult to satisfy',
                'Requires extra attention'
            ],
            'recommendations': [
                '⚠️ Assign best available room',
                'Front desk alert on arrival',
                'Proactive service recovery',
                'Senior staff handling',
                'Consider welcome amenity'
            ]
        })

    # 4. Upsell Candidate
    if total_spent > 1000 and upsells_accepted > 0:
        personas.append({
            'type': 'upsell_candidate',
            'confidence': 0.88,
            'indicators': [
                f'Total lifetime spend: ${total_spent:.2f}',
                f'Previously accepted {upsells_accepted} upsells',
                'Receptive to premium offerings'
            ],
            'recommendations': [
                '💰 Offer room upgrade ($50-100)',
                'Suggest late checkout',
                'Promote F&B packages',
                'Spa services upsell',
                'Airport transfer service'
            ]
        })

    # 5. High LTV (Lifetime Value)
    if total_spent > 2000 or len(bookings) > 5:
        ltv_score = total_spent + (len(bookings) * 200)  # Factor in repeat visits
        personas.append({
            'type': 'high_ltv',
            'confidence': 0.95,
            'indicators': [
                f'Lifetime value: ${ltv_score:.2f}',
                f'{len(bookings)} total stays',
                'Most valuable guest segment'
            ],
            'recommendations': [
                '⭐ VIP treatment',
                'Loyalty program auto-upgrade',
                'Exclusive perks and benefits',
                'Personalized communication',
                'Invitation to special events'
            ]
        })

    # 6. OTA → Direct Conversion Candidate
    if ota_bookings > 0 and direct_bookings == 0 and len(bookings) >= 2:
        personas.append({
            'type': 'ota_to_direct_candidate',
            'confidence': 0.75,
            'indicators': [
                f'{ota_bookings} OTA bookings, 0 direct bookings',
                'Repeat customer (familiar with hotel)',
                'High conversion potential'
            ],
            'recommendations': [
                '🎯 Offer direct booking discount (10-15%)',
                'Highlight member benefits',
                'Send personalized email campaign',
                'Loyalty points bonus for direct booking',
                'Best rate guarantee promotion'
            ]
        })

    # Store personas
    for persona_data in personas:
        persona = GuestPersona(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            persona_type=persona_data['type'],
            confidence_score=persona_data['confidence'],
            indicators=persona_data['indicators'],
            recommendations=persona_data['recommendations']
        )

        # Check if exists
        existing = await db.guest_personas.find_one({
            'guest_id': guest_id,
            'tenant_id': current_user.tenant_id,
            'persona_type': persona_data['type']
        })

        persona_dict = persona.model_dump()
        persona_dict['created_at'] = persona_dict['created_at'].isoformat()
        persona_dict['updated_at'] = persona_dict['updated_at'].isoformat()

        if existing:
            await db.guest_personas.update_one(
                {'id': existing.get('id')},
                {'$set': persona_dict}
            )
        else:
            await db.guest_personas.insert_one(persona_dict)

    return {
        'guest_id': guest_id,
        'guest_name': guest.get('name'),
        'analysis_summary': {
            'total_bookings': len(bookings),
            'lifetime_value': round(total_spent, 2),
            'ota_bookings': ota_bookings,
            'direct_bookings': direct_bookings,
            'upsells_accepted': upsells_accepted,
            'negative_reviews': negative_reviews
        },
        'personas_detected': len(personas),
        'personas': personas,
        'primary_persona': personas[0]['type'] if personas else None
    }
# ── GET /ai/guest-persona/all-insights ──
@router.get("/ai/guest-persona/all-insights")
async def get_all_guest_insights(
    persona_type: str | None = None,
    min_confidence: float = 0.7,
    current_user: User = Depends(get_current_user)
):
    """
    Get all guest persona insights
    - Segment guests by persona type
    - Actionable marketing campaigns
    """
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        'confidence_score': {'$gte': min_confidence}
    }

    if persona_type:
        match_criteria['persona_type'] = persona_type

    personas = await db.guest_personas.find(match_criteria).sort('confidence_score', -1).to_list(5000)

    # Batch lookup all referenced guests in one query (was N+1)
    guest_ids = list({p.get('guest_id') for p in personas if p.get('guest_id')})
    guest_name_map = {}
    if guest_ids:
        async for g in db.guests.find(
            {'id': {'$in': guest_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'name': 1}
        ):
            guest_name_map[g['id']] = g.get('name', 'Unknown')

    insights = []
    for persona in personas:
        gid = persona.get('guest_id')
        insights.append({
            'guest_id': gid,
            'guest_name': guest_name_map.get(gid, 'Unknown'),
            'persona_type': persona.get('persona_type'),
            'confidence': persona.get('confidence_score'),
            'recommendations': persona.get('recommendations')
        })

    # Group by persona type
    by_type = {}
    for insight in insights:
        ptype = insight['persona_type']
        if ptype not in by_type:
            by_type[ptype] = []
        by_type[ptype].append(insight)

    return {
        'total_insights': len(insights),
        'persona_filter': persona_type,
        'min_confidence': min_confidence,
        'insights': insights,
        'by_type': {k: len(v) for k, v in by_type.items()},
        'marketing_campaigns': [
            {'persona_type': ptype, 'audience_size': len(items),
             'suggestion': f"{ptype} segmenti için kişiselleştirilmiş kampanya"}
            for ptype, items in by_type.items() if items
        ]
    }
