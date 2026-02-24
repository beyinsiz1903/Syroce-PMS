#!/usr/bin/env python3
"""
Detailed CM ARI v2 Response Analysis
Get detailed response structure and sample data for reporting
"""

import requests
import json
from datetime import datetime

BASE_URL = "https://improvement-guide-1.preview.emergentagent.com/api"

def get_detailed_response():
    """Get detailed CM ARI v2 response for analysis"""
    
    # Use the API key from previous test
    api_key = "0plB4AncKNSP6ZoO_5z035I0pOEYuKvzxBBePwdaV1c"
    
    headers = {"X-API-Key": api_key}
    params = {
        "start_date": "2024-01-01",
        "end_date": "2024-01-07"
    }
    
    try:
        response = requests.get(
            f"{BASE_URL}/cm/ari/v2",
            headers=headers,
            params=params,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            print("🔍 DETAILED CM ARI V2 RESPONSE ANALYSIS")
            print("=" * 50)
            
            # Main response structure
            print(f"📊 Main Response:")
            print(f"   hotel_id: {data.get('hotel_id')}")
            print(f"   currency: {data.get('currency')}")
            print(f"   date_from: {data.get('date_from')}")
            print(f"   date_to: {data.get('date_to')}")
            print(f"   room_types count: {len(data.get('room_types', []))}")
            
            # Room types analysis
            room_types = data.get('room_types', [])
            print(f"\n🏨 Room Types Analysis:")
            for i, room_type in enumerate(room_types):
                print(f"   Room Type {i+1}:")
                print(f"     room_type_id: {room_type.get('room_type_id')}")
                print(f"     name: {room_type.get('name')}")
                print(f"     days count: {len(room_type.get('days', []))}")
                
                # Sample day analysis
                days = room_type.get('days', [])
                if days:
                    sample_day = days[0]
                    print(f"     Sample Day ({sample_day.get('date')}):")
                    print(f"       available: {sample_day.get('available')}")
                    print(f"       sold: {sample_day.get('sold')}")
                    
                    restrictions = sample_day.get('restrictions', {})
                    print(f"       restrictions:")
                    print(f"         stop_sell: {restrictions.get('stop_sell')}")
                    print(f"         min_stay: {restrictions.get('min_stay')}")
                    print(f"         cta: {restrictions.get('cta')}")
                    print(f"         ctd: {restrictions.get('ctd')}")
                    print(f"         max_stay: {restrictions.get('max_stay')}")
                    
                    rate = sample_day.get('rate', {})
                    print(f"       rate:")
                    print(f"         amount: {rate.get('amount')}")
                    print(f"         currency: {rate.get('currency')}")
                    print(f"         tax_included: {rate.get('tax_included')}")
                    print(f"         source: {rate.get('source')}")
                    print(f"         rate_plan_id: {rate.get('rate_plan_id')}")
                    print(f"         board_code: {rate.get('board_code')}")
            
            # JSON structure for reference
            print(f"\n📋 Complete JSON Response (first 1000 chars):")
            json_str = json.dumps(data, indent=2)
            print(json_str[:1000] + "..." if len(json_str) > 1000 else json_str)
            
            return True
        else:
            print(f"❌ Failed to get response: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False

if __name__ == "__main__":
    get_detailed_response()