import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.hotel_pms
    res = await db.bookings.find_one({"booking_number": "RES-A20B6B"})
    if not res:
        res = await db.bookings.find_one({"id": "RES-A20B6B"})
    if not res:
        res = await db.bookings.find_one({"guest_name": "mehmet aydın"})
    if not res:
        print("Not found")
        return
    print(f"Total Amount: {res.get('total_amount')}")
    print(f"Is Complimentary: {res.get('is_complimentary')}")
    print(f"Status: {res.get('status')}")
    print(f"Base Rate: {res.get('base_rate')}")
    print(f"Check In: {res.get('check_in')}")

asyncio.run(main())
