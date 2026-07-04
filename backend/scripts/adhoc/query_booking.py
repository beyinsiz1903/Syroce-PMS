import asyncio

from core.database import db


async def main():
    booking = await db.bookings.find_one({"_id": "RES-347624"})
    if not booking:
        print("Booking not found")
        return
    print("Booking:", booking)
    folios = await db.folios.find({"booking_id": "RES-347624"}).to_list(10)
    print("Folios:", folios)
    charges = await db.folio_charges.find({"booking_id": "RES-347624"}).to_list(100)
    print("Folio charges:", charges)
    extra = await db.extra_charges.find({"booking_id": "RES-347624"}).to_list(100)
    print("Extra charges:", extra)

asyncio.run(main())
