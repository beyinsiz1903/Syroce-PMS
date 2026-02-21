#!/usr/bin/env python3
"""
Simple test to check backend connectivity and create test user
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone

# Use external URL as configured
BACKEND_URL = "https://perf-boost-37.preview.emergentagent.com/api"

async def test_backend():
    async with aiohttp.ClientSession() as session:
        # First try to register a test user
        print("🔧 Attempting to register test user...")
        
        register_data = {
            "property_name": "Test Hotel",
            "email": "admin@hoteltest.com",
            "password": "admin123",
            "name": "Test Admin",
            "phone": "+1234567890",
            "address": "123 Test Street",
            "location": "Test City"
        }
        
        try:
            async with session.post(f"{BACKEND_URL}/auth/register", json=register_data) as response:
                print(f"Register response: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print("✅ User registered successfully")
                    token = data["access_token"]
                    
                    # Test the logs dashboard endpoint
                    headers = {"Authorization": f"Bearer {token}"}
                    async with session.get(f"{BACKEND_URL}/logs/dashboard", headers=headers) as dash_response:
                        print(f"Dashboard response: {dash_response.status}")
                        if dash_response.status == 200:
                            dash_data = await dash_response.json()
                            print("✅ Dashboard endpoint working")
                            print(f"Dashboard keys: {list(dash_data.keys())}")
                        else:
                            print(f"❌ Dashboard failed: {dash_response.status}")
                            error_text = await dash_response.text()
                            print(f"Error: {error_text}")
                    
                elif response.status == 400:
                    # User might already exist, try login
                    print("⚠️ User might already exist, trying login...")
                    
                    login_data = {
                        "email": "admin@hoteltest.com",
                        "password": "admin123"
                    }
                    
                    async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as login_response:
                        print(f"Login response: {login_response.status}")
                        if login_response.status == 200:
                            data = await login_response.json()
                            print("✅ Login successful")
                            token = data["access_token"]
                            
                            # Test the logs dashboard endpoint
                            headers = {"Authorization": f"Bearer {token}"}
                            async with session.get(f"{BACKEND_URL}/logs/dashboard", headers=headers) as dash_response:
                                print(f"Dashboard response: {dash_response.status}")
                                if dash_response.status == 200:
                                    dash_data = await dash_response.json()
                                    print("✅ Dashboard endpoint working")
                                    print(f"Dashboard keys: {list(dash_data.keys())}")
                                else:
                                    print(f"❌ Dashboard failed: {dash_response.status}")
                                    error_text = await dash_response.text()
                                    print(f"Error: {error_text}")
                        else:
                            print(f"❌ Login failed: {login_response.status}")
                            error_text = await login_response.text()
                            print(f"Error: {error_text}")
                else:
                    print(f"❌ Registration failed: {response.status}")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    
        except Exception as e:
            print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_backend())