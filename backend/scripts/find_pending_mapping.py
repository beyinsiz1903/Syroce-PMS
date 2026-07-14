import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import _raw_db

async def main():
    print("Searching for pending mapping reservations in CM collections...")
    
    cols = await _raw_db.list_collection_names()
    
    target_cols = [c for c in cols if 'channel' in c or 'cm_' in c or 'ota_' in c or 'hotelrunner' in c]
    for col in target_cols:
        cursor = _raw_db[col].find({"pms_status": "pending_mapping"})
        docs = await cursor.to_list(length=10)
        if docs:
            print(f"--- Found in {col} ---")
            for doc in docs:
                print(f"Tenant: {doc.get('tenant_id')}")
                print(f"Provider: {doc.get('provider')}")
                print(f"Channel Room Code: {doc.get('channel_room_code')}")
                print(f"Channel Rate Code: {doc.get('channel_rate_code')}")
                if 'rooms' in doc:
                    print(f"Rooms array: {doc['rooms']}")
                print("----------")

if __name__ == "__main__":
    asyncio.run(main())
