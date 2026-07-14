import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
import jwt
from core import database
from core.security import JWT_ALGORITHM, JWT_SECRET

async def main():
    db = database._raw_db
    
    booking_id = "test_booking_123"
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {
            "status": "inhouse", 
            "guest_name": "Test Guest",
            "room_number": "101"
        }},
        upsert=True
    )
    
    payload = {
        "booking_id": booking_id,
        "exp": datetime.now(timezone.utc).timestamp() + (3600 * 24)
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    print("\n" + "="*50)
    print("QR CODE DATA STRING (Bu metni kopyala):")
    print(token)
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
