import asyncio
import os
from datetime import datetime, UTC
from core.database import db
from core.atomic_checkin_checkout import check_in_booking_atomic

async def test():
    os.environ["MONGO_DISABLE_TRANSACTIONS"] = "1"
    booking = await db.bookings.find_one()
    if not booking:
        print("No booking found")
        return
    try:
        res = await check_in_booking_atomic(
            booking["id"],
            booking["tenant_id"],
            "test_user"
        )
        print("Result:", res)
    except Exception as e:
        print("Error:", repr(e))

asyncio.run(test())
