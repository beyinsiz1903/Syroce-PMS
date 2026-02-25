#!/usr/bin/env python3
"""
Hotel Team Management & Subscription Upgrade Backend Test
Tests the hotel team management endpoints and upgrade flow as specified in the review request.
"""

import asyncio
import aiohttp
import json
import sys
import traceback
from datetime import datetime

# Backend URL from frontend .env
BACKEND_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"

# Test credentials from review request
CREDENTIALS = {
    "basic_hotel": {"email": "demo@butikotel.com", "password": "demo123"},
    "professional_hotel": {"email": "demo@grandcity.com", "password": "demo123"}, 
    "super_admin": {"email": "superadmin@syroce.com", "password": "Admin123!"}
}

class HotelTeamTester:
    def __init__(self):
        self.session = None
        self.tokens = {}
        self.results = []
        
    async def setup_session(self):
        """Initialize HTTP session"""
        connector = aiohttp.TCPConnector(ssl=False, limit=20)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        
    async def cleanup_session(self):
        """Clean up HTTP session"""
        if self.session:
            await self.session.close()
            
    def log_result(self, test_name, success, message, details=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name} - {message}")
        if details:
            print(f"   Details: {details}")
        
        self.results.append({
            "test": test_name,
            "success": success, 
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        
    async def login_user(self, user_type):
        """Login user and get JWT token"""
        try:
            creds = CREDENTIALS[user_type]
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", 
                                       json=creds) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Login failed for {user_type}: {resp.status} - {error_text}")
                
                data = await resp.json()
                token = data.get("access_token")
                if not token:
                    raise Exception(f"No access token in response for {user_type}")
                
                self.tokens[user_type] = token
                self.log_result(f"Login {user_type}", True, f"Successfully logged in as {user_type}")
                return token
                
        except Exception as e:
            self.log_result(f"Login {user_type}", False, f"Failed to login: {str(e)}")
            return None
            
    def get_auth_headers(self, user_type):
        """Get authorization headers for user"""
        token = self.tokens.get(user_type)
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}
        
    async def test_get_basic_hotel_team(self):
        """Test Case 1: GET /api/hotel/team (as Basic hotel admin)"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("GET Basic Hotel Team", False, "No auth token available")
                return
                
            async with self.session.get(f"{BACKEND_URL}/hotel/team", 
                                      headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                
                data = await resp.json()
                
                # Verify expected fields
                expected_tier = "basic"
                expected_allowed_roles = ["admin"] 
                expected_max_users = 3
                
                if data.get("tier") != expected_tier:
                    raise Exception(f"Expected tier '{expected_tier}', got '{data.get('tier')}'")
                    
                if data.get("allowed_roles") != expected_allowed_roles:
                    raise Exception(f"Expected allowed_roles {expected_allowed_roles}, got {data.get('allowed_roles')}")
                    
                if data.get("max_users") != expected_max_users:
                    raise Exception(f"Expected max_users {expected_max_users}, got {data.get('max_users')}")
                
                self.log_result("GET Basic Hotel Team", True, 
                              f"Basic hotel team data correct: tier={data.get('tier')}, "
                              f"allowed_roles={data.get('allowed_roles')}, max_users={data.get('max_users')}")
                
        except Exception as e:
            self.log_result("GET Basic Hotel Team", False, f"Failed: {str(e)}")
            
    async def test_add_basic_hotel_team_member_valid(self):
        """Test Case 2: POST /api/hotel/team (as Basic hotel admin) - Valid role"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("POST Basic Hotel Team Valid", False, "No auth token available")
                return
                
            payload = {
                "email": "test@butikotel.com",
                "name": "Test User", 
                "role": "admin",
                "password": "test123"
            }
            
            async with self.session.post(f"{BACKEND_URL}/hotel/team",
                                       json=payload, headers=headers) as resp:
                
                response_text = await resp.text()
                
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {response_text}")
                
                data = await resp.json()
                
                if not data.get("success"):
                    raise Exception(f"Expected success=true, got response: {data}")
                
                # Store user_id for later tests
                self.basic_hotel_test_user_id = data.get("user_id")
                
                self.log_result("POST Basic Hotel Team Valid", True, 
                              f"Successfully added team member with admin role: {data.get('message')}")
                
        except Exception as e:
            self.log_result("POST Basic Hotel Team Valid", False, f"Failed: {str(e)}")
            
    async def test_add_basic_hotel_team_member_invalid(self):
        """Test Case 3: POST /api/hotel/team with invalid role (as Basic hotel admin)"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("POST Basic Hotel Team Invalid", False, "No auth token available")
                return
                
            payload = {
                "email": "test2@butikotel.com",
                "name": "Test2",
                "role": "front_desk", 
                "password": "test123"
            }
            
            async with self.session.post(f"{BACKEND_URL}/hotel/team",
                                       json=payload, headers=headers) as resp:
                
                response_text = await resp.text()
                
                # Should fail with 400 error for invalid role
                if resp.status != 400:
                    raise Exception(f"Expected HTTP 400 for invalid role, got {resp.status}: {response_text}")
                
                data = await resp.json()
                error_message = data.get("detail", "")
                
                # Verify error mentions role restriction
                if "front_desk" not in error_message.lower() or "basic" not in error_message.lower():
                    raise Exception(f"Error message should mention 'front_desk' role not allowed for 'basic' tier. Got: {error_message}")
                
                self.log_result("POST Basic Hotel Team Invalid", True, 
                              f"Correctly rejected 'front_desk' role for basic tier: {error_message}")
                
        except Exception as e:
            self.log_result("POST Basic Hotel Team Invalid", False, f"Failed: {str(e)}")
            
    async def test_get_professional_hotel_team(self):
        """Test Case 4: GET /api/hotel/team (as Professional hotel admin)"""
        try:
            headers = self.get_auth_headers("professional_hotel")
            if not headers:
                self.log_result("GET Professional Hotel Team", False, "No auth token available")
                return
                
            async with self.session.get(f"{BACKEND_URL}/hotel/team", 
                                      headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                
                data = await resp.json()
                
                # Verify expected fields for professional tier
                expected_tier = "professional"
                expected_roles = ["admin", "supervisor", "front_desk", "housekeeping", "finance"]
                
                if data.get("tier") != expected_tier:
                    raise Exception(f"Expected tier '{expected_tier}', got '{data.get('tier')}'")
                
                allowed_roles = data.get("allowed_roles", [])
                for role in expected_roles:
                    if role not in allowed_roles:
                        raise Exception(f"Expected role '{role}' to be allowed for professional tier")
                
                self.log_result("GET Professional Hotel Team", True, 
                              f"Professional hotel team data correct: tier={data.get('tier')}, "
                              f"allowed_roles includes {expected_roles}")
                
        except Exception as e:
            self.log_result("GET Professional Hotel Team", False, f"Failed: {str(e)}")
            
    async def test_add_professional_hotel_team_member(self):
        """Test Case 5: POST /api/hotel/team (as Professional hotel admin)"""
        try:
            headers = self.get_auth_headers("professional_hotel")
            if not headers:
                self.log_result("POST Professional Hotel Team", False, "No auth token available")
                return
                
            payload = {
                "email": "recep@grandcity.com", 
                "name": "Recep Ali",
                "role": "front_desk",
                "password": "test123"
            }
            
            async with self.session.post(f"{BACKEND_URL}/hotel/team",
                                       json=payload, headers=headers) as resp:
                
                response_text = await resp.text()
                
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {response_text}")
                
                data = await resp.json()
                
                if not data.get("success"):
                    raise Exception(f"Expected success=true, got response: {data}")
                
                # Store user_id for later tests
                self.professional_hotel_test_user_id = data.get("user_id")
                
                self.log_result("POST Professional Hotel Team", True, 
                              f"Successfully added front_desk member to professional hotel: {data.get('message')}")
                
        except Exception as e:
            self.log_result("POST Professional Hotel Team", False, f"Failed: {str(e)}")
            
    async def test_update_team_member_role(self):
        """Test Case 6: PATCH /api/hotel/team/{user_id}/role - Update role"""
        try:
            headers = self.get_auth_headers("professional_hotel")
            if not headers:
                self.log_result("PATCH Team Member Role", False, "No auth token available")
                return
                
            if not hasattr(self, 'professional_hotel_test_user_id'):
                self.log_result("PATCH Team Member Role", False, "No test user ID from previous test")
                return
                
            user_id = self.professional_hotel_test_user_id
            payload = {"role": "supervisor"}
            
            async with self.session.patch(f"{BACKEND_URL}/hotel/team/{user_id}/role",
                                        json=payload, headers=headers) as resp:
                
                response_text = await resp.text()
                
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {response_text}")
                
                data = await resp.json()
                
                if not data.get("success"):
                    raise Exception(f"Expected success=true, got response: {data}")
                
                self.log_result("PATCH Team Member Role", True, 
                              f"Successfully updated role to supervisor: {data.get('message')}")
                
        except Exception as e:
            self.log_result("PATCH Team Member Role", False, f"Failed: {str(e)}")
            
    async def test_update_team_member_role_invalid(self):
        """Test updating role to one not allowed for tier"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("PATCH Team Member Role Invalid", False, "No auth token available") 
                return
                
            if not hasattr(self, 'basic_hotel_test_user_id'):
                self.log_result("PATCH Team Member Role Invalid", False, "No test user ID from previous test")
                return
                
            user_id = self.basic_hotel_test_user_id
            payload = {"role": "front_desk"}  # Not allowed for basic tier
            
            async with self.session.patch(f"{BACKEND_URL}/hotel/team/{user_id}/role",
                                        json=payload, headers=headers) as resp:
                
                response_text = await resp.text()
                
                # Should fail with 400 error
                if resp.status != 400:
                    raise Exception(f"Expected HTTP 400 for invalid role update, got {resp.status}: {response_text}")
                
                data = await resp.json()
                error_message = data.get("detail", "")
                
                if "front_desk" not in error_message.lower() or "basic" not in error_message.lower():
                    raise Exception(f"Error should mention role restriction. Got: {error_message}")
                
                self.log_result("PATCH Team Member Role Invalid", True, 
                              f"Correctly rejected invalid role update: {error_message}")
                
        except Exception as e:
            self.log_result("PATCH Team Member Role Invalid", False, f"Failed: {str(e)}")
            
    async def test_delete_team_member(self):
        """Test Case 7: DELETE /api/hotel/team/{user_id} - Remove team member"""
        try:
            headers = self.get_auth_headers("professional_hotel")
            if not headers:
                self.log_result("DELETE Team Member", False, "No auth token available")
                return
                
            if not hasattr(self, 'professional_hotel_test_user_id'):
                self.log_result("DELETE Team Member", False, "No test user ID from previous test")
                return
                
            user_id = self.professional_hotel_test_user_id
            
            async with self.session.delete(f"{BACKEND_URL}/hotel/team/{user_id}",
                                         headers=headers) as resp:
                
                response_text = await resp.text()
                
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {response_text}")
                
                data = await resp.json()
                
                if not data.get("success"):
                    raise Exception(f"Expected success=true, got response: {data}")
                
                self.log_result("DELETE Team Member", True, 
                              f"Successfully deleted team member: {data.get('message')}")
                
        except Exception as e:
            self.log_result("DELETE Team Member", False, f"Failed: {str(e)}")
            
    async def test_get_rbac_roles_basic(self):
        """Test Case 8: GET /api/rbac/roles (as Basic user)"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("GET RBAC Roles Basic", False, "No auth token available")
                return
                
            async with self.session.get(f"{BACKEND_URL}/rbac/roles", 
                                      headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                
                data = await resp.json()
                
                # Verify basic tier restrictions
                expected_tier = "basic"
                expected_allowed_roles = ["admin"]
                
                if data.get("tier") != expected_tier:
                    raise Exception(f"Expected tier '{expected_tier}', got '{data.get('tier')}'")
                    
                if data.get("allowed_roles") != expected_allowed_roles:
                    raise Exception(f"Expected allowed_roles {expected_allowed_roles}, got {data.get('allowed_roles')}")
                
                self.log_result("GET RBAC Roles Basic", True, 
                              f"RBAC correctly returns tier-specific roles for basic: {data.get('allowed_roles')}")
                
        except Exception as e:
            self.log_result("GET RBAC Roles Basic", False, f"Failed: {str(e)}")
            
    async def test_subscription_upgrade(self):
        """Test Case 9: POST /api/subscription/upgrade (as Basic hotel)"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("POST Subscription Upgrade", False, "No auth token available")
                return
                
            # First check current subscription
            async with self.session.get(f"{BACKEND_URL}/subscription/current", 
                                      headers=headers) as resp:
                if resp.status == 200:
                    current_data = await resp.json()
                    current_tier = current_data.get("tier", "basic")
                    print(f"   Current tier: {current_tier}")
                
            # Attempt upgrade
            async with self.session.post(f"{BACKEND_URL}/subscription/upgrade",
                                       params={"new_tier": "professional", "billing_cycle": "monthly"},
                                       headers=headers) as resp:
                
                response_text = await resp.text()
                
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {response_text}")
                
                data = await resp.json()
                
                if not data.get("success"):
                    raise Exception(f"Expected success=true, got response: {data}")
                
                if data.get("tier") != "professional":
                    raise Exception(f"Expected tier=professional, got {data.get('tier')}")
                
                self.log_result("POST Subscription Upgrade", True, 
                              f"Successfully upgraded to professional: {data.get('message')}")
                
                # Verify the upgrade took effect
                await asyncio.sleep(1)  # Brief pause
                async with self.session.get(f"{BACKEND_URL}/subscription/current", 
                                          headers=headers) as resp:
                    if resp.status == 200:
                        current_data = await resp.json()
                        new_tier = current_data.get("tier")
                        if new_tier == "professional":
                            print(f"   ✅ Upgrade verified: tier is now {new_tier}")
                        else:
                            print(f"   ⚠️ Upgrade verification failed: tier is {new_tier}")
                
        except Exception as e:
            self.log_result("POST Subscription Upgrade", False, f"Failed: {str(e)}")
            
    async def test_subscription_current_after_upgrade(self):
        """Verify GET /api/subscription/current returns professional after upgrade"""
        try:
            headers = self.get_auth_headers("basic_hotel")
            if not headers:
                self.log_result("GET Subscription Current After Upgrade", False, "No auth token available")
                return
                
            async with self.session.get(f"{BACKEND_URL}/subscription/current", 
                                      headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                
                data = await resp.json()
                
                if data.get("tier") != "professional":
                    raise Exception(f"Expected tier=professional after upgrade, got {data.get('tier')}")
                
                self.log_result("GET Subscription Current After Upgrade", True, 
                              f"Subscription correctly shows professional tier after upgrade")
                
        except Exception as e:
            self.log_result("GET Subscription Current After Upgrade", False, f"Failed: {str(e)}")
            
    async def run_all_tests(self):
        """Run all test cases"""
        print("🚀 Starting Hotel Team Management & Subscription Backend Tests")
        print(f"Backend URL: {BACKEND_URL}")
        print("="*80)
        
        await self.setup_session()
        
        try:
            # Login users
            print("\n📝 Logging in users...")
            await self.login_user("basic_hotel")
            await self.login_user("professional_hotel")
            # Skip super_admin login for now as it's not needed for current tests
            
            print("\n🧪 Running test cases...")
            
            # Test 1: Basic hotel team info
            await self.test_get_basic_hotel_team()
            
            # Test 2: Add valid team member to basic hotel
            await self.test_add_basic_hotel_team_member_valid()
            
            # Test 3: Try to add invalid role to basic hotel
            await self.test_add_basic_hotel_team_member_invalid()
            
            # Test 4: Professional hotel team info
            await self.test_get_professional_hotel_team()
            
            # Test 5: Add team member to professional hotel
            await self.test_add_professional_hotel_team_member()
            
            # Test 6: Update team member role (valid)
            await self.test_update_team_member_role()
            
            # Test 6b: Update team member role (invalid for tier)
            await self.test_update_team_member_role_invalid()
            
            # Test 7: Delete team member
            await self.test_delete_team_member()
            
            # Test 8: Get RBAC roles for basic user
            await self.test_get_rbac_roles_basic()
            
            # Test 9: Subscription upgrade
            await self.test_subscription_upgrade()
            
            # Test 10: Verify subscription after upgrade
            await self.test_subscription_current_after_upgrade()
            
        finally:
            await self.cleanup_session()
            
    def generate_summary(self):
        """Generate test results summary"""
        print("\n" + "="*80)
        print("📊 TEST RESULTS SUMMARY")
        print("="*80)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for result in self.results:
                if not result["success"]:
                    print(f"  • {result['test']}: {result['message']}")
        
        print(f"\n✅ PASSED TESTS ({passed_tests}):")
        for result in self.results:
            if result["success"]:
                print(f"  • {result['test']}: {result['message']}")
        
        return {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests/total_tests)*100 if total_tests > 0 else 0,
            "results": self.results
        }

async def main():
    """Main execution function"""
    try:
        tester = HotelTeamTester()
        await tester.run_all_tests()
        summary = tester.generate_summary()
        
        # Return appropriate exit code
        return 0 if summary["failed"] == 0 else 1
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)