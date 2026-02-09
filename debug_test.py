#!/usr/bin/env python3
"""
Debug specific failing endpoints
"""

import requests
import json

# Configuration
BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

def authenticate():
    """Authenticate with the backend"""
    response = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if response.status_code == 200:
        data = response.json()
        return data["access_token"]
    else:
        print(f"Authentication failed: {response.status_code} - {response.text}")
        return None

def test_endpoint(token, method, endpoint, data=None):
    """Test a specific endpoint"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"\n🔍 Testing {method} {endpoint}")
    
    try:
        if method == "POST":
            response = requests.post(f"{BACKEND_URL}{endpoint}", json=data, headers=headers)
        else:
            response = requests.get(f"{BACKEND_URL}{endpoint}", headers=headers)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code >= 400:
            print(f"Error Response: {response.text}")
        else:
            try:
                result = response.json()
                print(f"Success: {json.dumps(result, indent=2)[:200]}...")
            except:
                print(f"Response: {response.text[:200]}...")
                
    except Exception as e:
        print(f"Exception: {str(e)}")

def main():
    token = authenticate()
    if not token:
        return
    
    # Test failing endpoints
    print("🧪 Testing failing endpoints...")
    
    # Messaging template
    test_endpoint(token, "POST", "/messaging/templates", {
        "name": "Welcome Template Test",
        "channel": "whatsapp",
        "content": "Welcome {{guest_name}} to our hotel! Your room {{room_number}} is ready.",
        "variables": ["guest_name", "room_number"]
    })
    
    # RMS comp-set
    test_endpoint(token, "POST", "/rms/comp-set", {
        "name": "Hilton Downtown Test",
        "location": "Downtown Business District",
        "star_rating": 4.5,
        "url": "https://hilton.com"
    })
    
    # Marketplace products (using correct field names for old Product model)
    test_endpoint(token, "POST", "/marketplace/products", {
        "name": "Bath Towels Premium",
        "category": "linens",
        "description": "High quality cotton bath towels",
        "price": 15.50,
        "unit": "piece",
        "supplier": "Linen Supply Co"
    })
    
    # POS transaction
    test_endpoint(token, "POST", "/pos/transaction", {
        "amount": 150.50,
        "payment_method": "card",
        "folio_id": None
    })
    
    # Group reservations
    test_endpoint(token, "POST", "/group-reservations", {
        "group_name": "Corporate Training Group Test",
        "group_type": "corporate",
        "contact_person": "John Smith",
        "contact_email": "john@company.com",
        "contact_phone": "+1234567890",
        "check_in_date": "2025-02-15",
        "check_out_date": "2025-02-17",
        "total_rooms": 10,
        "adults_per_room": 2,
        "special_requests": "Meeting room required"
    })

if __name__ == "__main__":
    main()