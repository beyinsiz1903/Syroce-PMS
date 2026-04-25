"""
HotelRunner Router — Sync Log Writer
=====================================

UI-facing sync history writer. Persists to `hotelrunner_sync_logs` collection
which the frontend Channel Manager page renders. Distinct from
`observability.py` which records provider-call HTTP metrics for monitoring.
"""
import uuid
from datetime import UTC, datetime

from core.database import db


async def log_sync(
    tenant_id: str,
    sync_type: str,
    status: str,
    duration_ms: int = 0,
    records: int = 0,
    error: str | None = None,
    user_name: str = "system",
) -> None:
    """Log a sync event for UI display."""
    await db.hotelrunner_sync_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "sync_type": sync_type,
        "status": status,
        "duration_ms": duration_ms,
        "records_synced": records,
        "error_message": error,
        "initiator": user_name,
    })
