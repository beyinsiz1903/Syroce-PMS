"""
Logging Service for Hotel PMS
Centralized logging for production monitoring
"""

import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class LogLevel(str, Enum):
    """Log severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    DEBUG = "debug"


class LogCategory(str, Enum):
    """Log categories"""
    ERROR = "error"
    NIGHT_AUDIT = "night_audit"
    OTA_SYNC = "ota_sync"
    RMS_PUBLISH = "rms_publish"
    MAINTENANCE_PREDICTION = "maintenance_prediction"
    ALERT = "alert"
    SYSTEM = "system"
    API = "api"
    AUTH = "auth"


class LoggingService:
    """Centralized logging service"""

    def __init__(self, db):
        self.db = db

    async def log_error(
        self,
        tenant_id: str,
        error_type: str,
        error_message: str,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        request_data: Optional[Dict] = None,
        stack_trace: Optional[str] = None,
        severity: LogLevel = LogLevel.ERROR,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Log an error

        Args:
            tenant_id: Tenant identifier
            error_type: Type of error (e.g., "ValidationError", "DatabaseError")
            error_message: Error message
            endpoint: API endpoint where error occurred
            user_id: User who triggered the error
            user_name: User name
            request_data: Request payload (sanitized)
            stack_trace: Full stack trace
            severity: Error severity
            metadata: Additional metadata

        Returns:
            Log ID
        """
        import uuid

        log_id = str(uuid.uuid4())

        log_entry = {
            'id': log_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.ERROR,
            'severity': severity,
            'error_type': error_type,
            'error_message': error_message,
            'endpoint': endpoint,
            'user_id': user_id,
            'user_name': user_name,
            'request_data': request_data,
            'stack_trace': stack_trace,
            'metadata': metadata or {},
            'resolved': False,
            'resolved_at': None,
            'resolved_by': None,
            'resolution_notes': None
        }

        await self.db.error_logs.insert_one(log_entry)

        # Also create an alert for critical errors
        if severity == LogLevel.CRITICAL:
            await self.create_alert(
                tenant_id=tenant_id,
                alert_type='critical_error',
                title=f'Critical Error: {error_type}',
                description=error_message,
                severity='critical',
                source_module=endpoint or 'system',
                metadata={'error_log_id': log_id}
            )

        return log_id

    async def log_night_audit(
        self,
        tenant_id: str,
        audit_date: str,
        user_id: str,
        user_name: str,
        status: str,  # started, completed, failed
        rooms_processed: int = 0,
        charges_posted: int = 0,
        total_amount: float = 0.0,
        duration_seconds: Optional[float] = None,
        errors: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Log night audit operation"""
        import uuid

        log_id = str(uuid.uuid4())

        log_entry = {
            'id': log_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.NIGHT_AUDIT,
            'audit_date': audit_date,
            'user_id': user_id,
            'user_name': user_name,
            'status': status,
            'rooms_processed': rooms_processed,
            'charges_posted': charges_posted,
            'total_amount': total_amount,
            'duration_seconds': duration_seconds,
            'errors': errors or [],
            'metadata': metadata or {}
        }

        await self.db.night_audit_logs.insert_one(log_entry)

        # Create alert if audit failed
        if status == 'failed':
            await self.create_alert(
                tenant_id=tenant_id,
                alert_type='night_audit_failed',
                title='Night Audit Failed',
                description=f'Night audit for {audit_date} failed. Check logs for details.',
                severity='high',
                source_module='night_audit',
                metadata={'log_id': log_id}
            )

        return log_id

    async def log_ota_sync(
        self,
        tenant_id: str,
        channel: str,  # booking_com, expedia, airbnb, etc.
        sync_type: str,  # rates, availability, reservations, inventory
        direction: str,  # push, pull, bidirectional
        status: str,  # started, completed, failed, partial
        records_synced: int = 0,
        records_failed: int = 0,
        duration_seconds: Optional[float] = None,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Log OTA channel sync operation"""
        import uuid

        log_id = str(uuid.uuid4())

        log_entry = {
            'id': log_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.OTA_SYNC,
            'channel': channel,
            'sync_type': sync_type,
            'direction': direction,
            'status': status,
            'records_synced': records_synced,
            'records_failed': records_failed,
            'duration_seconds': duration_seconds,
            'errors': errors or [],
            'warnings': warnings or [],
            'metadata': metadata or {}
        }

        await self.db.ota_sync_logs.insert_one(log_entry)

        # Create alert if sync failed
        if status == 'failed':
            await self.create_alert(
                tenant_id=tenant_id,
                alert_type='ota_sync_failed',
                title=f'OTA Sync Failed: {channel}',
                description=f'{sync_type} sync with {channel} failed. {len(errors or [])} errors detected.',
                severity='high',
                source_module='channel_manager',
                metadata={'log_id': log_id}
            )

        return log_id

    async def log_rms_publish(
        self,
        tenant_id: str,
        publish_type: str,  # rates, restrictions, inventory
        channels: List[str],
        room_types: List[str],
        date_range: Dict[str, str],
        status: str,  # started, completed, failed, partial
        records_published: int = 0,
        records_failed: int = 0,
        auto_published: bool = False,
        triggered_by: str = 'manual',  # manual, auto, ai_recommendation
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        errors: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Log RMS rate/restriction publishing"""
        import uuid

        log_id = str(uuid.uuid4())

        log_entry = {
            'id': log_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.RMS_PUBLISH,
            'publish_type': publish_type,
            'channels': channels,
            'room_types': room_types,
            'date_range': date_range,
            'status': status,
            'records_published': records_published,
            'records_failed': records_failed,
            'auto_published': auto_published,
            'triggered_by': triggered_by,
            'user_id': user_id,
            'user_name': user_name,
            'duration_seconds': duration_seconds,
            'errors': errors or [],
            'metadata': metadata or {}
        }

        await self.db.rms_publish_logs.insert_one(log_entry)

        # Create alert if publishing failed
        if status == 'failed':
            await self.create_alert(
                tenant_id=tenant_id,
                alert_type='rms_publish_failed',
                title='RMS Publishing Failed',
                description=f'{publish_type} publishing to {len(channels)} channels failed.',
                severity='high',
                source_module='rms',
                metadata={'log_id': log_id}
            )

        return log_id

    async def log_maintenance_prediction(
        self,
        tenant_id: str,
        prediction_type: str,  # failure_risk, days_until_failure, preventive_schedule
        prediction_result: str,  # low, medium, high risk
        equipment_id: Optional[str] = None,
        equipment_type: Optional[str] = None,
        room_id: Optional[str] = None,
        room_number: Optional[str] = None,
        confidence_score: float = 0.0,
        days_until_failure: Optional[int] = None,
        indicators: Optional[List[str]] = None,
        recommended_action: Optional[str] = None,
        auto_task_created: bool = False,
        task_id: Optional[str] = None,
        model_version: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Log predictive maintenance AI predictions"""
        import uuid

        log_id = str(uuid.uuid4())

        log_entry = {
            'id': log_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.MAINTENANCE_PREDICTION,
            'prediction_type': prediction_type,
            'equipment_id': equipment_id,
            'equipment_type': equipment_type,
            'room_id': room_id,
            'room_number': room_number,
            'prediction_result': prediction_result,
            'confidence_score': confidence_score,
            'days_until_failure': days_until_failure,
            'indicators': indicators or [],
            'recommended_action': recommended_action,
            'auto_task_created': auto_task_created,
            'task_id': task_id,
            'model_version': model_version,
            'metadata': metadata or {}
        }

        await self.db.maintenance_prediction_logs.insert_one(log_entry)

        # Create alert for high-risk predictions
        if prediction_result == 'high':
            await self.create_alert(
                tenant_id=tenant_id,
                alert_type='maintenance_high_risk',
                title=f'High Risk: {equipment_type or "Equipment"} in Room {room_number}',
                description=f'Predicted failure in {days_until_failure or "unknown"} days. {recommended_action or "Action required"}',
                severity='high',
                source_module='predictive_maintenance',
                metadata={'log_id': log_id}
            )

        return log_id

    async def create_alert(
        self,
        tenant_id: str,
        alert_type: str,
        title: str,
        description: str,
        severity: str = 'medium',  # low, medium, high, critical
        source_module: str = 'system',
        assigned_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Create an alert in alert center"""
        import uuid

        alert_id = str(uuid.uuid4())

        alert_entry = {
            'id': alert_id,
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'alert_type': alert_type,
            'title': title,
            'description': description,
            'severity': severity,
            'source_module': source_module,
            'status': 'unread',  # unread, read, acknowledged, resolved
            'assigned_to': assigned_to,
            'acknowledged_at': None,
            'acknowledged_by': None,
            'resolved_at': None,
            'resolved_by': None,
            'resolution_notes': None,
            'metadata': metadata or {}
        }

        # Insert into both alerts collection and alert_history
        await self.db.alerts.insert_one(alert_entry)
        await self.db.alert_history.insert_one(alert_entry)

        return alert_id

    async def log_api_request(
        self,
        tenant_id: str,
        endpoint: str,
        method: str,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        status_code: int = 200,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Log API request for monitoring"""
        log_entry = {
            'tenant_id': tenant_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'category': LogCategory.API,
            'endpoint': endpoint,
            'method': method,
            'user_id': user_id,
            'user_name': user_name,
            'status_code': status_code,
            'duration_ms': duration_ms,
            'error': error
        }

        # Only log slow requests (>2s) or errors to reduce storage
        if duration_ms and duration_ms > 2000 or status_code >= 400:
            await self.db.api_logs.insert_one(log_entry)


# Helper function to capture exception details
def format_exception(e: Exception) -> Dict[str, str]:
    """Format exception for logging"""
    return {
        'type': type(e).__name__,
        'message': str(e),
        'traceback': traceback.format_exc()
    }


# Singleton instance
_logging_service = None

def get_logging_service(db):
    """Get or create logging service instance"""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService(db)
    return _logging_service
