#!/usr/bin/env python3
"""
Simple test to check the exact API responses for Reservation Calendar modules
"""

import requests
import json

def test_modules():
    base_url = "https://bug-fix-update.preview.emergentagent.com/api"
    
    # Login first
    print("🔐 Logging in...")
    login_response = requests.post(f"{base_url}/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        return
    
    token = login_response.json().get('access_token')
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print("✅ Login successful")
    
    # Test date ranges
    historical_params = {'start_date': '2024-01-01', 'end_date': '2024-02-15'}
    future_params = {'start_date': '2025-12-01', 'end_date': '2025-12-15'}
    
    print("\n📊 Testing PMS Bookings (historical)...")
    pms_response = requests.get(f"{base_url}/pms/bookings", params=historical_params, headers=headers)
    if pms_response.status_code == 200:
        bookings = pms_response.json()
        print(f"✅ PMS Bookings: {len(bookings)} bookings found")
    else:
        print(f"❌ PMS Bookings failed: {pms_response.status_code}")
    
    print("\n🛡️ Testing Deluxe Oversell Protection...")
    oversell_response = requests.get(f"{base_url}/deluxe/oversell-protection", params=historical_params, headers=headers)
    if oversell_response.status_code == 200:
        oversell_data = oversell_response.json()
        protection_map = oversell_data.get('protection_map', [])
        print(f"✅ Oversell Protection: {len(protection_map)} entries")
        print(f"   Sample data: {json.dumps(oversell_data, indent=2)[:500]}...")
    else:
        print(f"❌ Oversell Protection failed: {oversell_response.status_code}")
    
    print("\n🎯 Testing Deluxe Channel Mix (historical)...")
    channel_response = requests.post(f"{base_url}/deluxe/optimize-channel-mix", 
                                   json=historical_params, headers=headers)
    if channel_response.status_code == 200:
        channel_data = channel_response.json()
        print(f"✅ Channel Mix successful")
        print(f"   Full response: {json.dumps(channel_data, indent=2)}")
    else:
        print(f"❌ Channel Mix failed: {channel_response.status_code}")
        print(f"   Error: {channel_response.text}")
    
    print("\n🗺️ Testing Enterprise Availability Heatmap...")
    heatmap_response = requests.get(f"{base_url}/enterprise/availability-heatmap", 
                                  params=historical_params, headers=headers)
    if heatmap_response.status_code == 200:
        heatmap_data = heatmap_response.json()
        heatmap = heatmap_data.get('heatmap', [])
        print(f"✅ Availability Heatmap: {len(heatmap)} entries")
        print(f"   Sample data: {json.dumps(heatmap_data, indent=2)[:500]}...")
    else:
        print(f"❌ Availability Heatmap failed: {heatmap_response.status_code}")
    
    print("\n🎯 Testing Deluxe Channel Mix (future - should be 0)...")
    future_channel_response = requests.post(f"{base_url}/deluxe/optimize-channel-mix", 
                                          json=future_params, headers=headers)
    if future_channel_response.status_code == 200:
        future_channel_data = future_channel_response.json()
        analysis = future_channel_data.get('analysis', {})
        total_bookings = analysis.get('total_bookings', 0)
        print(f"✅ Future Channel Mix: {total_bookings} bookings (should be 0)")
        print(f"   Full response: {json.dumps(future_channel_data, indent=2)}")
    else:
        print(f"❌ Future Channel Mix failed: {future_channel_response.status_code}")

if __name__ == "__main__":
    test_modules()