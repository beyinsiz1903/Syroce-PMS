"""
gm

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.helpers import require_module
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel











































_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /dashboard/gm/pickup-analysis ──
@router.get("/dashboard/gm/pickup-analysis")
async def get_pickup_analysis(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pickup analysis for revenue management"""
    current_user = await get_current_user(credentials)

    if not start_date:
        start_date = datetime.now(UTC).replace(day=1)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        # Next 30 days
        end_date = datetime.now(UTC) + timedelta(days=30)
    else:
        end_date = datetime.fromisoformat(end_date)

    # Get bookings for date range
    pickup_data = []

    # Group by booking date (created_at)
    pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'check_in': {
                    '$gte': start_date,
                    '$lte': end_date
                },
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            }
        },
        {
            '$group': {
                '_id': {
                    'stay_date': '$check_in',
                    'booking_date': '$created_at'
                },
                'room_count': {'$sum': 1},
                'total_revenue': {'$sum': '$total_amount'}
            }
        },
        {
            '$sort': {'_id.stay_date': 1}
        }
    ]

    async for doc in db.bookings.aggregate(pipeline):
        stay_date = doc['_id']['stay_date']
        booking_date = doc['_id']['booking_date']

        # Calculate days before arrival
        days_before = (stay_date - booking_date).days if stay_date and booking_date else 0

        pickup_data.append({
            'stay_date': stay_date.date().isoformat() if stay_date else None,
            'booking_date': booking_date.date().isoformat() if booking_date else None,
            'days_before_arrival': days_before,
            'rooms': doc['room_count'],
            'revenue': doc['total_revenue']
        })

    # Calculate pickup velocity
    sum(d['rooms'] for d in pickup_data)
    sum(d['revenue'] for d in pickup_data)

    # Group by days_before_arrival for trend analysis
    pickup_trends = {}
    for data in pickup_data:
        days_key = data['days_before_arrival']
        if days_key not in pickup_trends:
            pickup_trends[days_key] = {'rooms': 0, 'revenue': 0}
        pickup_trends[days_key]['rooms'] += data['rooms']
        pickup_trends[days_key]['revenue'] += data['revenue']

    return {
        'pickup_data': pickup_data,
        'pickup_trends': pickup_trends
    }
# ── GET /gm/team-performance ──
@router.get("/gm/team-performance")
async def get_team_performance(
    department: str | None = None,
    period: str = 'month',
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _: None = Depends(require_module("gm_dashboards")),
    _perm=Depends(require_op("view_system_diagnostics")),  # v103 DX alias drift fix
):
    """Get team performance metrics"""
    await get_current_user(credentials)

    # Mock team performance data
    team_data = {
        'front_desk': {
            'department': 'Front Desk',
            'staff_count': 8,
            'avg_performance_score': 92.5,
            'tasks_completed': 245,
            'guest_satisfaction': 4.6,
            'top_performer': {'name': 'Ayşe Yılmaz', 'score': 98},
            'metrics': {
                'check_ins': 156,
                'check_outs': 148,
                'avg_time': '4.2 min'
            }
        },
        'housekeeping': {
            'department': 'Housekeeping',
            'staff_count': 12,
            'avg_performance_score': 88.3,
            'tasks_completed': 612,
            'guest_satisfaction': 4.4,
            'top_performer': {'name': 'Fatma Demir', 'score': 95},
            'metrics': {
                'rooms_cleaned': 612,
                'avg_time': '28 min',
                'quality_score': 4.5
            }
        },
        'maintenance': {
            'department': 'Maintenance',
            'staff_count': 6,
            'avg_performance_score': 91.2,
            'tasks_completed': 89,
            'guest_satisfaction': 4.5,
            'top_performer': {'name': 'Mehmet Koç', 'score': 96},
            'metrics': {
                'tasks_completed': 89,
                'avg_response_time': '18 min',
                'sla_compliance': 94
            }
        },
        'fnb': {
            'department': 'F&B',
            'staff_count': 15,
            'avg_performance_score': 87.8,
            'tasks_completed': 1240,
            'guest_satisfaction': 4.3,
            'top_performer': {'name': 'Ali Şahin', 'score': 93},
            'metrics': {
                'orders_served': 1240,
                'avg_time': '12 min',
                'quality_score': 4.3
            }
        }
    }

    if department:
        return team_data.get(department, {})

    return {
        'departments': team_data,
        'period': period,
        'overall_performance': round(sum(d['avg_performance_score'] for d in team_data.values()) / len(team_data), 1)
    }
# ── GET /gm/complaints ──
@router.get("/gm/complaints")
async def get_complaints(
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get guest complaints"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status
    if priority:
        query['priority'] = priority

    complaints = []
    async for complaint in db.complaints.find(query).sort('created_at', -1).limit(limit):
        complaint.pop('_id', None)
        complaints.append(complaint)

    # If no complaints, create mock data
    if len(complaints) == 0:
        mock_complaints = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_name': 'Ahmet Yılmaz',
                'room_number': '205',
                'category': 'cleanliness',
                'subject': 'Oda temizliği yetersiz',
                'description': 'Banyoda havlu eksikliği var',
                'priority': 'normal',
                'status': 'open',
                'created_at': (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                'assigned_to': 'Housekeeping',
                'resolution': None
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_name': 'Zeynep Kaya',
                'room_number': '312',
                'category': 'noise',
                'subject': 'Gürültü şikayeti',
                'description': 'Yan odadan yüksek ses geliyor',
                'priority': 'high',
                'status': 'in_progress',
                'created_at': (datetime.now(UTC) - timedelta(hours=5)).isoformat(),
                'assigned_to': 'Front Desk',
                'resolution': None
            }
        ]
        complaints = mock_complaints

    return {
        'complaints': complaints,
        'count': len(complaints),
        'by_status': {
            'open': sum(1 for c in complaints if c['status'] == 'open'),
            'in_progress': sum(1 for c in complaints if c['status'] == 'in_progress'),
            'resolved': sum(1 for c in complaints if c['status'] == 'resolved')
        }
    }
# ── POST /gm/complaint ──
@router.post("/gm/complaint")
async def create_complaint(
    complaint_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_executive_reports")),  # v89 DW
):
    """Create a new complaint"""
    current_user = await get_current_user(credentials)

    complaint = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_name': complaint_data.get('guest_name'),
        'room_number': complaint_data.get('room_number'),
        'category': complaint_data.get('category'),
        'subject': complaint_data.get('subject'),
        'description': complaint_data.get('description'),
        'priority': complaint_data.get('priority', 'normal'),
        'status': 'open',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.name,
        'assigned_to': complaint_data.get('assigned_to'),
        'resolution': None
    }

    await db.complaints.insert_one(complaint)

    return {
        'message': 'Complaint created',
        'complaint_id': complaint['id']
    }
# ── POST /gm/complaint/{complaint_id}/resolve ──
@router.post("/gm/complaint/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: str,
    resolution_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_executive_reports")),  # v89 DW
):
    """Resolve a complaint"""
    current_user = await get_current_user(credentials)

    await db.complaints.update_one(
        {'id': complaint_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'resolved',
                'resolution': resolution_data.get('resolution'),
                'resolved_by': current_user.name,
                'resolved_at': datetime.now(UTC).isoformat()
            }
        }
    )

    return {
        'message': 'Complaint resolved',
        'complaint_id': complaint_id
    }
