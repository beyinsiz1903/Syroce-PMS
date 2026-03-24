"""
Night Audit — Pre-Run Validations
Validates system state before allowing night audit execution.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def validate_pre_audit(db, tenant_id: str, business_date: str) -> Dict[str, Any]:
    """Run pre-audit validations. Returns dict with pass/fail + blockers."""
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # 1. Check for in-progress housekeeping tasks on occupied rooms
    cleaning_in_progress = await db.housekeeping_tasks.count_documents({
        "tenant_id": tenant_id,
        "status": "in_progress",
    })
    if cleaning_in_progress > 0:
        warnings.append({
            "code": "HK_IN_PROGRESS",
            "message": f"{cleaning_in_progress} housekeeping tasks still in progress",
            "count": cleaning_in_progress,
        })

    # 2. Check for unposted POS transactions
    open_pos = await db.pos_transactions.count_documents({
        "tenant_id": tenant_id,
        "status": "open",
    })
    if open_pos > 0:
        warnings.append({
            "code": "OPEN_POS_TRANSACTIONS",
            "message": f"{open_pos} unposted POS transactions",
            "count": open_pos,
        })

    # 3. Check for checked-in guests with no room assignment
    orphan_checkins = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": "checked_in",
        "room_id": {"$in": [None, ""]},
    })
    if orphan_checkins > 0:
        blockers.append({
            "code": "ORPHAN_CHECKINS",
            "message": f"{orphan_checkins} checked-in bookings without room assignment",
            "count": orphan_checkins,
        })

    # 4. Check for concurrent audit already running
    running_audit = await db.night_audit_runs.find_one({
        "tenant_id": tenant_id,
        "status": "running",
    })
    if running_audit:
        blockers.append({
            "code": "AUDIT_ALREADY_RUNNING",
            "message": f"Night audit already running (id: {running_audit.get('id')})",
            "audit_id": running_audit.get("id"),
        })

    passed = len(blockers) == 0
    return {
        "passed": passed,
        "blockers": blockers,
        "warnings": warnings,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }
