"""
PMS / Calendar Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date
import os
import uuid
import random
import logging
import io

from core.database import db
from core.security import (
    get_current_user, security, JWT_SECRET, JWT_ALGORITHM,
    generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    create_audit_log, require_feature, require_module,
    require_super_admin_guard as require_super_admin, require_admin,
    get_tenant_modules, load_tenant_doc,
)
from models.schemas import User, CreateRateCodeRequest, GetCalendarTooltipRequest
from models.enums import UserRole

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Calendar"])


# ── Inline Models ──

class ChannelMixRequest(BaseModel):
    start_date: str = Field(..., description="Inclusive period start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Inclusive period end date (YYYY-MM-DD)")


@router.get("/enterprise/rate-leakage")
@cached(ttl=900, key_prefix="enterprise_rate_leakage")  # Cache for 15 min
async def detect_rate_leakage(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Detect rate leakage where OTA rates are lower than direct rates"""
    current_user = await get_current_user(credentials)
    
    # Default to next 30 days
    start = datetime.fromisoformat(start_date).date() if start_date else datetime.now(timezone.utc).date()
    end = datetime.fromisoformat(end_date).date() if end_date else (start + timedelta(days=30))
    
    # Get rooms
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    room_types = list(set(r['room_type'] for r in rooms))
    
    leakages = []
    total_leakage_amount = 0
    
    for rt in room_types:
        rt_rooms = [r for r in rooms if r['room_type'] == rt]
        direct_rate = rt_rooms[0].get('base_rate', 0) if rt_rooms else 0
        
        # Get OTA bookings in date range
        ota_bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'room_id': {'$in': [r['id'] for r in rt_rooms]},
            'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()},
            'ota_channel': {'$ne': None},
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }, {'_id': 0}).to_list(1000)
        
        for booking in ota_bookings:
            nights = (datetime.fromisoformat(booking['check_out']) - datetime.fromisoformat(booking['check_in'])).days
            if nights > 0:
                ota_rate = booking.get('rate_per_night', 0)
                
                # Rate leakage = OTA rate < Direct rate
                if ota_rate < direct_rate:
                    leakage_amount = (direct_rate - ota_rate) * nights
                    total_leakage_amount += leakage_amount
                    
                    leakages.append({
                        'booking_id': booking['id'],
                        'guest_name': booking.get('guest_name', 'Unknown'),
                        'room_type': rt,
                        'ota_channel': booking['ota_channel'],
                        'check_in': booking['check_in'],
                        'check_out': booking['check_out'],
                        'nights': nights,
                        'direct_rate': round(direct_rate, 2),
                        'ota_rate': round(ota_rate, 2),
                        'difference_per_night': round(direct_rate - ota_rate, 2),
                        'total_leakage': round(leakage_amount, 2),
                        'commission_pct': booking.get('commission_pct', 0),
                        'severity': 'high' if (direct_rate - ota_rate) > 20 else 'medium' if (direct_rate - ota_rate) > 10 else 'low'
                    })
    
    # Sort by total leakage descending
    leakages.sort(key=lambda x: x['total_leakage'], reverse=True)
    
    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat()
        },
        'summary': {
            'total_leakage_instances': len(leakages),
            'total_leakage_amount': round(total_leakage_amount, 2),
            'high_severity_count': sum(1 for l in leakages if l['severity'] == 'high'),
            'medium_severity_count': sum(1 for l in leakages if l['severity'] == 'medium')
        },
        'leakages': leakages[:50],  # Top 50 worst leakages
        'recommendations': [
            "Update OTA rate parity to match or exceed direct rates",
            "Review commission structures with high-leakage OTAs",
            "Consider restricting inventory on channels with severe leakage"
        ]
    }



@router.get("/enterprise/pickup-pace")
@cached(ttl=900, key_prefix="enterprise_pickup_pace")  # Cache for 15 min
async def get_pickup_pace(
    target_date: str,
    lookback_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Analyze booking pickup pace for a target date"""
    target = datetime.fromisoformat(target_date).date()
    today = datetime.now(timezone.utc).date()
    
    # Get bookings for target date created in last lookback_days
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': target.isoformat(),
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'created_at': {'$gte': (today - timedelta(days=lookback_days)).isoformat()}
    }, {'_id': 0}).to_list(1000)
    
    # Group by creation date
    pickup_by_date = {}
    for booking in bookings:
        created_date = datetime.fromisoformat(booking['created_at']).date()
        days_before_arrival = (target - created_date).days
        
        if days_before_arrival >= 0:
            if days_before_arrival not in pickup_by_date:
                pickup_by_date[days_before_arrival] = {
                    'count': 0,
                    'revenue': 0,
                    'channels': {}
                }
            
            pickup_by_date[days_before_arrival]['count'] += 1
            pickup_by_date[days_before_arrival]['revenue'] += booking.get('total_amount', 0)
            
            channel = booking.get('ota_channel') or 'direct'
            pickup_by_date[days_before_arrival]['channels'][channel] = \
                pickup_by_date[days_before_arrival]['channels'].get(channel, 0) + 1
    
    # Create timeline
    pickup_timeline = []
    cumulative_bookings = 0
    cumulative_revenue = 0
    
    for days_before in range(lookback_days, -1, -1):
        if days_before in pickup_by_date:
            data = pickup_by_date[days_before]
            cumulative_bookings += data['count']
            cumulative_revenue += data['revenue']
        
        pickup_timeline.append({
            'days_before_arrival': days_before,
            'date': (target - timedelta(days=days_before)).isoformat(),
            'daily_bookings': pickup_by_date.get(days_before, {}).get('count', 0),
            'daily_revenue': round(pickup_by_date.get(days_before, {}).get('revenue', 0), 2),
            'cumulative_bookings': cumulative_bookings,
            'cumulative_revenue': round(cumulative_revenue, 2)
        })
    
    # Calculate velocity (bookings per day)
    recent_7_days = sum(pickup_by_date.get(i, {}).get('count', 0) for i in range(7))
    velocity = round(recent_7_days / 7, 2)
    
    return {
        'target_date': target.isoformat(),
        'days_until_arrival': (target - today).days,
        'total_bookings': cumulative_bookings,
        'total_revenue': round(cumulative_revenue, 2),
        'velocity_7day': velocity,
        'pickup_timeline': pickup_timeline,
        'insights': [
            f"Current pace: {velocity} bookings/day",
            f"Total bookings to date: {cumulative_bookings}",
            f"Days until arrival: {(target - today).days}"
        ]
    }



@router.get("/enterprise/availability-heatmap")
@cached(ttl=900, key_prefix="enterprise_avail_heatmap")  # Cache for 15 min
async def get_availability_heatmap(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Generate availability heatmap showing occupancy intensity"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    # Get all rooms
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    total_rooms = len(rooms)
    room_types = list(set(r['room_type'] for r in rooms))
    
    heatmap_data = []
    
    current_date = start
    while current_date <= end:
        start_of_day = datetime.combine(current_date, datetime.min.time())
        end_of_day = datetime.combine(current_date, datetime.max.time())
        
        # Get bookings for this date
        occupied = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
            'check_in': {'$lte': end_of_day.isoformat()},
            'check_out': {'$gte': start_of_day.isoformat()}
        })
        
        # Get blocks for this date
        blocks = await db.room_blocks.count_documents({
            'tenant_id': current_user.tenant_id,
            'status': 'active',
            'start_date': {'$lte': current_date.isoformat()},
            '$or': [
                {'end_date': {'$gte': current_date.isoformat()}},
                {'end_date': None}
            ]
        })
        
        available = total_rooms - occupied - blocks
        occupancy_pct = round((occupied / total_rooms * 100) if total_rooms > 0 else 0, 1)
        
        # Determine intensity
        if occupancy_pct >= 95:
            intensity = 'critical'  # Red
        elif occupancy_pct >= 85:
            intensity = 'high'  # Orange
        elif occupancy_pct >= 70:
            intensity = 'moderate'  # Yellow
        elif occupancy_pct >= 50:
            intensity = 'medium'  # Light green
        else:
            intensity = 'low'  # Green
        
        # Get room type breakdown
        rt_breakdown = {}
        for rt in room_types:
            rt_rooms = [r for r in rooms if r['room_type'] == rt]
            rt_occupied = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_id': {'$in': [r['id'] for r in rt_rooms]},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': end_of_day.isoformat()},
                'check_out': {'$gte': start_of_day.isoformat()}
            })
            rt_breakdown[rt] = {
                'occupied': rt_occupied,
                'total': len(rt_rooms),
                'occupancy_pct': round((rt_occupied / len(rt_rooms) * 100) if len(rt_rooms) > 0 else 0, 1)
            }
        
        heatmap_data.append({
            'date': current_date.isoformat(),
            'day_of_week': current_date.strftime('%a'),
            'occupied': occupied,
            'available': available,
            'blocked': blocks,
            'total': total_rooms,
            'occupancy_pct': occupancy_pct,
            'intensity': intensity,
            'room_types': rt_breakdown
        })
        
        current_date += timedelta(days=1)
    
    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'days': len(heatmap_data)
        },
        'summary': {
            'avg_occupancy': round(sum(d['occupancy_pct'] for d in heatmap_data) / len(heatmap_data), 1),
            'peak_date': max(heatmap_data, key=lambda x: x['occupancy_pct'])['date'],
            'peak_occupancy': max(d['occupancy_pct'] for d in heatmap_data),
            'critical_days': sum(1 for d in heatmap_data if d['intensity'] == 'critical'),
            'high_days': sum(1 for d in heatmap_data if d['intensity'] == 'high')
        },
        'heatmap': heatmap_data
    }


@router.get("/deluxe/group-bookings")
@cached(ttl=300, key_prefix="deluxe_group_bookings")  # Cache for 5 min
async def get_group_bookings(
    start_date: str,
    end_date: str,
    min_rooms: int = 5,
    current_user: User = Depends(get_current_user)
):
    """Detect and analyze group bookings (5+ rooms)"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    # Get all bookings in range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }, {'_id': 0}).to_list(10000)
    
    # Group by company_id and check_in date
    groups = {}
    for booking in bookings:
        company_id = booking.get('company_id')
        if not company_id:
            continue
        
        check_in = booking['check_in']
        key = f"{company_id}_{check_in}"
        
        if key not in groups:
            groups[key] = {
                'company_id': company_id,
                'check_in': check_in,
                'check_out': booking['check_out'],
                'bookings': [],
                'room_count': 0,
                'total_revenue': 0
            }
        
        groups[key]['bookings'].append(booking)
        groups[key]['room_count'] += 1
        groups[key]['total_revenue'] += booking.get('total_amount', 0)
    
    # Filter groups with min_rooms or more
    group_bookings = []
    for key, group in groups.items():
        if group['room_count'] >= min_rooms:
            # Get company info
            company = await db.companies.find_one({
                'id': group['company_id'],
                'tenant_id': current_user.tenant_id
            }, {'_id': 0})
            
            group_bookings.append({
                'group_id': key,
                'company_id': group['company_id'],
                'company_name': company.get('name', 'Unknown') if company else 'Unknown',
                'check_in': group['check_in'],
                'check_out': group['check_out'],
                'room_count': group['room_count'],
                'total_revenue': round(group['total_revenue'], 2),
                'avg_rate': round(group['total_revenue'] / group['room_count'], 2),
                'room_numbers': [b.get('room_number', 'TBD') for b in group['bookings']],
                'booking_ids': [b['id'] for b in group['bookings']],
                'is_large_group': group['room_count'] >= 10
            })
    
    # Sort by room count descending
    group_bookings.sort(key=lambda x: x['room_count'], reverse=True)
    
    return {
        'period': {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'groups': group_bookings,
        'total_groups': len(group_bookings),
        'total_rooms': sum(g['room_count'] for g in group_bookings),
        'total_revenue': round(sum(g['total_revenue'] for g in group_bookings), 2)
    }



@router.get("/deluxe/pickup-pace-analytics")
@cached(ttl=900, key_prefix="deluxe_pickup_pace")  # Cache for 15 min
async def get_pickup_pace_analytics(
    target_date: str,
    lookback_days: int = 90,
    group_only: bool = False,
    company_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Advanced pickup pace analytics with trend analysis"""
    target = datetime.fromisoformat(target_date).date()
    today = datetime.now(timezone.utc).date()
    
    # Get bookings created in lookback period for target date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': target.isoformat(),
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }, {'_id': 0}).to_list(10000)

    # Optional filters: group-only and company
    if group_only:
        bookings = [b for b in bookings if b.get('group_booking_id')]
    if company_id:
        bookings = [b for b in bookings if b.get('company_id') == company_id]
    
    # Build daily pickup timeline
    daily_pickup = {}
    for booking in bookings:
        created_date = datetime.fromisoformat(booking['created_at']).date()
        days_before = (target - created_date).days
        
        if days_before >= 0 and days_before <= lookback_days:
            if days_before not in daily_pickup:
                daily_pickup[days_before] = {'count': 0, 'revenue': 0, 'channels': {}}
            
            daily_pickup[days_before]['count'] += 1
            daily_pickup[days_before]['revenue'] += booking.get('total_amount', 0)
            
            channel = booking.get('ota_channel') or 'direct'
            daily_pickup[days_before]['channels'][channel] = \
                daily_pickup[days_before]['channels'].get(channel, 0) + 1
    
    # Create chart data
    chart_data = []
    cumulative_bookings = 0
    cumulative_revenue = 0
    
    for days_before in range(lookback_days, -1, -1):
        data = daily_pickup.get(days_before, {'count': 0, 'revenue': 0})
        cumulative_bookings += data['count']
        cumulative_revenue += data['revenue']
        
        chart_data.append({
            'days_before': days_before,
            'date': (target - timedelta(days=days_before)).isoformat(),
            'daily_pickup': data['count'],
            'daily_revenue': round(data['revenue'], 2),
            'cumulative_bookings': cumulative_bookings,
            'cumulative_revenue': round(cumulative_revenue, 2)
        })
    
    # Calculate velocities
    velocity_7 = sum(daily_pickup.get(i, {}).get('count', 0) for i in range(7)) / 7
    velocity_14 = sum(daily_pickup.get(i, {}).get('count', 0) for i in range(14)) / 14
    velocity_30 = sum(daily_pickup.get(i, {}).get('count', 0) for i in range(30)) / 30

    # Aggregate channel-level pickup (for direct vs OTA and other breakdowns)
    channel_pickup: Dict[str, int] = {}
    for day_data in daily_pickup.values():
        for ch, cnt in day_data.get('channels', {}).items():
            channel_pickup[ch] = channel_pickup.get(ch, 0) + cnt

    channels_summary = [
        {
            'channel': ch,
            'bookings': count,
        }
        for ch, count in channel_pickup.items()
    ]
    
    return {
        'target_date': target.isoformat(),
        'days_until_arrival': (target - today).days,
        'chart_data': chart_data,
        'summary': {
            'total_bookings': cumulative_bookings,
            'total_revenue': round(cumulative_revenue, 2),
            'velocity_7day': round(velocity_7, 2),
            'velocity_14day': round(velocity_14, 2),
            'velocity_30day': round(velocity_30, 2)
        },
        'channels_summary': channels_summary
    }



@router.get("/deluxe/lead-time-analysis")
@cached(ttl=900, key_prefix="deluxe_lead_time")  # Cache for 15 min
async def get_lead_time_analysis(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Analyze booking lead time patterns"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }, {'_id': 0}).to_list(10000)
    
    lead_times = []
    channel_lead_times = {}
    
    for booking in bookings:
        created = datetime.fromisoformat(booking['created_at']).date()
        check_in = datetime.fromisoformat(booking['check_in']).date()
        lead_time = (check_in - created).days
        
        if lead_time >= 0:
            lead_times.append(lead_time)
            
            channel = booking.get('ota_channel') or 'direct'
            if channel not in channel_lead_times:
                channel_lead_times[channel] = []
            channel_lead_times[channel].append(lead_time)
    
    # Calculate statistics
    if lead_times:
        avg_lead_time = sum(lead_times) / len(lead_times)
        median_lead_time = sorted(lead_times)[len(lead_times) // 2]
    else:
        avg_lead_time = 0
        median_lead_time = 0
    
    # Lead time distribution
    distribution = {
        'same_day': sum(1 for lt in lead_times if lt == 0),
        'next_day': sum(1 for lt in lead_times if lt == 1),
        '2_7_days': sum(1 for lt in lead_times if 2 <= lt <= 7),
        '8_14_days': sum(1 for lt in lead_times if 8 <= lt <= 14),
        '15_30_days': sum(1 for lt in lead_times if 15 <= lt <= 30),
        '31_60_days': sum(1 for lt in lead_times if 31 <= lt <= 60),
        '61_90_days': sum(1 for lt in lead_times if 61 <= lt <= 90),
        'over_90_days': sum(1 for lt in lead_times if lt > 90)
    }
    
    # Channel breakdown
    channel_stats = {}
    for channel, times in channel_lead_times.items():
        channel_stats[channel] = {
            'avg_lead_time': round(sum(times) / len(times), 1) if times else 0,
            'median_lead_time': sorted(times)[len(times) // 2] if times else 0,
            'booking_count': len(times)
        }
    
    return {
        'period': {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'overall': {
            'avg_lead_time': round(avg_lead_time, 1),
            'median_lead_time': median_lead_time,
            'total_bookings': len(bookings)
        },
        'distribution': distribution,
        'by_channel': channel_stats,
        'optimal_booking_window': f"{int(median_lead_time)} days" if median_lead_time > 0 else "Same day"
    }



@router.get("/deluxe/oversell-protection")
@cached(ttl=600, key_prefix="deluxe_oversell")  # Cache for 10 min
async def get_oversell_protection_map(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """AI oversell protection heatmap"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    total_rooms = len(rooms)
    
    protection_map = []
    current_date = start
    
    while current_date <= end:
        start_of_day = datetime.combine(current_date, datetime.min.time())
        end_of_day = datetime.combine(current_date, datetime.max.time())
        
        # Count bookings
        bookings_count = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
            'check_in': {'$lte': end_of_day.isoformat()},
            'check_out': {'$gte': start_of_day.isoformat()}
        })
        
        occupancy_pct = (bookings_count / total_rooms * 100) if total_rooms > 0 else 0
        
        # Calculate oversell risk and protection (5-level system)
        if occupancy_pct >= 100:
            risk_level = 'blackout'  # New level
            max_oversell = 0
            recommendation = "🔴 BLACKOUT - STOP ALL SELLING"
        elif occupancy_pct >= 95:
            risk_level = 'danger'
            max_oversell = 0
            recommendation = "🔴 RED ALERT - Stop selling, relocate if possible"
        elif occupancy_pct >= 85:
            risk_level = 'caution'
            max_oversell = 1
            recommendation = "🟠 ORANGE - Careful, max 1 oversell with backup"
        elif occupancy_pct >= 70:
            risk_level = 'moderate'
            max_oversell = 2
            recommendation = "🟡 YELLOW - Allow 2 oversells, monitor closely"
        else:
            risk_level = 'safe'
            max_oversell = 3
            recommendation = "🟢 GREEN - Safe to sell, normal operations"
        
        # Calculate walk probability
        walk_probability = max(0, min(100, (occupancy_pct - 90) * 10))
        
        protection_map.append({
            'date': current_date.isoformat(),
            'occupancy_pct': round(occupancy_pct, 1),
            'bookings': bookings_count,
            'available': total_rooms - bookings_count,
            'risk_level': risk_level,
            'max_oversell': max_oversell,
            'walk_probability': round(walk_probability, 1),
            'recommendation': recommendation
        })
        
        current_date += timedelta(days=1)
    
    return {
        'period': {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'protection_map': protection_map,
        'summary': {
            'danger_days': sum(1 for d in protection_map if d['risk_level'] == 'danger')
        }
    }



@router.get("/deluxe/grouped-conflicts")
@cached(ttl=600, key_prefix="deluxe_grouped_conflicts")  # Cache for 10 min
async def get_grouped_conflicts(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get booking conflicts grouped by room for cleaner display"""
    
    # Default to next 30 days
    if not start_date:
        start_date = datetime.now(timezone.utc).isoformat()
    if not end_date:
        end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    
    # Find all overlapping bookings
    pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$gte': start_date, '$lte': end_date}
            }
        },
        {
            '$group': {
                '_id': {
                    'room_id': '$room_id',
                    'date': {'$substr': ['$check_in', 0, 10]}
                },
                'count': {'$sum': 1},
                'bookings': {
                    '$push': {
                        'id': '$id',
                        'guest_id': '$guest_id',
                        'check_in': '$check_in',
                        'check_out': '$check_out',
                        'total_amount': '$total_amount'
                    }
                }
            }
        },
        {
            '$match': {'count': {'$gt': 1}}
        }
    ]
    
    conflicts_raw = await db.bookings.aggregate(pipeline).to_list(1000)
    
    # Group by room
    room_conflicts = {}
    total_conflicts = 0
    
    for conflict in conflicts_raw:
        room_id = conflict['_id']['room_id']
        if room_id not in room_conflicts:
            # Get room details
            room = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
            room_conflicts[room_id] = {
                'room_number': room.get('room_number', 'Unknown') if room else 'Unknown',
                'room_type': room.get('room_type', 'N/A') if room else 'N/A',
                'conflict_dates': [],
                'total_overlaps': 0
            }
        
        room_conflicts[room_id]['conflict_dates'].append({
            'date': conflict['_id']['date'],
            'overlap_count': conflict['count'],
            'bookings': conflict['bookings']
        })
        room_conflicts[room_id]['total_overlaps'] += (conflict['count'] - 1)
        total_conflicts += (conflict['count'] - 1)
    
    # Convert to list and sort by severity
    grouped_list = []
    for room_id, data in room_conflicts.items():
        grouped_list.append({
            'room_id': room_id,
            'room_number': data['room_number'],
            'room_type': data['room_type'],
            'total_overlaps': data['total_overlaps'],
            'conflict_count': len(data['conflict_dates']),
            'conflict_dates': sorted(data['conflict_dates'], key=lambda x: x['date']),
            'severity': 'critical' if data['total_overlaps'] >= 5 else 'high' if data['total_overlaps'] >= 3 else 'medium'
        })
    
    # Sort by total_overlaps descending
    grouped_list.sort(key=lambda x: x['total_overlaps'], reverse=True)
    
    # Get top 10 critical rooms
    top_critical = grouped_list[:10]
    
    return {
        'total_conflict_count': total_conflicts,
        'affected_rooms': len(grouped_list),
        'top_critical_rooms': top_critical,
        'all_conflicts': grouped_list,
        'summary': {
            'critical': len([r for r in grouped_list if r['severity'] == 'critical']),
            'high': len([r for r in grouped_list if r['severity'] == 'high']),
            'medium': len([r for r in grouped_list if r['severity'] == 'medium'])
        }
    }



@router.post("/deluxe/optimize-channel-mix")
async def optimize_channel_mix(
    request: ChannelMixRequest,
    current_user: User = Depends(get_current_user)
):
    """Simulate optimal OTA vs Direct channel mix"""
    try:
        start = datetime.fromisoformat(request.start_date).date()
        end = datetime.fromisoformat(request.end_date).date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
    
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be before end_date.")
    
    # Get historical bookings
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}
    }, {'_id': 0}).to_list(10000)
    
    # Calculate current mix
    current_mix = {}
    total_revenue = 0
    total_commission = 0
    
    for booking in bookings:
        channel = booking.get('ota_channel') or 'direct'
        amount = booking.get('total_amount', 0)
        commission_pct = booking.get('commission_pct', 0)
        
        if channel not in current_mix:
            current_mix[channel] = {
                'bookings': 0,
                'revenue': 0,
                'commission_cost': 0
            }
        
        current_mix[channel]['bookings'] += 1
        current_mix[channel]['revenue'] += amount
        
        if commission_pct > 0:
            commission = amount * (commission_pct / 100)
            current_mix[channel]['commission_cost'] += commission
            total_commission += commission
        
        total_revenue += amount
    
    # Calculate percentages
    for channel, data in current_mix.items():
        data['revenue_pct'] = round((data['revenue'] / total_revenue * 100) if total_revenue > 0 else 0, 1)
        data['booking_pct'] = round((data['bookings'] / len(bookings) * 100) if bookings else 0, 1)
    
    # AI Optimal Mix Recommendation
    optimal_mix = {
        'direct': {'target_pct': 40, 'reason': 'Zero commission, highest margin'},
        'booking_com': {'target_pct': 25, 'reason': 'High volume, acceptable commission'},
        'expedia': {'target_pct': 20, 'reason': 'Good conversion, premium segment'},
        'airbnb': {'target_pct': 10, 'reason': 'Alternative segment, unique guests'},
        'other': {'target_pct': 5, 'reason': 'Diversification'}
    }
    
    # Calculate potential savings with optimal mix
    current_commission_rate = (total_commission / total_revenue * 100) if total_revenue > 0 else 0
    optimal_commission_rate = 12  # Industry benchmark
    potential_savings = (current_commission_rate - optimal_commission_rate) * total_revenue / 100
    
    return {
        'period': {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'current_mix': current_mix,
        'optimal_mix': optimal_mix,
        'analysis': {
            'total_bookings': len(bookings),
            'total_revenue': round(total_revenue, 2),
            'current_commission_cost': round(total_commission, 2),
            'current_commission_rate': round(current_commission_rate, 1),
            'optimal_commission_rate': optimal_commission_rate,
            'potential_annual_savings': round(potential_savings * 12, 2),
            'direct_booking_gap': round(40 - current_mix.get('direct', {}).get('revenue_pct', 0), 1)
        },
        'recommendations': [
            "Increase direct bookings through better website conversion",
            "Offer rate parity + perks for direct (free wifi, late checkout)",
            "Reduce dependency on high-commission OTAs",
            "Implement direct booking loyalty rewards program"
        ]
    }


@router.get("/calendar/rate-codes")
async def get_rate_codes(current_user: User = Depends(get_current_user)):
    """Get all rate codes"""
    rate_codes = await db.rate_codes.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)
    
    # Default rate codes if none exist
    if not rate_codes:
        default_codes = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'RO',
                'name': 'Room Only',
                'description': 'Room only, no meals included',
                'includes_breakfast': False,
                'includes_lunch': False,
                'includes_dinner': False,
                'is_refundable': True,
                'cancellation_policy': 'Free cancellation up to 24h before arrival',
                'price_modifier': 1.0
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'BB',
                'name': 'Bed & Breakfast',
                'description': 'Room with breakfast included',
                'includes_breakfast': True,
                'includes_lunch': False,
                'includes_dinner': False,
                'is_refundable': True,
                'cancellation_policy': 'Free cancellation up to 48h before arrival',
                'price_modifier': 1.15
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'HB',
                'name': 'Half Board',
                'description': 'Room with breakfast and dinner',
                'includes_breakfast': True,
                'includes_lunch': False,
                'includes_dinner': True,
                'is_refundable': True,
                'cancellation_policy': 'Free cancellation up to 72h before arrival',
                'price_modifier': 1.30
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'FB',
                'name': 'Full Board',
                'description': 'Room with all meals (breakfast, lunch, dinner)',
                'includes_breakfast': True,
                'includes_lunch': True,
                'includes_dinner': True,
                'is_refundable': True,
                'cancellation_policy': 'Free cancellation up to 72h before arrival',
                'price_modifier': 1.45
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'AI',
                'name': 'All Inclusive',
                'description': 'All meals and drinks included',
                'includes_breakfast': True,
                'includes_lunch': True,
                'includes_dinner': True,
                'is_refundable': True,
                'cancellation_policy': 'Free cancellation up to 7 days before arrival',
                'price_modifier': 1.75
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'code': 'NR',
                'name': 'Non-Refundable',
                'description': 'Best price, non-refundable rate',
                'includes_breakfast': False,
                'includes_lunch': False,
                'includes_dinner': False,
                'is_refundable': False,
                'cancellation_policy': 'Non-refundable - no cancellation allowed',
                'price_modifier': 0.85
            }
        ]
        rate_codes = default_codes
    
    return {'rate_codes': rate_codes, 'count': len(rate_codes)}



@router.post("/calendar/rate-codes")
async def create_rate_code(
    request: CreateRateCodeRequest,
    current_user: User = Depends(get_current_user)
):
    """Create custom rate code"""
    rate_code = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'code': request.code.upper(),
        'name': request.name,
        'description': request.description,
        'includes_breakfast': request.includes_breakfast,
        'includes_lunch': request.includes_lunch,
        'includes_dinner': request.includes_dinner,
        'is_refundable': request.is_refundable,
        'cancellation_policy': request.cancellation_policy,
        'price_modifier': request.price_modifier,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    rate_copy = rate_code.copy()
    await db.rate_codes.insert_one(rate_copy)
    return rate_code


# 2. ENHANCED CALENDAR TOOLTIP DATA


@router.post("/calendar/tooltip")
async def get_calendar_tooltip(
    request: GetCalendarTooltipRequest,
    current_user: User = Depends(get_current_user)
):
    """Get enriched data for calendar tooltip hover"""
    date = request.date
    room_type_filter = request.room_type
    
    # Get bookings for this date
    bookings_query = {
        'tenant_id': current_user.tenant_id,
        'check_in_date': {'$lte': date},
        'check_out_date': {'$gt': date},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }
    
    if room_type_filter:
        bookings_query['room_type'] = room_type_filter
    
    bookings = await db.bookings.find(bookings_query, {'_id': 0}).to_list(1000)
    
    # Get total rooms
    rooms_query = {'tenant_id': current_user.tenant_id}
    if room_type_filter:
        rooms_query['room_type'] = room_type_filter
    
    total_rooms = await db.rooms.count_documents(rooms_query)
    occupied_rooms = len(bookings)
    occupancy_pct = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
    
    # Calculate revenue for the day
    folio_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'charge_date': date,
        'voided': False
    }, {'_id': 0}).to_list(1000)
    
    total_revenue = sum(charge.get('total', 0) for charge in folio_charges)
    adr = (total_revenue / occupied_rooms) if occupied_rooms > 0 else 0
    
    # Segment breakdown
    segment_counts = {}
    for booking in bookings:
        segment = booking.get('booking_source', 'direct')
        segment_counts[segment] = segment_counts.get(segment, 0) + 1
    
    # Rate code breakdown
    rate_code_counts = {}
    rate_code_revenue = {}
    for booking in bookings:
        rate_code = booking.get('rate_code', 'BB')
        rate_code_counts[rate_code] = rate_code_counts.get(rate_code, 0) + 1
        
        # Get booking rate
        booking_charges = [c for c in folio_charges if c.get('booking_id') == booking.get('id')]
        if booking_charges:
            rate_code_revenue[rate_code] = rate_code_revenue.get(rate_code, 0) + sum(c.get('total', 0) for c in booking_charges)
    
    # Room type breakdown (if no filter)
    room_type_occupancy = {}
    if not room_type_filter:
        room_types = await db.room_types.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
        for rt in room_types:
            rt_bookings = [b for b in bookings if b.get('room_type') == rt['name']]
            rt_total = await db.rooms.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_type': rt['name']
            })
            rt_occ = (len(rt_bookings) / rt_total * 100) if rt_total > 0 else 0
            room_type_occupancy[rt['name']] = {
                'occupied': len(rt_bookings),
                'total': rt_total,
                'occupancy_pct': round(rt_occ, 1)
            }
    
    # Group reservations for this date
    group_bookings = [b for b in bookings if b.get('group_id')]
    group_ids = list(set([b['group_id'] for b in group_bookings if b.get('group_id')]))
    
    groups_info = []
    for group_id in group_ids:
        group = await db.group_reservations.find_one({'id': group_id}, {'_id': 0})
        if group:
            group_rooms = len([b for b in group_bookings if b.get('group_id') == group_id])
            groups_info.append({
                'group_name': group.get('group_name'),
                'total_rooms': group.get('total_rooms'),
                'rooms_today': group_rooms
            })
    
    return {
        'date': date,
        'occupancy': {
            'occupied_rooms': occupied_rooms,
            'total_rooms': total_rooms,
            'occupancy_pct': round(occupancy_pct, 1),
            'available_rooms': total_rooms - occupied_rooms
        },
        'revenue': {
            'total_revenue': round(total_revenue, 2),
            'adr': round(adr, 2),
            'revpar': round((total_revenue / total_rooms), 2) if total_rooms > 0 else 0
        },
        'segments': segment_counts,
        'rate_codes': {
            'breakdown': rate_code_counts,
            'revenue_by_code': {k: round(v, 2) for k, v in rate_code_revenue.items()}
        },
        'room_types': room_type_occupancy,
        'groups': {
            'count': len(groups_info),
            'details': groups_info
        }
    }


# 3. GROUP RESERVATION CALENDAR VIEW


@router.get("/calendar/group-view")
async def get_calendar_group_view(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Get calendar view optimized for group reservations"""
    # Get all group reservations that overlap with date range
    groups = await db.group_reservations.find({
        'tenant_id': current_user.tenant_id,
        'check_in_date': {'$lte': end_date},
        'check_out_date': {'$gte': start_date}
    }, {'_id': 0}).to_list(100)
    
    calendar_data = []
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1
    
    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()
        
        # Get groups active on this date
        active_groups = []
        for group in groups:
            if group.get('check_in_date') <= current_date <= group.get('check_out_date'):
                # Get bookings for this group on this date
                group_bookings = await db.bookings.find({
                    'tenant_id': current_user.tenant_id,
                    'group_id': group['id'],
                    'check_in_date': {'$lte': current_date},
                    'check_out_date': {'$gt': current_date}
                }, {'_id': 0}).to_list(1000)
                
                active_groups.append({
                    'group_id': group['id'],
                    'group_name': group.get('group_name'),
                    'group_type': group.get('group_type'),
                    'total_rooms': group.get('total_rooms'),
                    'rooms_active_today': len(group_bookings),
                    'contact_person': group.get('contact_person')
                })
        
        # Get regular (non-group) bookings
        regular_bookings = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in_date': {'$lte': current_date},
            'check_out_date': {'$gt': current_date},
            'group_id': None,
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        })
        
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        group_rooms = sum(g['rooms_active_today'] for g in active_groups)
        
        calendar_data.append({
            'date': current_date,
            'total_rooms': total_rooms,
            'group_rooms': group_rooms,
            'regular_rooms': regular_bookings,
            'available_rooms': total_rooms - group_rooms - regular_bookings,
            'groups': active_groups
        })
    
    return {
        'calendar': calendar_data,
        'summary': {
            'total_days': days,
            'total_groups': len(groups),
            'date_range': f"{start_date} to {end_date}"
        }
    }



@router.get("/calendar/rate-code-breakdown")
async def get_rate_code_breakdown(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Get rate code breakdown for date range"""
    # Get all bookings in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in_date': {'$lte': end_date},
        'check_out_date': {'$gte': start_date},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }, {'_id': 0}).to_list(10000)
    
    # Get rate codes
    rate_codes = await db.rate_codes.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    rate_code_map = {rc['code']: rc['name'] for rc in rate_codes}
    
    # Aggregate by date and rate code
    breakdown_by_date = {}
    
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1
    
    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()
        
        # Get bookings for this date
        date_bookings = [
            b for b in bookings
            if b.get('check_in_date') <= current_date < b.get('check_out_date')
        ]
        
        # Count by rate code
        rate_counts = {}
        for booking in date_bookings:
            rate_code = booking.get('rate_code', 'BB')
            rate_counts[rate_code] = rate_counts.get(rate_code, 0) + 1
        
        breakdown_by_date[current_date] = {
            'date': current_date,
            'total_bookings': len(date_bookings),
            'rate_codes': [
                {
                    'code': code,
                    'name': rate_code_map.get(code, code),
                    'count': count,
                    'percentage': round((count / len(date_bookings) * 100), 1) if date_bookings else 0
                }
                for code, count in rate_counts.items()
            ]
        }
    
    # Overall summary
    total_rate_counts = {}
    for booking in bookings:
        rate_code = booking.get('rate_code', 'BB')
        total_rate_counts[rate_code] = total_rate_counts.get(rate_code, 0) + 1
    
    return {
        'breakdown': list(breakdown_by_date.values()),
        'summary': {
            'date_range': f"{start_date} to {end_date}",
            'total_bookings': len(bookings),
            'rate_code_distribution': [
                {
                    'code': code,
                    'name': rate_code_map.get(code, code),
                    'count': count,
                    'percentage': round((count / len(bookings) * 100), 1) if bookings else 0
                }
                for code, count in total_rate_counts.items()
            ]
        }
    }

