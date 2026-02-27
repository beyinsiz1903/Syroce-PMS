#!/usr/bin/env python3
"""
AI Dashboard Briefing Endpoint Test
Tests ONLY the /api/ai/dashboard/briefing endpoint to validate response structure
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://pms-i18next-demo.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

def authenticate():
    """Authenticate and get JWT token"""
    print("🔐 Authenticating...")
    
    login_data = {
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            user = data.get('user', {})
            print(f"✅ Authentication successful - User: {user.get('name', 'Unknown')}")
            return token
        else:
            print(f"❌ Authentication failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None

def test_ai_briefing_endpoint(token):
    """Test the AI Dashboard Briefing endpoint"""
    print("\n🎯 Testing AI Dashboard Briefing Endpoint...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Test the endpoint
        response = requests.get(f"{BASE_URL}/ai/dashboard/briefing", headers=headers, timeout=15)
        
        print(f"📊 Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Validate required fields
            required_fields = [
                'briefing_date',
                'briefing_items', 
                'summary',
                'metrics',
                'generated_at'
            ]
            
            missing_fields = []
            for field in required_fields:
                if field not in data:
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"❌ Missing required fields: {missing_fields}")
                return False
            
            # Validate metrics structure
            metrics = data.get('metrics', {})
            required_metrics = [
                'occupancy_rate',
                'today_checkins',
                'today_checkouts', 
                'monthly_revenue'
            ]
            
            missing_metrics = []
            for metric in required_metrics:
                if metric not in metrics:
                    missing_metrics.append(metric)
            
            if missing_metrics:
                print(f"❌ Missing required metrics: {missing_metrics}")
                return False
            
            # Validate data types
            validation_errors = []
            
            # Check briefing_date is string in YYYY-MM-DD format
            briefing_date = data.get('briefing_date')
            if not isinstance(briefing_date, str):
                validation_errors.append("briefing_date should be string")
            else:
                try:
                    datetime.strptime(briefing_date, "%Y-%m-%d")
                except ValueError:
                    validation_errors.append("briefing_date should be YYYY-MM-DD format")
            
            # Check briefing_items is array
            briefing_items = data.get('briefing_items')
            if not isinstance(briefing_items, list):
                validation_errors.append("briefing_items should be array")
            
            # Check summary is string
            summary = data.get('summary')
            if not isinstance(summary, str):
                validation_errors.append("summary should be string")
            
            # Check generated_at is ISO timestamp string
            generated_at = data.get('generated_at')
            if not isinstance(generated_at, str):
                validation_errors.append("generated_at should be string")
            else:
                try:
                    datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
                except ValueError:
                    validation_errors.append("generated_at should be ISO timestamp")
            
            # Check metrics are numeric
            for metric_name, metric_value in metrics.items():
                if not isinstance(metric_value, (int, float)):
                    validation_errors.append(f"metrics.{metric_name} should be numeric, got {type(metric_value)}")
            
            if validation_errors:
                print(f"❌ Validation errors: {validation_errors}")
                return False
            
            # Print success details
            print("✅ AI Dashboard Briefing endpoint working correctly!")
            print(f"📅 Briefing Date: {briefing_date}")
            print(f"📝 Summary: {summary}")
            print(f"📊 Metrics:")
            print(f"   - Occupancy Rate: {metrics['occupancy_rate']}%")
            print(f"   - Today Check-ins: {metrics['today_checkins']}")
            print(f"   - Today Check-outs: {metrics['today_checkouts']}")
            print(f"   - Monthly Revenue: {metrics['monthly_revenue']}")
            print(f"📋 Briefing Items: {len(briefing_items)} items")
            print(f"⏰ Generated At: {generated_at}")
            
            # Show example response structure (redacted)
            print(f"\n📄 Example Response Structure:")
            example_response = {
                "briefing_date": briefing_date,
                "briefing_items": f"[{len(briefing_items)} items with priority, category, message, insight]",
                "summary": summary[:50] + "..." if len(summary) > 50 else summary,
                "metrics": {
                    "occupancy_rate": metrics['occupancy_rate'],
                    "today_checkins": metrics['today_checkins'], 
                    "today_checkouts": metrics['today_checkouts'],
                    "monthly_revenue": metrics['monthly_revenue']
                },
                "generated_at": generated_at
            }
            print(json.dumps(example_response, indent=2))
            
            return True
            
        else:
            print(f"❌ Endpoint failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def check_backend_logs():
    """Check backend logs for any errors"""
    print("\n📋 Checking backend logs...")
    try:
        import subprocess
        result = subprocess.run(
            ["tail", "-n", "20", "/var/log/supervisor/backend.out.log"],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            logs = result.stdout
            if "ERROR" in logs or "Exception" in logs or "500" in logs:
                print("⚠️ Found errors in backend logs:")
                print(logs)
            else:
                print("✅ No errors found in recent backend logs")
        else:
            print("⚠️ Could not read backend logs")
            
    except Exception as e:
        print(f"⚠️ Could not check logs: {e}")

def main():
    """Main test function"""
    print("🎯 AI Dashboard Briefing Endpoint Test")
    print("=" * 50)
    
    # Authenticate
    token = authenticate()
    if not token:
        print("❌ Cannot proceed without authentication")
        sys.exit(1)
    
    # Test the AI briefing endpoint
    success = test_ai_briefing_endpoint(token)
    
    # Check backend logs
    check_backend_logs()
    
    # Final result
    print("\n" + "=" * 50)
    if success:
        print("🎉 AI DASHBOARD BRIEFING TEST: PASSED")
        print("✅ All required fields present and properly typed")
        print("✅ Metrics are numeric (no NaN/undefined)")
        print("✅ Response structure matches frontend expectations")
    else:
        print("❌ AI DASHBOARD BRIEFING TEST: FAILED")
        print("❌ Issues found with response structure or data types")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()