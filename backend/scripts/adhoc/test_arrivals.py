import asyncio

from core.database import db
from core.tenant_db import set_tenant_context


async def main():
    set_tenant_context("tenant1")
    booking = await db.bookings.find_one({"status": {"$in": ["confirmed", "guaranteed"]}})
    if booking:
        print("Booking check_in format:", repr(booking.get("check_in")))
    else:
        print("No booking found")


if __name__ == "__main__":
    asyncio.run(main())
