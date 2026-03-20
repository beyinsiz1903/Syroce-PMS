"""
Admin Tenants API Tests
Tests for the Admin Tenant Management endpoints:
- GET /api/admin/tenants - list all tenants
- POST /api/admin/tenants - create new tenant
- PATCH /api/admin/tenants/{id}/info - update tenant info
- GET /api/admin/tenants/{id}/team - list team members
- POST /api/admin/tenants/{id}/team - add team member
- DELETE /api/admin/tenants/{id}/team/{user_id} - remove team member
- PATCH /api/admin/tenants/{id}/team/{user_id}/role - update role
- GET /api/admin/tenants/{id}/stats - get tenant stats
- GET /api/admin/users - list all users
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials for super_admin
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set – integration tests require a running server"
)


class TestAdminTenantsAPI:
    """Admin Tenants API Tests - requires super_admin role"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for super_admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip(f"No token in response: {data}")
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with authentication"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    # ===================== GET /api/admin/tenants =====================
    
    def test_list_tenants_success(self, auth_headers):
        """Test listing all tenants - should return 200 with tenant list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "tenants" in data, "Response should contain 'tenants' key"
        assert isinstance(data["tenants"], list), "tenants should be a list"
        
        # Check tenant structure
        if len(data["tenants"]) > 0:
            tenant = data["tenants"][0]
            assert "id" in tenant, "Tenant should have 'id' field"
            print(f"Found {len(data['tenants'])} tenants")
    
    def test_list_tenants_unauthorized(self):
        """Test listing tenants without auth - should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/admin/tenants")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    # ===================== POST /api/admin/tenants =====================
    
    def test_create_tenant_success(self, auth_headers):
        """Test creating a new tenant - should return 200/201"""
        unique_id = str(uuid.uuid4())[:8]
        new_tenant = {
            "property_name": f"TEST_Hotel_{unique_id}",
            "email": f"test-tenant-{unique_id}@test.com",
            "password": "testpass123",
            "name": f"Test Admin {unique_id}",
            "phone": "+90 555 000 0000",
            "address": "Test Address 123",
            "location": "Test City",
            "description": "Test hotel created by automated tests",
            "subscription_tier": "basic",
            "subscription_days": 30
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers,
            json=new_tenant
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        assert "tenant_id" in data, f"Response should contain tenant_id: {data}"
        
        # Store tenant_id for cleanup
        print(f"Created tenant: {data.get('tenant_id')}")
        return data.get("tenant_id")
    
    def test_create_tenant_missing_fields(self, auth_headers):
        """Test creating tenant with missing required fields - should return 400/422"""
        incomplete_tenant = {
            "property_name": "Test Hotel"
            # Missing email, password, name, phone, address
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers,
            json=incomplete_tenant
        )
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
    
    def test_create_tenant_duplicate_email(self, auth_headers):
        """Test creating tenant with duplicate email - should return 400"""
        # Using existing demo email
        duplicate_tenant = {
            "property_name": "Duplicate Hotel",
            "email": "demo@hotel.com",  # Already exists
            "password": "testpass123",
            "name": "Duplicate Admin",
            "phone": "+90 555 000 0001",
            "address": "Test Address"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers,
            json=duplicate_tenant
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    
    # ===================== PATCH /api/admin/tenants/{id}/info =====================
    
    def test_update_tenant_info(self, auth_headers):
        """Test updating tenant info - should return 200"""
        # First get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        # Update the tenant info
        update_data = {
            "description": f"Updated by test at {uuid.uuid4()}"
        }
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/info",
            headers=auth_headers,
            json=update_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
    
    def test_update_tenant_info_not_found(self, auth_headers):
        """Test updating non-existent tenant - should return 404"""
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/nonexistent-tenant-id/info",
            headers=auth_headers,
            json={"description": "Test"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    # ===================== GET /api/admin/tenants/{id}/team =====================
    
    def test_list_tenant_team(self, auth_headers):
        """Test listing tenant team members - should return 200"""
        # First get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        response = requests.get(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "users" in data, f"Response should contain 'users' key: {data}"
        assert "count" in data, f"Response should contain 'count' key: {data}"
        print(f"Team has {data.get('count')} members")
    
    # ===================== POST /api/admin/tenants/{id}/team =====================
    
    def test_add_team_member(self, auth_headers):
        """Test adding a team member - should return 200"""
        # First get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        unique_id = str(uuid.uuid4())[:8]
        
        new_member = {
            "email": f"test-member-{unique_id}@test.com",
            "name": f"Test Member {unique_id}",
            "phone": "+90 555 000 0002",
            "password": "testpass123",
            "role": "front_desk"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team",
            headers=auth_headers,
            json=new_member
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        assert "user_id" in data, f"Response should contain user_id: {data}"
        
        print(f"Added team member: {data.get('user_id')}")
        return data.get("user_id"), tenant_id
    
    def test_add_team_member_duplicate_email(self, auth_headers):
        """Test adding team member with duplicate email - should return 400"""
        # First get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        # Try to add with existing email
        duplicate_member = {
            "email": "demo@hotel.com",  # Already exists
            "name": "Duplicate Member",
            "password": "testpass123",
            "role": "front_desk"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team",
            headers=auth_headers,
            json=duplicate_member
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    # ===================== GET /api/admin/tenants/{id}/stats =====================
    
    def test_get_tenant_stats(self, auth_headers):
        """Test getting tenant stats - should return 200 with stats data"""
        # First get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        response = requests.get(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/stats",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Check expected stat fields
        expected_fields = ["rooms", "users", "guests", "total_bookings", "bookings_this_month", "checked_in"]
        for field in expected_fields:
            assert field in data, f"Stats should contain '{field}' field: {data}"
        
        print(f"Tenant stats: rooms={data.get('rooms')}, users={data.get('users')}, guests={data.get('guests')}")
    
    def test_get_tenant_stats_not_found(self, auth_headers):
        """Test getting stats for non-existent tenant - should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/admin/tenants/nonexistent-tenant-id/stats",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    # ===================== GET /api/admin/users =====================
    
    def test_list_all_users(self, auth_headers):
        """Test listing all users - should return 200 with user list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "users" in data, f"Response should contain 'users' key: {data}"
        assert "count" in data, f"Response should contain 'count' key: {data}"
        
        # Check user structure (password should be excluded)
        if len(data["users"]) > 0:
            user = data["users"][0]
            assert "id" in user, "User should have 'id' field"
            assert "email" in user, "User should have 'email' field"
            assert "role" in user, "User should have 'role' field"
            assert "hashed_password" not in user, "User should NOT have password field"
            assert "password_hash" not in user, "User should NOT have password_hash field"
        
        print(f"Found {data.get('count')} users")
    
    def test_list_users_with_filters(self, auth_headers):
        """Test listing users with filters - should return 200"""
        # Filter by role
        response = requests.get(
            f"{BASE_URL}/api/admin/users?role_filter=admin",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # All returned users should have admin role
        for user in data.get("users", []):
            assert user.get("role") == "admin", f"Expected admin role: {user}"
    
    # ===================== PATCH /api/admin/tenants/{id}/team/{user_id}/role =====================
    
    def test_update_team_member_role(self, auth_headers):
        """Test updating team member role - need to first add a member"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        # Get team members
        team_response = requests.get(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team",
            headers=auth_headers
        )
        assert team_response.status_code == 200
        
        users = team_response.json().get("users", [])
        # Find a non-super_admin user to update
        target_user = None
        for user in users:
            if user.get("role") != "super_admin":
                target_user = user
                break
        
        if not target_user:
            pytest.skip("No non-super_admin users to test role update")
        
        user_id = target_user.get("id")
        current_role = target_user.get("role")
        new_role = "housekeeping" if current_role != "housekeeping" else "front_desk"
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team/{user_id}/role",
            headers=auth_headers,
            json={"role": new_role}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        
        # Restore original role
        requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team/{user_id}/role",
            headers=auth_headers,
            json={"role": current_role}
        )
    
    # ===================== DELETE /api/admin/tenants/{id}/team/{user_id} =====================
    
    def test_remove_team_member(self, auth_headers):
        """Test removing a team member - need to first add one"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        unique_id = str(uuid.uuid4())[:8]
        
        # Add a member to remove
        new_member = {
            "email": f"test-to-delete-{unique_id}@test.com",
            "name": f"Test Delete {unique_id}",
            "phone": "+90 555 000 0003",
            "password": "testpass123",
            "role": "front_desk"
        }
        
        add_response = requests.post(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team",
            headers=auth_headers,
            json=new_member
        )
        
        if add_response.status_code != 200:
            pytest.skip(f"Could not add member for delete test: {add_response.text}")
        
        user_id = add_response.json().get("user_id")
        
        # Now delete
        response = requests.delete(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team/{user_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
    
    def test_remove_team_member_not_found(self, auth_headers):
        """Test removing non-existent team member - should return 404"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        response = requests.delete(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/team/nonexistent-user-id",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


# Additional tests for plan and subscription endpoints

class TestAdminPlanAndSubscription:
    """Tests for plan change and subscription update endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for super_admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_update_tenant_tier(self, auth_headers):
        """Test updating tenant tier/plan"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        # Find a basic tier tenant to upgrade
        target_tenant = None
        for t in tenants:
            if t.get("subscription_tier") == "basic":
                target_tenant = t
                break
        
        if not target_tenant:
            target_tenant = tenants[0]
        
        tenant_id = target_tenant.get("id")
        original_tier = target_tenant.get("subscription_tier", "basic")
        
        # Change to different tier
        new_tier = "professional" if original_tier != "professional" else "basic"
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/tier",
            headers=auth_headers,
            json={"tier": new_tier, "reset_modules": False}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        
        # Restore original tier
        requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/tier",
            headers=auth_headers,
            json={"tier": original_tier, "reset_modules": False}
        )
    
    def test_update_tenant_subscription(self, auth_headers):
        """Test updating tenant subscription dates"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/subscription",
            headers=auth_headers,
            json={"subscription_days": 90}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        assert "subscription_end" in data, f"Response should contain subscription_end: {data}"
    
    def test_update_modules(self, auth_headers):
        """Test updating tenant modules"""
        # Get a tenant
        list_response = requests.get(
            f"{BASE_URL}/api/admin/tenants",
            headers=auth_headers
        )
        tenants = list_response.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants available for testing")
        
        tenant_id = tenants[0].get("id")
        
        # Toggle a module
        response = requests.patch(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/modules",
            headers=auth_headers,
            json={"modules": {"pms": True, "reports": True}}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "modules" in data, f"Response should contain modules: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
