import asyncio
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import client, init_db

async def run():
    print("Starting Occupancy Sync Script on PROD database...")
    await init_db()
    system_db = client["syroce_pms"]

    try:
        tenants = await system_db.tenants.find({}).to_list(1000)
    except Exception as e:
        print(f"Failed to query tenants: {e}")
        return

    fixed_rooms = 0
    
    for t in tenants:
        tenant_id = t["id"]
        
        # 1. Active bookings (checked_in) -> Dict mapping room_id -> booking_id
        bookings = await system_db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
            "is_active": {"$ne": False}
        }).to_list(10000)
        
        active_room_ids = {}
        for b in bookings:
            rid = b.get("room_id")
            if rid:
                active_room_ids[rid] = b.get("id")
        
        # 2. Check rooms against active bookings
        rooms = await system_db.rooms.find({"tenant_id": tenant_id}).to_list(10000)
        for r in rooms:
            rid = r.get("id")
            actual_status = r.get("status")
            expected_booking_id = active_room_ids.get(rid)

            if expected_booking_id:
                # Room must be marked as occupied
                if actual_status not in ["occupied", "cleaning", "maintenance"]:
                    print(f"[Tenant {tenant_id}] Room {r.get('room_number')} is '{actual_status}' but has active booking. Fixing to 'occupied'.")
                    await system_db.rooms.update_one(
                        {"_id": r["_id"]},
                        {"$set": {"status": "occupied", "current_booking_id": expected_booking_id}}
                    )
                    fixed_rooms += 1
            else:
                # Room must NOT be occupied unless dirty
                if actual_status == "occupied":
                    print(f"[Tenant {tenant_id}] Room {r.get('room_number')} is 'occupied' but has NO active booking. Fixing to 'dirty'.")
                    await system_db.rooms.update_one(
                        {"_id": r["_id"]},
                        {"$set": {"status": "dirty", "current_booking_id": None}}
                    )
                    fixed_rooms += 1

    print(f"Sync complete. Fixed {fixed_rooms} rooms total.")

if __name__ == "__main__":
    asyncio.run(run())
