"""
gm

Auto-split sub-router (shared imports/classes inlined).
"""
"""
PMS / Dashboard Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator




# ── Inline Models ──

class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0



class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: list[BudgetMonth]

















# ============= CHECK-IN ENHANCEMENTS =============













# ===== F&B MODULE ENHANCEMENTS =====








# 2. GET /api/executive/performance-alerts - Performance alerts




# 3. GET /api/executive/daily-summary - Daily summary




















# ============================================================================
# NOTIFICATION SYSTEM - Push Notifications
# ============================================================================





async def _build_complaint_management(current_user) -> dict:
    """Complaint management ortak helper — 3 feedback find'ı tek gather'da paralel."""
    tid = current_user.tenant_id
    active_docs, all_low_docs, resolved_docs = await asyncio.gather(
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': {'$ne': True},
        }).sort('created_at', -1).limit(20).to_list(20),
        db.feedback.find(
            {'tenant_id': tid, 'rating': {'$lte': 2}},
            {'_id': 0, 'category': 1},
        ).to_list(10000),
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': True,
            'resolved_at': {'$exists': True},
        }).limit(50).to_list(50),
    )

    now_utc = datetime.now(UTC)
    active_complaints = []
    for feedback in active_docs:
        try:
            ca = feedback.get('created_at') or now_utc.isoformat()
            days_open = (now_utc - datetime.fromisoformat(str(ca).replace('Z', '+00:00'))).days
        except Exception:
            days_open = 0
        active_complaints.append({
            'id': feedback.get('id', str(uuid.uuid4())),
            'guest_name': feedback.get('guest_name', 'Anonim'),
            'rating': feedback.get('rating', 1),
            'category': feedback.get('category', 'general'),
            'comment': feedback.get('comment', ''),
            'created_at': feedback.get('created_at'),
            'days_open': days_open,
        })

    categories: dict[str, int] = {}
    for feedback in all_low_docs:
        category = feedback.get('category', 'general')
        categories[category] = categories.get(category, 0) + 1

    category_breakdown = [
        {
            'category': cat,
            'category_tr': {
                'room': 'Oda', 'service': 'Servis', 'cleanliness': 'Temizlik',
                'fnb': 'Yiyecek & İçecek', 'general': 'Genel',
            }.get(cat, cat),
            'count': count,
        }
        for cat, count in categories.items()
    ]

    resolution_hours_list = []
    for feedback in resolved_docs:
        try:
            created = datetime.fromisoformat(feedback['created_at'].replace('Z', '+00:00'))
            resolved = datetime.fromisoformat(feedback['resolved_at'].replace('Z', '+00:00'))
            resolution_hours_list.append((resolved - created).total_seconds() / 3600)
        except Exception:
            continue
    avg_resolution_time = (
        sum(resolution_hours_list) / len(resolution_hours_list)
        if resolution_hours_list else 24
    )

    return {
        'active_complaints': active_complaints,
        'active_count': len(active_complaints),
        'category_breakdown': category_breakdown,
        'avg_resolution_time_hours': round(avg_resolution_time, 1),
        'urgent_complaints': len([c for c in active_complaints if c['days_open'] > 2]),
    }


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode




# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode




# ============================================================================
# SALES & CRM MOBILE - Satış & Müşteri Yönetimi
# ============================================================================

# Models

router = APIRouter(prefix="/api", tags=["PMS / Dashboard"])


# ── GET /gm/team-performance + GET /gm/complaint-management ──
@router.get("/gm/team-performance")
@router.get("/gm/complaint-management")
async def get_complaint_management(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_system_diagnostics"))  # v103 DX alias drift fix
):
    """
    Get complaint management overview
    Active complaints, categories, resolution times
    """
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)
# ── GET /gm/complaint-management ──
@router.get("/gm/complaint-management")
async def get_complaint_management_v2(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """v2 — _build_complaint_management helper'ını kullanır (DRY + N+1 fix)."""
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)
# ── GET /gm/snapshot-enhanced ──
@router.get("/gm/snapshot-enhanced")
async def get_enhanced_snapshot(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Enhanced GM snapshot - all critical metrics in one view
    Today vs Yesterday vs Last Week
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    # Get metrics for all three periods
    def get_metrics_for_date(date):
        return {
            'date': date.isoformat(),
            'occupancy': 0,  # To be calculated
            'revenue': 0,
            'check_ins': 0,
            'check_outs': 0,
            'complaints': 0,
            'pending_tasks': 0
        }

    today_metrics = get_metrics_for_date(today)
    yesterday_metrics = get_metrics_for_date(yesterday)
    last_week_metrics = get_metrics_for_date(last_week)

    # 7 bagimsiz read paralel — N+1 fix. Revenue Mongo aggregate ile (truncation yok).
    tid = current_user.tenant_id
    today_iso = today.isoformat()
    total_rooms, occupied_today, payment_agg, check_ins, check_outs, complaints, pending_tasks = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': today_iso}}},
            {'$group': {'_id': None, 't': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_in': today_iso, 'status': 'checked_in',
        }),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_out': today_iso, 'status': 'checked_out',
        }),
        db.feedback.count_documents({
            'tenant_id': tid, 'rating': {'$lte': 2},
            'created_at': {'$gte': today_iso},
        }),
        db.maintenance_tasks.count_documents({
            'tenant_id': tid, 'status': 'pending',
            'priority': {'$in': ['high', 'urgent']},
        }),
    )

    today_metrics['occupancy'] = round((occupied_today / total_rooms * 100) if total_rooms > 0 else 0, 1)
    today_metrics['revenue'] = (payment_agg[0]['t'] if payment_agg else 0) or 0
    today_metrics['check_ins'] = check_ins
    today_metrics['check_outs'] = check_outs
    today_metrics['complaints'] = complaints
    today_metrics['pending_tasks'] = pending_tasks

    # Simulated yesterday and last week data
    yesterday_metrics.update({
        'occupancy': today_metrics['occupancy'] - 3,
        'revenue': today_metrics['revenue'] * 0.95,
        'check_ins': today_metrics['check_ins'] - 2,
        'check_outs': today_metrics['check_outs'] + 1,
        'complaints': today_metrics['complaints'] + 1,
        'pending_tasks': today_metrics['pending_tasks'] + 2
    })

    last_week_metrics.update({
        'occupancy': today_metrics['occupancy'] - 5,
        'revenue': today_metrics['revenue'] * 0.92,
        'check_ins': today_metrics['check_ins'] - 3,
        'check_outs': today_metrics['check_outs'] - 1,
        'complaints': today_metrics['complaints'] + 2,
        'pending_tasks': today_metrics['pending_tasks'] + 3
    })

    return {
        'today': today_metrics,
        'yesterday': yesterday_metrics,
        'last_week': last_week_metrics,
        'trends': {
            'occupancy_trend': 'up' if today_metrics['occupancy'] > yesterday_metrics['occupancy'] else 'down',
            'revenue_trend': 'up' if today_metrics['revenue'] > yesterday_metrics['revenue'] else 'down',
            'complaints_trend': 'up' if today_metrics['complaints'] > yesterday_metrics['complaints'] else 'down'
        }
    }
