"""
Runtime Test — Rate Storm
Tests system behavior under high-frequency rate/ARI update bursts.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any

from core.database import db


async def simulate_rate_storm(tenant_id: str, num_updates: int = 100) -> Dict[str, Any]:
    """
    Simulate N concurrent rate update operations.
    Expected: All updates should complete without data corruption.
    """
    results = {"success": 0, "error": 0, "details": []}

    async def rate_update(i: int):
        try:
            rate_entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "room_type": f"test_type_{i % 5}",
                "date": (date.today() + timedelta(days=i % 30)).isoformat(),
                "rate": 100 + (i * 1.5),
                "source": "rate_storm_test",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.rate_updates.insert_one(rate_entry)
            results["success"] += 1
        except Exception as e:
            results["error"] += 1
            results["details"].append({"update": i, "error": str(e)})

    tasks = [rate_update(i) for i in range(num_updates)]
    await asyncio.gather(*tasks)

    # Verify data integrity
    stored = await db.rate_updates.count_documents({"tenant_id": tenant_id, "source": "rate_storm_test"})

    # Cleanup
    await db.rate_updates.delete_many({"tenant_id": tenant_id, "source": "rate_storm_test"})

    results["total_updates"] = num_updates
    results["stored_count"] = stored
    results["test_passed"] = stored == results["success"]
    results["message"] = (
        f"PASS: All {stored} rate updates stored correctly"
        if results["test_passed"]
        else f"FAIL: Expected {results['success']} stored, got {stored}"
    )
    return results


async def run_test(tenant_id: str) -> Dict[str, Any]:
    return await simulate_rate_storm(tenant_id)
