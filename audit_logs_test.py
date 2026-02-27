#!/usr/bin/env python3
"""
AUDIT LOGS ENDPOINT PERMISSION TESTING
Test audit logs endpoint permission changes.

OBJECTIVE: Test audit logs endpoint permissions for different user roles

TARGET ENDPOINTS:
1. POST /api/auth/login - Login with different users
2. GET /api/auth/me - Get user role information
3. GET /api/audit-logs?limit=5 - Test audit logs access

TEST SCENARIOS:
1. Login as muratsutay@hotmail.com / murat1903 (role super_admin). Call GET /api/audit-logs?limit=5. Expect 200.
2. Login as demo@hotel.com / demo123 (likely admin or staff). Call GET /api/audit-logs?limit=5. If role is admin, expect 200; if not admin, expect 403.
3. If demo is not admin, create a quick admin user? Do NOT create unless required; instead just report role from /api/auth/me.

EXPECTED RESULTS:
- Super admin should have access (HTTP 200)
- Admin users should have access (HTTP 200)
- Non-admin users should be denied access (HTTP 403)
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Configuration
BACKEND_URL = "https://code-cleanup-135.preview.emergentagent.com/api"

class AuditLogsTester:
    def __init__(self):
        self.session = None
        self.test_results = []

    async def create_session(self):
        """Create HTTP session with proper headers"""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )

    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Login user and return auth info"""
        login_data = {
            "email": email,
            "password": password
        }
        
        print(f"\n🔐 Attempting login for: {email}")
        
        try:
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    auth_data = json.loads(response_text)
                    token = auth_data.get('access_token')
                    user = auth_data.get('user', {})
                    
                    print(f"✅ Login successful")
                    print(f"   User: {user.get('name', 'Unknown')}")
                    print(f"   Role: {user.get('role', 'Unknown')}")
                    print(f"   Email: {user.get('email', 'Unknown')}")
                    
                    return {
                        'success': True,
                        'token': token,
                        'user': user,
                        'response_time': response.headers.get('X-Response-Time', 'N/A')
                    }
                else:
                    print(f"❌ Login failed: HTTP {response.status}")
                    print(f"   Response: {response_text}")
                    return {
                        'success': False,
                        'status': response.status,
                        'error': response_text
                    }
                    
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information using /auth/me endpoint"""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        print(f"\n👤 Getting user info via /auth/me")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/auth/me", headers=headers) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    user_data = json.loads(response_text)
                    print(f"✅ User info retrieved successfully")
                    print(f"   Name: {user_data.get('name', 'Unknown')}")
                    print(f"   Role: {user_data.get('role', 'Unknown')}")
                    print(f"   Email: {user_data.get('email', 'Unknown')}")
                    print(f"   Tenant ID: {user_data.get('tenant_id', 'Unknown')}")
                    
                    return {
                        'success': True,
                        'user': user_data,
                        'response_time': response.headers.get('X-Response-Time', 'N/A')
                    }
                else:
                    print(f"❌ Failed to get user info: HTTP {response.status}")
                    print(f"   Response: {response_text}")
                    return {
                        'success': False,
                        'status': response.status,
                        'error': response_text
                    }
                    
        except Exception as e:
            print(f"❌ User info error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def test_audit_logs_access(self, token: str, user_role: str, user_email: str) -> Dict[str, Any]:
        """Test access to audit logs endpoint"""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        print(f"\n📋 Testing audit logs access for {user_role} ({user_email})")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/audit-logs?limit=5", headers=headers) as response:
                response_text = await response.text()
                
                print(f"   Status: HTTP {response.status}")
                print(f"   Response time: {response.headers.get('X-Response-Time', 'N/A')}")
                
                if response.status == 200:
                    try:
                        audit_data = json.loads(response_text)
                        audit_count = len(audit_data) if isinstance(audit_data, list) else len(audit_data.get('logs', []))
                        print(f"✅ Access granted - Retrieved {audit_count} audit log entries")
                        
                        # Show sample audit log structure if available
                        if isinstance(audit_data, list) and audit_data:
                            sample_log = audit_data[0]
                            print(f"   Sample log: {sample_log.get('action', 'N/A')} by {sample_log.get('user_name', 'N/A')} on {sample_log.get('entity_type', 'N/A')}")
                        elif isinstance(audit_data, dict) and audit_data.get('logs'):
                            sample_log = audit_data['logs'][0]
                            print(f"   Sample log: {sample_log.get('action', 'N/A')} by {sample_log.get('user_name', 'N/A')} on {sample_log.get('entity_type', 'N/A')}")
                        
                        return {
                            'success': True,
                            'status': response.status,
                            'audit_count': audit_count,
                            'response_time': response.headers.get('X-Response-Time', 'N/A'),
                            'data': audit_data
                        }
                    except json.JSONDecodeError:
                        print(f"✅ Access granted but response is not JSON: {response_text[:200]}...")
                        return {
                            'success': True,
                            'status': response.status,
                            'response_time': response.headers.get('X-Response-Time', 'N/A'),
                            'raw_response': response_text[:500]
                        }
                        
                elif response.status == 403:
                    print(f"❌ Access denied (403 Forbidden) - Expected for non-admin roles")
                    return {
                        'success': False,
                        'status': response.status,
                        'expected_denial': True,
                        'error': response_text,
                        'response_time': response.headers.get('X-Response-Time', 'N/A')
                    }
                    
                else:
                    print(f"❌ Unexpected response: HTTP {response.status}")
                    print(f"   Response: {response_text}")
                    return {
                        'success': False,
                        'status': response.status,
                        'error': response_text,
                        'response_time': response.headers.get('X-Response-Time', 'N/A')
                    }
                    
        except Exception as e:
            print(f"❌ Audit logs test error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def run_comprehensive_test(self):
        """Run comprehensive audit logs permission test"""
        print("🎯 AUDIT LOGS ENDPOINT PERMISSION TESTING")
        print("=" * 60)
        
        await self.create_session()
        
        # Test scenarios
        test_users = [
            {
                'email': 'muratsutay@hotmail.com',
                'password': 'murat1903',
                'expected_role': 'super_admin',
                'expected_access': True
            },
            {
                'email': 'demo@hotel.com',
                'password': 'demo123',
                'expected_role': 'admin',  # We'll verify this
                'expected_access': None  # Depends on actual role
            }
        ]
        
        overall_results = []
        
        for i, user_config in enumerate(test_users, 1):
            print(f"\n{'='*20} TEST SCENARIO {i} {'='*20}")
            
            # Step 1: Login
            login_result = await self.login_user(user_config['email'], user_config['password'])
            
            if not login_result['success']:
                print(f"❌ Cannot proceed with audit logs test - login failed")
                overall_results.append({
                    'user': user_config['email'],
                    'login_success': False,
                    'audit_access': None,
                    'error': login_result.get('error', 'Login failed')
                })
                continue
            
            token = login_result['token']
            user_data = login_result['user']
            actual_role = user_data.get('role', 'unknown')
            
            # Step 2: Verify user info via /auth/me
            user_info_result = await self.get_user_info(token)
            
            if user_info_result['success']:
                verified_role = user_info_result['user'].get('role', 'unknown')
                if verified_role != actual_role:
                    print(f"⚠️ Role mismatch: login says {actual_role}, /auth/me says {verified_role}")
                    actual_role = verified_role  # Use the verified role
            
            # Step 3: Test audit logs access
            audit_result = await self.test_audit_logs_access(token, actual_role, user_config['email'])
            
            # Determine expected behavior based on role
            should_have_access = actual_role in ['super_admin', 'admin']
            
            # Evaluate result
            test_passed = False
            if should_have_access:
                test_passed = audit_result['success'] and audit_result.get('status') == 200
                expected_outcome = "✅ Should have access (200)"
            else:
                test_passed = not audit_result['success'] and audit_result.get('status') == 403
                expected_outcome = "❌ Should be denied access (403)"
            
            print(f"\n📊 TEST RESULT FOR {user_config['email']}:")
            print(f"   Role: {actual_role}")
            print(f"   Expected: {expected_outcome}")
            print(f"   Actual: HTTP {audit_result.get('status', 'ERROR')}")
            print(f"   Result: {'✅ PASSED' if test_passed else '❌ FAILED'}")
            
            overall_results.append({
                'user': user_config['email'],
                'role': actual_role,
                'login_success': True,
                'audit_access_granted': audit_result['success'],
                'status_code': audit_result.get('status'),
                'should_have_access': should_have_access,
                'test_passed': test_passed,
                'response_time': audit_result.get('response_time', 'N/A'),
                'audit_count': audit_result.get('audit_count', 0) if audit_result['success'] else 0
            })
        
        # Final summary
        print(f"\n{'='*20} FINAL SUMMARY {'='*20}")
        
        passed_tests = sum(1 for result in overall_results if result.get('test_passed', False))
        total_tests = len(overall_results)
        
        print(f"📈 Overall Success Rate: {passed_tests}/{total_tests} ({(passed_tests/total_tests*100):.1f}%)")
        
        for result in overall_results:
            status_icon = "✅" if result.get('test_passed', False) else "❌"
            access_status = "GRANTED" if result.get('audit_access_granted', False) else "DENIED"
            print(f"{status_icon} {result['user']} ({result.get('role', 'unknown')}): {access_status} (HTTP {result.get('status_code', 'N/A')})")
        
        # Specific findings
        print(f"\n📋 KEY FINDINGS:")
        
        super_admin_result = next((r for r in overall_results if 'muratsutay' in r['user']), None)
        if super_admin_result:
            if super_admin_result.get('test_passed'):
                print(f"✅ Super admin access working correctly")
            else:
                print(f"❌ Super admin access FAILED - this is a critical issue")
        
        demo_result = next((r for r in overall_results if 'demo@hotel.com' in r['user']), None)
        if demo_result:
            demo_role = demo_result.get('role', 'unknown')
            if demo_role == 'admin':
                if demo_result.get('test_passed'):
                    print(f"✅ Admin user (demo@hotel.com) access working correctly")
                else:
                    print(f"❌ Admin user (demo@hotel.com) access FAILED")
            else:
                if demo_result.get('test_passed'):
                    print(f"✅ Non-admin user (demo@hotel.com, role: {demo_role}) correctly denied access")
                else:
                    print(f"❌ Non-admin user (demo@hotel.com, role: {demo_role}) access control FAILED")
        
        await self.session.close()
        return overall_results

async def main():
    """Main test execution"""
    tester = AuditLogsTester()
    
    try:
        results = await tester.run_comprehensive_test()
        
        # Return appropriate exit code
        all_passed = all(result.get('test_passed', False) for result in results)
        sys.exit(0 if all_passed else 1)
        
    except Exception as e:
        print(f"❌ Test execution failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())