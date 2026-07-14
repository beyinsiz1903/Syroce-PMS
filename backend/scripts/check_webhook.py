import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.database import _raw_db

async def main():
    print("Checking raw_channel_events for R685254457...")
    docs = await _raw_db.raw_channel_events.find({"external_reservation_id": "R685254457"}).sort("received_at", 1).to_list(10)
    for d in docs:
        print(f"ID: {d.get('provider_event_id')} | Via: {d.get('received_via')} | Status: {d.get('processing_status')} | Time: {d.get('received_at')}")
        
    print("\nChecking latest webhook events globally...")
    docs = await _raw_db.raw_channel_events.find({"received_via": "webhook"}).sort("received_at", -1).to_list(5)
    for d in docs:
        print(f"ID: {d.get('provider_event_id')} | Time: {d.get('received_at')}")

asyncio.run(main())
