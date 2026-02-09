#!/usr/bin/env python3
"""
Create test data for group bookings validation
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone, timedelta
import uuid

BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

async def create_test_data():
    async with aiohttp.ClientSession() as session:
        # Login
        login_data = {'email': TEST_EMAIL, 'password': TEST_PASSWORD}
        async with session.post(f'{BACKEND_URL}/auth/login', json=login_data) as response:
            if response.status == 200:
                data = await response.json()
                token = data['access_token']
                headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                
                print("✅ Authentication successful")
                
                # Create test companies
                companies = []
                company_names = ["Acme Corp", "Global Hotels Ltd", "Business Travel Inc"]
                
                for name in company_names:
                    company_data = {
                        "name": name,
                        "corporate_code": f"CORP{len(companies)+1:03d}",
                        "contact_person": f"Manager {len(companies)+1}",
                        "contact_email": f"manager{len(companies)+1}@{name.lower().replace(' ', '')}.com",
                        "contact_phone": f"+1-555-{1000+len(companies):04d}"
                    }
                    
                    async with session.post(f'{BACKEND_URL}/companies', json=company_data, headers=headers) as response:
                        if response.status == 200:
                            company = await response.json()
                            companies.append(company)
                            print(f"✅ Created company: {name} (ID: {company['id']})")
                        else:
                            print(f"❌ Failed to create company {name}: {response.status}")
                
                # Get available rooms
                async with session.get(f'{BACKEND_URL}/pms/rooms', headers=headers) as response:
                    if response.status == 200:
                        rooms = await response.json()
                        print(f"✅ Found {len(rooms)} rooms")
                    else:
                        print(f"❌ Failed to get rooms: {response.status}")
                        return
                
                # Create test guests and group bookings
                today = datetime.now(timezone.utc)
                
                for i, company in enumerate(companies):
                    # Create multiple guests for each company
                    for j in range(3):  # 3 guests per company
                        guest_data = {
                            "name": f"Guest {i+1}-{j+1}",
                            "email": f"guest{i+1}-{j+1}@{company['name'].lower().replace(' ', '')}.com",
                            "phone": f"+1-555-{2000+i*10+j:04d}",
                            "id_number": f"ID{i+1}{j+1:02d}",
                            "nationality": "US"
                        }
                        
                        async with session.post(f'{BACKEND_URL}/pms/guests', json=guest_data, headers=headers) as response:
                            if response.status == 200:
                                guest = await response.json()
                                
                                # Create booking for this guest
                                if j < len(rooms):
                                    room = rooms[j % len(rooms)]
                                    
                                    booking_data = {
                                        "guest_id": guest["id"],
                                        "room_id": room["id"],
                                        "check_in": (today + timedelta(days=i*7+j)).isoformat(),
                                        "check_out": (today + timedelta(days=i*7+j+2)).isoformat(),
                                        "adults": 2,
                                        "children": 0,
                                        "guests_count": 2,
                                        "total_amount": 300.0 + (i*50) + (j*25),
                                        "company_id": company["id"],
                                        "channel": "direct"
                                    }
                                    
                                    async with session.post(f'{BACKEND_URL}/pms/bookings', json=booking_data, headers=headers) as response:
                                        if response.status == 200:
                                            booking = await response.json()
                                            print(f"✅ Created booking for {guest['name']} at {company['name']}")
                                        else:
                                            error_text = await response.text()
                                            print(f"❌ Failed to create booking: {response.status} - {error_text[:100]}")
                            else:
                                print(f"❌ Failed to create guest: {response.status}")
                
                print("\n🎉 Test data creation completed!")
                
            else:
                print(f"❌ Authentication failed: {response.status}")

if __name__ == "__main__":
    asyncio.run(create_test_data())