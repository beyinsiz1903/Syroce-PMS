#!/usr/bin/env python3
"""
Detailed Response Structure Verification for Ops Events API
===========================================================

This script examines the actual response structures to ensure they match
the expected format specified in the review request.
"""
import asyncio
import json
from datetime import datetime

import aiohttp


async def examine_response_structures():
    """Examine actual response structures from the API"""
    base_url = "https://ops-resilience-gaps.preview.emergentagent.com"
    api_base = f"{base_url}/api"
    
    # Authenticate first
    login_data = {"email": "demo@hotel.com", "password": "demo123"}
    
    async with aiohttp.ClientSession() as session:
        # Get auth token
        async with session.post(f"{api_base}/auth/login", json=login_data) as response:
            if response.status != 200:
                print("❌ Authentication failed")
                return
            
            auth_data = await response.json()
            token = auth_data.get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
        
        print("🔍 EXAMINING RESPONSE STRUCTURES")
        print("=" * 50)
        
        # Test each endpoint and show structure
        endpoints_to_examine = [
            ("/ops-events/list", "Ops Events List"),
            ("/ops-events/webhook-deliveries", "Webhook Deliveries"),
            ("/ops-events/webhook-dlq", "Webhook DLQ"),
            ("/ops-events/rate-limit-status", "Rate Limit Status"),
            ("/ops-events/channel-health", "Channel Health"),
            ("/ops-events/dashboard-summary", "Dashboard Summary"),
        ]
        
        for endpoint, name in endpoints_to_examine:
            print(f"\n📋 {name} ({endpoint})")
            print("-" * 40)
            
            try:
                async with session.get(f"{api_base}{endpoint}", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Show top-level structure
                        print("Top-level fields:")
                        for key in data.keys():
                            value = data[key]
                            if isinstance(value, list):
                                print(f"  • {key}: array[{len(value)}]")
                                if len(value) > 0:
                                    print(f"    Sample item keys: {list(value[0].keys()) if isinstance(value[0], dict) else type(value[0]).__name__}")
                            elif isinstance(value, dict):
                                print(f"  • {key}: object")
                                print(f"    Keys: {list(value.keys())}")
                            else:
                                print(f"  • {key}: {type(value).__name__} = {value}")
                        
                        # Show sample data for verification
                        if endpoint == "/ops-events/dashboard-summary":
                            print("\n🎯 Dashboard Summary Structure Verification:")
                            webhook_delivery = data.get("webhook_delivery", {})
                            print(f"  webhook_delivery keys: {list(webhook_delivery.keys())}")
                            
                            rate_limit = data.get("rate_limit", {})
                            print(f"  rate_limit keys: {list(rate_limit.keys())}")
                            
                            channels = data.get("channels", [])
                            print(f"  channels: {len(channels)} items")
                            if channels:
                                print(f"  channel sample keys: {list(channels[0].keys())}")
                    else:
                        print(f"❌ Error {response.status}: {await response.text()}")
                        
            except Exception as e:
                print(f"❌ Exception: {e}")


if __name__ == "__main__":
    asyncio.run(examine_response_structures())