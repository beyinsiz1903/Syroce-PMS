"""
autopilot_reco

Auto-split sub-router (shared imports/classes inlined).
"""
"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
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


# ── GET /autopilot/status ──
@router.get("/autopilot/status")
async def get_autopilot_status(current_user: User = Depends(get_current_user)):
    """Autopilot durumu"""
    from domains.ai.revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    return {
        'mode': autopilot.mode,
        'active': True,
        'last_cycle': datetime.now(UTC).isoformat()
    }
# ── POST /autopilot/run-cycle ──
@router.post("/autopilot/run-cycle")
async def run_autopilot_cycle(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Autopilot cycle manuel çalıştır"""
    from domains.ai.revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    report = await autopilot.daily_optimization_cycle(current_user.tenant_id)
    return report
# ── POST /autopilot/set-mode ──
@router.post("/autopilot/set-mode")
async def set_autopilot_mode(mode_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Autopilot modunu ayarla"""
    from domains.ai.revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    autopilot.mode = mode_data.get('mode', 'advisory')  # full_auto, supervised, advisory
    return {'success': True, 'new_mode': autopilot.mode}
# ── POST /ai/solve-overbooking ──
@router.post("/ai/solve-overbooking")
async def solve_overbooking(
    date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """AI-powered overbooking resolution suggestions"""
    target_date = datetime.fromisoformat(date).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Get all rooms
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)

    # Find overbookings (multiple bookings on same room same date)
    conflicts = []
    for room in rooms:
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'room_id': room['id'],
            'status': {'$in': ['confirmed', 'guaranteed']},
            'check_in': {'$lte': end_of_day.isoformat()},
            'check_out': {'$gte': start_of_day.isoformat()}
        }, {'_id': 0}).to_list(100)

        if len(bookings) > 1:
            conflicts.append({
                'room': room,
                'bookings': bookings
            })

    # Generate AI solutions
    solutions = []
    for conflict in conflicts:
        room = conflict['room']
        bookings = conflict['bookings']

        # Find alternative rooms of same type
        alt_rooms = [r for r in rooms if r['room_type'] == room['room_type'] and r['id'] != room['id']]

        for booking in bookings[1:]:  # Keep first booking, move others
            # Find available alternative rooms
            available_alts = []
            for alt_room in alt_rooms:
                # Check if alt room is available
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': alt_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })

                if existing == 0:
                    # Calculate guest priority score
                    guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
                    loyalty_tier = guest.get('loyalty_tier', 'standard') if guest else 'standard'
                    priority_score = {
                        'vip': 100,
                        'gold': 80,
                        'silver': 60,
                        'standard': 40
                    }.get(loyalty_tier, 40)

                    # Add OTA channel penalty (harder to move OTA bookings)
                    if booking.get('ota_channel'):
                        priority_score -= 20

                    available_alts.append({
                        'room': alt_room,
                        'priority_score': priority_score,
                        'reason': f"Same type ({alt_room['room_type']}), Floor {alt_room['floor']}"
                    })

            # Sort by priority score
            available_alts.sort(key=lambda x: x['priority_score'], reverse=True)

            if available_alts:
                best_option = available_alts[0]
                solutions.append({
                    'conflict_type': 'overbooking',
                    'severity': 'high',
                    'current_room': room['room_number'],
                    'booking_id': booking['id'],
                    'guest_name': booking.get('guest_name', 'Unknown'),
                    'check_in': booking['check_in'],
                    'check_out': booking['check_out'],
                    'recommended_action': 'move',
                    'recommended_room': best_option['room']['room_number'],
                    'recommended_room_id': best_option['room']['id'],
                    'confidence': 0.85,
                    'reason': best_option['reason'],
                    'impact': 'minimal',
                    'auto_apply': False
                })

    return {
        'date': target_date.isoformat(),
        'conflicts_found': len(conflicts),
        'solutions': solutions,
        'summary': f"Found {len(conflicts)} overbooking conflicts with {len(solutions)} AI-powered solutions"
    }
# ── POST /ai/recommend-room-moves ──
@router.post("/ai/recommend-room-moves")
async def recommend_room_moves(
    date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """AI recommendations for optimal room moves (upgrades, VIP service)"""
    target_date = datetime.fromisoformat(date).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)

    # Get bookings for target date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed']},
        'check_in': {'$lte': end_of_day.isoformat()},
        'check_out': {'$gte': start_of_day.isoformat()}
    }, {'_id': 0}).to_list(1000)

    recommendations = []

    for booking in bookings:
        guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
        if not guest:
            continue

        current_room = next((r for r in rooms if r['id'] == booking['room_id']), None)
        if not current_room:
            continue

        loyalty_tier = guest.get('loyalty_tier', 'standard')

        # VIP/Gold upgrade opportunities
        if loyalty_tier in ['vip', 'gold']:
            # Find better rooms available
            better_rooms = [r for r in rooms
                          if r['room_type'] != current_room['room_type']
                          and r['base_price'] > current_room['base_price']]

            for better_room in better_rooms:
                # Check availability
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': better_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })

                if existing == 0:
                    recommendations.append({
                        'type': 'upgrade',
                        'priority': 'high' if loyalty_tier == 'vip' else 'medium',
                        'booking_id': booking['id'],
                        'guest_name': guest.get('name', 'Unknown'),
                        'loyalty_tier': loyalty_tier,
                        'current_room': current_room['room_number'],
                        'recommended_room': better_room['room_number'],
                        'recommended_room_id': better_room['id'],
                        'reason': f"Complimentary upgrade for {loyalty_tier.upper()} guest",
                        'revenue_impact': 0,  # Complimentary
                        'confidence': 0.90
                    })
                    break  # One recommendation per booking

        # Room block avoidance
        blocks = await db.room_blocks.find({
            'tenant_id': current_user.tenant_id,
            'room_id': current_room['id'],
            'status': 'active',
            'start_date': {'$lte': booking['check_out']},
            '$or': [
                {'end_date': {'$gte': booking['check_in']}},
                {'end_date': None}
            ]
        }, {'_id': 0}).to_list(10)

        if blocks:
            # Find alternative same-type room
            alt_rooms = [r for r in rooms
                        if r['room_type'] == current_room['room_type']
                        and r['id'] != current_room['id']]

            for alt_room in alt_rooms:
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': alt_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })

                if existing == 0:
                    recommendations.append({
                        'type': 'block_avoidance',
                        'priority': 'urgent',
                        'booking_id': booking['id'],
                        'guest_name': guest.get('name', 'Unknown'),
                        'current_room': current_room['room_number'],
                        'recommended_room': alt_room['room_number'],
                        'recommended_room_id': alt_room['id'],
                        'reason': f"Room {current_room['room_number']} is blocked ({blocks[0]['type']})",
                        'revenue_impact': 0,
                        'confidence': 0.95
                    })
                    break

    # Sort by priority
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 99))

    return {
        'date': target_date.isoformat(),
        'recommendations': recommendations,
        'count': len(recommendations),
        'summary': f"Generated {len(recommendations)} AI room move recommendations"
    }
# ── POST /ai/recommend-rates ──
@router.post("/ai/recommend-rates")
async def recommend_rates(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """AI-powered dynamic rate recommendations"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    room_types = list({r['room_type'] for r in rooms})

    recommendations = []

    for rt in room_types:
        rt_rooms = [r for r in rooms if r['room_type'] == rt]
        total_rt_rooms = len(rt_rooms)
        base_rate = rt_rooms[0]['base_price'] if rt_rooms else 0

        current_date = start
        while current_date <= end:
            start_of_day = datetime.combine(current_date, datetime.min.time())
            end_of_day = datetime.combine(current_date, datetime.max.time())

            # Calculate occupancy
            occupied = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_id': {'$in': [r['id'] for r in rt_rooms]},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': end_of_day.isoformat()},
                'check_out': {'$gte': start_of_day.isoformat()}
            })

            occupancy_pct = (occupied / total_rt_rooms * 100) if total_rt_rooms > 0 else 0

            # AI pricing strategy
            if occupancy_pct >= 90:
                # High demand - increase rates
                recommended_rate = base_rate * 1.25
                strategy = 'demand_surge'
                reason = f"High occupancy ({occupancy_pct:.0f}%) - capitalize on demand"
                confidence = 0.88
            elif occupancy_pct >= 75:
                # Good demand - moderate increase
                recommended_rate = base_rate * 1.15
                strategy = 'optimize'
                reason = f"Strong demand ({occupancy_pct:.0f}%) - optimize revenue"
                confidence = 0.82
            elif occupancy_pct >= 50:
                # Moderate - maintain rates
                recommended_rate = base_rate
                strategy = 'maintain'
                reason = f"Normal occupancy ({occupancy_pct:.0f}%) - maintain base rates"
                confidence = 0.75
            else:
                # Low demand - discount to attract
                recommended_rate = base_rate * 0.85
                strategy = 'attract'
                reason = f"Low occupancy ({occupancy_pct:.0f}%) - attract bookings with discount"
                confidence = 0.80

            # Check day of week for adjustments
            day_of_week = current_date.weekday()
            if day_of_week in [4, 5]:  # Friday, Saturday
                recommended_rate *= 1.10
                reason += " + Weekend premium"

            recommendations.append({
                'date': current_date.isoformat(),
                'day_of_week': current_date.strftime('%A'),
                'room_type': rt,
                'current_rate': round(base_rate, 2),
                'recommended_rate': round(recommended_rate, 2),
                'difference': round(recommended_rate - base_rate, 2),
                'difference_pct': round(((recommended_rate - base_rate) / base_rate * 100), 1),
                'strategy': strategy,
                'reason': reason,
                'occupancy_pct': round(occupancy_pct, 1),
                'confidence': confidence,
                'revenue_impact': round((recommended_rate - base_rate) * (total_rt_rooms - occupied), 2)
            })

            current_date += timedelta(days=1)

    # Calculate total potential revenue impact
    total_impact = sum(r['revenue_impact'] for r in recommendations if r['revenue_impact'] > 0)

    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat()
        },
        'recommendations': recommendations,
        'summary': {
            'total_recommendations': len(recommendations),
            'increase_count': sum(1 for r in recommendations if r['difference'] > 0),
            'decrease_count': sum(1 for r in recommendations if r['difference'] < 0),
            'maintain_count': sum(1 for r in recommendations if r['difference'] == 0),
            'potential_revenue_increase': round(total_impact, 2)
        }
    }
