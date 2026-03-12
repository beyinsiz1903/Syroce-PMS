"""
Runtime Test — Overbooking Simulation
Tests system behavior under simultaneous booking attempts for the same room.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any

from core.database import db


async def simulate_overbooking(tenant_id: str, room_id: str, num_attempts: int = 10) -> Dict[str, Any]:
    """
    Simulate N concurrent booking attempts for the same room on the same date.
    Expected: Only 1 booking should succeed; others should fail with conflict.
    """
    check_in = (date.today() + timedelta(days=30)).isoformat()
    check_out = (date.today() + timedelta(days=31)).isoformat()

    results = {"success": 0, "conflict": 0, "error": 0, "details": []}

    async def attempt_booking(attempt_id: int):
        booking_id = str(uuid.uuid4())
        try:
            # Check if room already has a booking for this date
            existing = await db.bookings.find_one({
                "tenant_id": tenant_id,
                "room_id": room_id,
                "check_in": check_in,
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            if existing:
                results["conflict"] += 1
                results["details"].append({"attempt": attempt_id, "status": "conflict", "existing_booking": existing.get("id")})
                return

            # Attempt to create booking
            booking = {
                "id": booking_id,
                "tenant_id": tenant_id,
                "room_id": room_id,
                "guest_id": f"test-guest-{attempt_id}",
                "check_in": check_in,
                "check_out": check_out,
                "status": "confirmed",
                "source": "overbooking_test",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.bookings.insert_one(booking)
            results["success"] += 1
            results["details"].append({"attempt": attempt_id, "status": "success", "booking_id": booking_id})
        except Exception as e:
            results["error"] += 1
            results["details"].append({"attempt": attempt_id, "status": "error", "error": str(e)})

    # Run all attempts concurrently
    tasks = [attempt_booking(i) for i in range(num_attempts)]
    await asyncio.gather(*tasks)

    # Cleanup test bookings
    await db.bookings.delete_many({"tenant_id": tenant_id, "source": "overbooking_test"})

    results["total_attempts"] = num_attempts
    results["test_passed"] = results["success"] <= 1
    results["message"] = (
        "PASS: At most 1 booking created" if results["success"] <= 1
        else f"FAIL: {results['success']} bookings created (expected ≤ 1)"
    )
    return results


async def run_test(tenant_id: str) -> Dict[str, Any]:
    """Entry point for the overbooking simulation test."""
    # Get a test room
    room = await db.rooms.find_one({"tenant_id": tenant_id}, {"_id": 0, "id": 1})
    if not room:
        return {"status": "skipped", "reason": "No rooms found for tenant"}

    return await simulate_overbooking(tenant_id, room["id"])
