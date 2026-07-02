import asyncio
from core.database import db
from core.tenant_context import set_tenant_context
from modules.pms_core.front_desk_service import FrontDeskService

async def main():
    set_tenant_context("tenant1")
    # find a booking that can be checked in
    booking = await db.bookings.find_one({"status": "confirmed"})
    if not booking:
        print("No booking found to check-in")
        return
    
    print(f"Checking in booking {booking['id']}")
    fd = FrontDeskService()
    try:
        res = await fd.check_in("tenant1", booking["id"], "user1", "Test User")
        print("Success:", res)
    except Exception as e:
        print("Exception:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
