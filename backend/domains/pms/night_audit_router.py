"""
PMS / Night Audit Domain Router
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
from models.schemas import User
from models.enums import UserRole

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Night Audit"])

@router.get("/audit-logs")
@cached(ttl=600, key_prefix="audit_logs")  # Cache for 10 min
async def get_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get audit logs with filters"""
    # Access control: admin + super_admin
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    query = {'tenant_id': current_user.tenant_id}
    
    if entity_type:
        query['entity_type'] = entity_type
    if entity_id:
        query['entity_id'] = entity_id
    if user_id:
        query['user_id'] = user_id
    if action:
        query['action'] = action
    
    if start_date and end_date:
        query['timestamp'] = {
            '$gte': datetime.fromisoformat(start_date).isoformat(),
            '$lte': datetime.fromisoformat(end_date).isoformat()
        }
    
    logs = await db.audit_logs.find(query, {'_id': 0}).sort('timestamp', -1).limit(limit).to_list(limit)
    
    return {
        'logs': logs,
        'count': len(logs),
        'filters_applied': {k: v for k, v in query.items() if k != 'tenant_id'}
    }



@router.get("/logs/errors")
async def get_error_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    severity: Optional[str] = None,
    endpoint: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get error logs with filtering
    - Filter by date range, severity, endpoint
    - Support pagination
    """
    query = {'tenant_id': current_user.tenant_id}
    
    # Date filtering
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter
    
    # Other filters
    if severity:
        query['severity'] = severity
    if endpoint:
        query['endpoint'] = {'$regex': endpoint, '$options': 'i'}
    if resolved is not None:
        query['resolved'] = resolved
    
    # Get logs
    logs = []
    async for log in db.error_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        logs.append(log)
    
    total_count = await db.error_logs.count_documents(query)
    
    # Stats
    severity_stats = {}
    async for doc in db.error_logs.aggregate([
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {'_id': '$severity', 'count': {'$sum': 1}}}
    ]):
        severity_stats[doc['_id']] = doc['count']
    
    return {
        'logs': logs,
        'total_count': total_count,
        'returned_count': len(logs),
        'skip': skip,
        'limit': limit,
        'severity_stats': severity_stats
    }




@router.post("/logs/errors/{error_id}/resolve")
async def resolve_error_log(
    error_id: str,
    resolution_notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Mark error log as resolved"""
    result = await db.error_logs.update_one(
        {
            'id': error_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'resolved': True,
                'resolved_at': datetime.now(timezone.utc).isoformat(),
                'resolved_by': current_user.id,
                'resolution_notes': resolution_notes
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Error log not found")
    
    return {
        'success': True,
        'message': 'Error log marked as resolved'
    }




@router.get("/logs/night-audit")
async def get_night_audit_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get night audit logs
    - Filter by date range, status
    - Includes success rate, total charges posted
    """
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['audit_date'] = date_filter
    
    if status:
        query['status'] = status
    
    logs = []
    async for log in db.night_audit_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        logs.append(log)
    
    total_count = await db.night_audit_logs.count_documents(query)
    
    # Calculate stats
    stats = {
        'total_audits': total_count,
        'successful': 0,
        'failed': 0,
        'total_charges': 0.0,
        'total_rooms': 0
    }
    
    async for log in db.night_audit_logs.find({'tenant_id': current_user.tenant_id}):
        if log.get('status') == 'completed':
            stats['successful'] += 1
        elif log.get('status') == 'failed':
            stats['failed'] += 1
        stats['total_charges'] += log.get('total_amount', 0)
        stats['total_rooms'] += log.get('rooms_processed', 0)
    
    if stats['total_audits'] > 0:
        stats['success_rate'] = round(stats['successful'] / stats['total_audits'] * 100, 1)
    else:
        stats['success_rate'] = 0
    
    return {
        'logs': logs,
        'total_count': total_count,
        'returned_count': len(logs),
        'skip': skip,
        'limit': limit,
        'stats': stats
    }




@router.get("/logs/ota-sync")
async def get_ota_sync_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channel: Optional[str] = None,
    sync_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get OTA sync logs
    - Filter by date, channel, sync type, status
    - Includes success rate per channel
    """
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter
    
    if channel:
        query['channel'] = channel
    if sync_type:
        query['sync_type'] = sync_type
    if status:
        query['status'] = status
    
    logs = []
    async for log in db.ota_sync_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        logs.append(log)
    
    total_count = await db.ota_sync_logs.count_documents(query)
    
    # Channel stats
    channel_stats = {}
    async for doc in db.ota_sync_logs.aggregate([
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {
            '_id': '$channel',
            'total': {'$sum': 1},
            'successful': {
                '$sum': {'$cond': [{'$eq': ['$status', 'completed']}, 1, 0]}
            },
            'failed': {
                '$sum': {'$cond': [{'$eq': ['$status', 'failed']}, 1, 0]}
            },
            'records_synced': {'$sum': '$records_synced'}
        }}
    ]):
        channel_name = doc['_id']
        channel_stats[channel_name] = {
            'total_syncs': doc['total'],
            'successful': doc['successful'],
            'failed': doc['failed'],
            'success_rate': round(doc['successful'] / doc['total'] * 100, 1) if doc['total'] > 0 else 0,
            'records_synced': doc['records_synced']
        }
    
    return {
        'logs': logs,
        'total_count': total_count,
        'returned_count': len(logs),
        'skip': skip,
        'limit': limit,
        'channel_stats': channel_stats
    }




@router.get("/logs/rms-publish")
async def get_rms_publish_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    publish_type: Optional[str] = None,
    auto_published: Optional[bool] = None,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get RMS publish logs
    - Filter by date, publish type, auto/manual, status
    - Includes automation rate
    """
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter
    
    if publish_type:
        query['publish_type'] = publish_type
    if auto_published is not None:
        query['auto_published'] = auto_published
    if status:
        query['status'] = status
    
    logs = []
    async for log in db.rms_publish_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        logs.append(log)
    
    total_count = await db.rms_publish_logs.count_documents(query)
    
    # Calculate stats
    stats = {
        'total_publishes': total_count,
        'auto_publishes': 0,
        'manual_publishes': 0,
        'successful': 0,
        'failed': 0,
        'total_records': 0
    }
    
    async for log in db.rms_publish_logs.find({'tenant_id': current_user.tenant_id}):
        if log.get('auto_published'):
            stats['auto_publishes'] += 1
        else:
            stats['manual_publishes'] += 1
        
        if log.get('status') == 'completed':
            stats['successful'] += 1

# ============= TENANT ADMIN ENDPOINTS (HOTEL MODULE MANAGEMENT) =============



@router.get("/logs/maintenance-predictions")
async def get_maintenance_prediction_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    equipment_type: Optional[str] = None,
    prediction_result: Optional[str] = None,
    room_number: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get maintenance prediction logs
    - Filter by date, equipment type, risk level
    - Includes accuracy metrics
    """
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter
    
    if equipment_type:
        query['equipment_type'] = equipment_type
    if prediction_result:
        query['prediction_result'] = prediction_result
    if room_number:
        query['room_number'] = room_number
    
    logs = []
    async for log in db.maintenance_prediction_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        logs.append(log)
    
    total_count = await db.maintenance_prediction_logs.count_documents(query)
    
    # Risk distribution
    risk_stats = {}
    async for doc in db.maintenance_prediction_logs.aggregate([
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {
            '_id': '$prediction_result',
            'count': {'$sum': 1},
            'avg_confidence': {'$avg': '$confidence_score'},
            'tasks_created': {
                '$sum': {'$cond': ['$auto_task_created', 1, 0]}
            }
        }}
    ]):
        risk_level = doc['_id']
        risk_stats[risk_level] = {
            'count': doc['count'],
            'avg_confidence': round(doc['avg_confidence'], 3),
            'tasks_created': doc['tasks_created']
        }
    
    return {
        'logs': logs,
        'total_count': total_count,
        'returned_count': len(logs),
        'skip': skip,
        'limit': limit,
        'risk_stats': risk_stats
    }


# ============= SUBSCRIPTION & PRICING ENDPOINTS =============


