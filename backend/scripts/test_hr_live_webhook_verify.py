import asyncio
import sys
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

load_dotenv(override=False)
sys.path.append("/app")

async def main():
    print("==================================================")
    print("HOTELRUNNER LIVE WEBHOOK VERIFICATION REPORT")
    print("==================================================")

    from core import database
    db = database._raw_db

    # Check reservations created/modified in the last 2 hours from HR
    time_limit = datetime.now(UTC) - timedelta(hours=2)

    # We assume reservation model has fields like `hr_number` or `provider_reservation_id`
    # and `status` (created, modified, cancelled)
    query = {
        "channel": "hotelrunner",
        "updated_at": {"$gte": time_limit}
    }

    docs = await db.reservations.find(query).sort("updated_at", -1).to_list(20)

    if not docs:
        print("No recent HotelRunner reservations found in the DB.")
        print("Waiting for HR Extranet test reservation webhooks...")
        sys.exit(0)

    print(f"{'hr_number':<15} | {'pms_id':<24} | {'status':<10} | {'updated_at'}")
    print("-" * 75)
    for doc in docs:
        hr_num = doc.get("provider_reservation_id", doc.get("hr_number", "UNKNOWN"))
        pms_id = str(doc.get("_id"))
        status = doc.get("status", "N/A")
        upd = doc.get("updated_at")
        print(f"{hr_num:<15} | {pms_id:<24} | {status:<10} | {upd}")

    print("==================================================")
    print("If Create, Modify, and Cancel statuses are visible above, Phase B is PASS.")

if __name__ == "__main__":
    asyncio.run(main())
