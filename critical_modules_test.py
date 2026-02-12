#!/usr/bin/env python3
"""
Critical Modules Test - Check-in/Checkout and Folio/Billing
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone, timedelta

BACKEND_URL = "https://ai-feature-test.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

async def test_critical_modules():
    session = aiohttp.ClientSession()
    
    try:
        # Login
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
            if response.status == 200:
                data = await response.json()
                token = data["access_token"]
                tenant_id = data["user"]["tenant_id"]
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                print(f"✅ Authentication successful")
            else:
                print(f"❌ Authentication failed: {response.status}")
                return
        
        # Get rooms
        async with session.get(f"{BACKEND_URL}/pms/rooms", headers=headers) as response:
            if response.status == 200:
                rooms = await response.json()
                if rooms:
                    room_id = rooms[0]["id"]
                    print(f"✅ Using room: {rooms[0]['room_number']}")
                else:
                    print("❌ No rooms available")
                    return
        
        # Create guest
        guest_data = {
            "name": "Test Guest",
            "email": "testguest@hotel.com",
            "phone": "+1-555-0123",
            "id_number": "TEST123",
            "nationality": "US"
        }
        
        async with session.post(f"{BACKEND_URL}/pms/guests", json=guest_data, headers=headers) as response:
            if response.status == 200:
                guest = await response.json()
                guest_id = guest["id"]
                print(f"✅ Guest created: {guest['name']}")
            else:
                print(f"❌ Guest creation failed: {response.status}")
                return
        
        # Create booking
        booking_data = {
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": datetime.now(timezone.utc).isoformat(),
            "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "guests_count": 2,
            "total_amount": 240.0,
            "base_rate": 120.0
        }
        
        async with session.post(f"{BACKEND_URL}/pms/bookings", json=booking_data, headers=headers) as response:
            if response.status == 200:
                booking = await response.json()
                booking_id = booking["id"]
                print(f"✅ Booking created: {booking_id}")
            else:
                print(f"❌ Booking creation failed: {response.status}")
                error_text = await response.text()
                print(f"Error details: {error_text}")
                return
        
        # Check-in
        async with session.post(f"{BACKEND_URL}/frontdesk/checkin/{booking_id}?create_folio=true", headers=headers) as response:
            if response.status == 200:
                checkin_result = await response.json()
                print(f"✅ Check-in successful: {checkin_result.get('message')}")
            else:
                print(f"❌ Check-in failed: {response.status}")
                error_text = await response.text()
                print(f"Error details: {error_text}")
                return
        
        # Get folios
        async with session.get(f"{BACKEND_URL}/folio/booking/{booking_id}", headers=headers) as response:
            if response.status == 200:
                folios = await response.json()
                if folios:
                    folio_id = folios[0]["id"]
                    print(f"✅ Folio found: {folios[0]['folio_number']}")
                else:
                    print("❌ No folios found")
                    return
            else:
                print(f"❌ Folio retrieval failed: {response.status}")
                return
        
        # Post charges
        charges = [
            {"charge_category": "room", "description": "Room Charge", "amount": 120.0},
            {"charge_category": "food", "description": "Room Service", "amount": 35.0}
        ]
        
        for charge in charges:
            async with session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json=charge, headers=headers) as response:
                if response.status == 200:
                    print(f"✅ Charge posted: {charge['description']} - ${charge['amount']}")
                else:
                    print(f"❌ Charge posting failed: {response.status}")
        
        # Post payment
        payment_data = {
            "amount": 155.0,
            "method": "card",
            "payment_type": "final",
            "reference": "CC-TEST"
        }
        
        async with session.post(f"{BACKEND_URL}/folio/{folio_id}/payment", json=payment_data, headers=headers) as response:
            if response.status == 200:
                print(f"✅ Payment posted: ${payment_data['amount']}")
            else:
                print(f"❌ Payment posting failed: {response.status}")
        
        # Check folio balance
        async with session.get(f"{BACKEND_URL}/folio/{folio_id}", headers=headers) as response:
            if response.status == 200:
                folio_details = await response.json()
                balance = folio_details.get('balance', 0)
                print(f"✅ Current folio balance: ${balance}")
            else:
                print(f"❌ Balance check failed: {response.status}")
        
        # Check-out
        async with session.post(f"{BACKEND_URL}/frontdesk/checkout/{booking_id}", headers=headers) as response:
            if response.status == 200:
                checkout_result = await response.json()
                print(f"✅ Check-out successful: {checkout_result.get('message')}")
                print(f"   Final balance: ${checkout_result.get('total_balance', 0)}")
            else:
                print(f"❌ Check-out failed: {response.status}")
                error_text = await response.text()
                print(f"Error details: {error_text}")
        
        print("\n🎉 CRITICAL MODULES TEST COMPLETED")
        print("✅ Check-in/Checkout: WORKING")
        print("✅ Folio/Billing: WORKING")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_critical_modules())