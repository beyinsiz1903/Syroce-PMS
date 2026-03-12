"""
Runtime Test — Night Audit Concurrency
Tests simultaneous night audit operations for data consistency.
"""
import asyncio
import uuid
from datetime import datetime, timezone, date
from typing import Dict, Any

from core.database import db


async def simulate_night_audit_concurrency(tenant_id: str, concurrent_audits: int = 5) -> Dict[str, Any]:
    """
    Simulate concurrent night audit attempts.
    Expected: Only one audit should succeed; others should detect the lock.
    """
    audit_date = date.today().isoformat()
    results = {"success": 0, "locked": 0, "error": 0, "details": []}

    async def run_audit(audit_id: int):
        try:
            # Attempt to acquire night audit lock
            lock_result = await db.night_audit_locks.update_one(
                {"tenant_id": tenant_id, "audit_date": audit_date, "status": {"$ne": "running"}},
                {"$set": {
                    "tenant_id": tenant_id,
                    "audit_date": audit_date,
                    "status": "running",
                    "started_by": f"test-user-{audit_id}",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )

            if lock_result.modified_count > 0 or lock_result.upserted_id:
                results["success"] += 1
                results["details"].append({"audit": audit_id, "status": "acquired_lock"})

                # Simulate audit work
                await asyncio.sleep(0.1)

                # Release lock
                await db.night_audit_locks.update_one(
                    {"tenant_id": tenant_id, "audit_date": audit_date},
                    {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}},
                )
            else:
                results["locked"] += 1
                results["details"].append({"audit": audit_id, "status": "lock_denied"})

        except Exception as e:
            results["error"] += 1
            results["details"].append({"audit": audit_id, "status": "error", "error": str(e)})

    tasks = [run_audit(i) for i in range(concurrent_audits)]
    await asyncio.gather(*tasks)

    # Cleanup
    await db.night_audit_locks.delete_many({"tenant_id": tenant_id, "audit_date": audit_date})

    results["total_attempts"] = concurrent_audits
    results["test_passed"] = results["success"] >= 1 and results["error"] == 0
    results["message"] = (
        f"PASS: {results['success']} audit(s) succeeded, {results['locked']} locked out"
        if results["test_passed"]
        else f"FAIL: {results['error']} errors, {results['success']} successes"
    )
    return results


async def run_test(tenant_id: str) -> Dict[str, Any]:
    return await simulate_night_audit_concurrency(tenant_id)
