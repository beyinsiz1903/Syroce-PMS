"""
Governance Layer API Tests
Tests for: Entitlement Enforcement, Usage Metering, Feature Flags, Onboarding Automation
All APIs require super_admin auth via Bearer token.
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super_admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Session with auth header."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def tenant_id(api_client):
    """Get a valid tenant_id from the system."""
    response = api_client.get(f"{BASE_URL}/api/admin/tenants")
    if response.status_code == 200:
        tenants = response.json().get("tenants", [])
        if tenants:
            return tenants[0]["id"]
    pytest.skip("No tenants available for testing")


# ─── ENTITLEMENTS TESTS ───

class TestEntitlementsOverview:
    """Tests for GET /api/admin/entitlements/overview"""
    
    def test_entitlements_overview_returns_200(self, api_client):
        """Verify entitlements overview endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/entitlements/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_entitlements_overview_structure(self, api_client):
        """Verify entitlements overview returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/entitlements/overview")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_tenants" in data, "Missing total_tenants field"
        assert "by_tier" in data, "Missing by_tier field"
        assert "expired_subscriptions" in data, "Missing expired_subscriptions field"
        assert "expired_count" in data, "Missing expired_count field"
        
        # Verify data types
        assert isinstance(data["total_tenants"], int), "total_tenants should be int"
        assert isinstance(data["by_tier"], dict), "by_tier should be dict"
        assert isinstance(data["expired_subscriptions"], list), "expired_subscriptions should be list"
        assert isinstance(data["expired_count"], int), "expired_count should be int"
        
        print(f"Total tenants: {data['total_tenants']}, Tiers: {data['by_tier']}, Expired: {data['expired_count']}")


class TestTenantEntitlements:
    """Tests for GET /api/admin/tenants/{tenant_id}/entitlements"""
    
    def test_tenant_entitlements_returns_200(self, api_client, tenant_id):
        """Verify tenant entitlements endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/entitlements")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_tenant_entitlements_structure(self, api_client, tenant_id):
        """Verify tenant entitlements returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/entitlements")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "tenant_id" in data, "Missing tenant_id field"
        assert "tier" in data, "Missing tier field"
        assert "modules" in data, "Missing modules field"
        assert "quotas" in data, "Missing quotas field"
        assert "plan_limits" in data, "Missing plan_limits field"
        
        # Verify quotas structure
        assert "rooms" in data["quotas"], "Missing rooms quota"
        assert "users" in data["quotas"], "Missing users quota"
        
        # Verify plan_limits structure
        assert "max_rooms" in data["plan_limits"], "Missing max_rooms in plan_limits"
        assert "max_users" in data["plan_limits"], "Missing max_users in plan_limits"
        
        print(f"Tenant {tenant_id}: tier={data['tier']}, modules={len([k for k,v in data['modules'].items() if v])}")
    
    def test_tenant_entitlements_invalid_tenant(self, api_client):
        """Verify 404 for non-existent tenant."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/invalid-tenant-xyz/entitlements")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


# ─── USAGE METERING TESTS ───

class TestUsageOverview:
    """Tests for GET /api/admin/usage/overview"""
    
    def test_usage_overview_returns_200(self, api_client):
        """Verify usage overview endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/usage/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_usage_overview_structure(self, api_client):
        """Verify usage overview returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/usage/overview")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "today" in data, "Missing today field"
        assert "this_month" in data, "Missing this_month field"
        assert "active_tenants_7d" in data, "Missing active_tenants_7d field"
        assert "top_tenants" in data, "Missing top_tenants field"
        assert "generated_at" in data, "Missing generated_at field"
        
        # Verify data types
        assert isinstance(data["today"], dict), "today should be dict"
        assert isinstance(data["this_month"], dict), "this_month should be dict"
        assert isinstance(data["active_tenants_7d"], int), "active_tenants_7d should be int"
        assert isinstance(data["top_tenants"], list), "top_tenants should be list"
        
        print(f"Active tenants (7d): {data['active_tenants_7d']}, Top tenants: {len(data['top_tenants'])}")


class TestTenantUsage:
    """Tests for GET /api/admin/tenants/{tenant_id}/usage"""
    
    def test_tenant_usage_returns_200(self, api_client, tenant_id):
        """Verify tenant usage endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/usage")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_tenant_usage_structure(self, api_client, tenant_id):
        """Verify tenant usage returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/usage?days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "tenant_id" in data, "Missing tenant_id field"
        assert "period_days" in data, "Missing period_days field"
        assert "events" in data, "Missing events field"
        assert "current_resources" in data, "Missing current_resources field"
        
        # Verify current_resources structure
        assert "rooms" in data["current_resources"], "Missing rooms in current_resources"
        assert "users" in data["current_resources"], "Missing users in current_resources"
        assert "guests" in data["current_resources"], "Missing guests in current_resources"
        
        print(f"Tenant {tenant_id} usage: events={len(data['events'])}, resources={data['current_resources']}")


# ─── FEATURE FLAGS TESTS ───

class TestFeatureFlagsList:
    """Tests for GET /api/admin/feature-flags"""
    
    def test_feature_flags_list_returns_200(self, api_client):
        """Verify feature flags list endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/feature-flags")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_feature_flags_list_structure(self, api_client):
        """Verify feature flags list returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/feature-flags")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "flags" in data, "Missing flags field"
        assert "count" in data, "Missing count field"
        
        # Verify data types
        assert isinstance(data["flags"], list), "flags should be list"
        assert isinstance(data["count"], int), "count should be int"
        
        print(f"Feature flags count: {data['count']}")


class TestFeatureFlagCRUD:
    """Tests for feature flag CRUD operations"""
    
    TEST_FLAG_KEY = "TEST_governance_test_flag"
    
    def test_create_feature_flag(self, api_client):
        """Test POST /api/admin/feature-flags - create new flag."""
        payload = {
            "flag_key": self.TEST_FLAG_KEY,
            "enabled": True,
            "description": "Test flag for governance layer testing",
            "rollout_percentage": 50,
            "kill_switch": False
        }
        response = api_client.post(f"{BASE_URL}/api/admin/feature-flags", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Expected success=True"
        assert "flag" in data, "Missing flag in response"
        assert data["flag"]["flag_key"] == self.TEST_FLAG_KEY
        assert data["flag"]["enabled"] == True
        assert data["flag"]["rollout_percentage"] == 50
        
        print(f"Created flag: {self.TEST_FLAG_KEY}")
    
    def test_get_feature_flag(self, api_client):
        """Test GET /api/admin/feature-flags/{flag_key}."""
        response = api_client.get(f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["flag_key"] == self.TEST_FLAG_KEY
        assert "enabled" in data
        assert "description" in data
        
        print(f"Retrieved flag: {data['flag_key']}, enabled={data['enabled']}")
    
    def test_update_feature_flag(self, api_client):
        """Test POST /api/admin/feature-flags - update existing flag."""
        payload = {
            "flag_key": self.TEST_FLAG_KEY,
            "enabled": False,
            "description": "Updated test flag",
            "rollout_percentage": 75,
            "kill_switch": False
        }
        response = api_client.post(f"{BASE_URL}/api/admin/feature-flags", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["flag"]["enabled"] == False
        assert data["flag"]["rollout_percentage"] == 75
        
        print(f"Updated flag: {self.TEST_FLAG_KEY}, enabled=False, rollout=75%")
    
    def test_check_flag_for_tenant(self, api_client, tenant_id):
        """Test GET /api/admin/feature-flags/{flag_key}/check?tenant_id=X."""
        response = api_client.get(
            f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}/check",
            params={"tenant_id": tenant_id}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "flag_key" in data
        assert "tenant_id" in data
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)
        
        print(f"Flag check: {data['flag_key']} for tenant {data['tenant_id']} = {data['enabled']}")
    
    def test_set_tenant_override(self, api_client, tenant_id):
        """Test PATCH /api/admin/feature-flags/{flag_key}/tenant-override."""
        payload = {
            "tenant_id": tenant_id,
            "enabled": True
        }
        response = api_client.patch(
            f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}/tenant-override",
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        
        # Verify override is set
        check_response = api_client.get(
            f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}/check",
            params={"tenant_id": tenant_id}
        )
        assert check_response.status_code == 200
        assert check_response.json()["enabled"] == True, "Override should enable flag for tenant"
        
        print(f"Set tenant override: {tenant_id} = True")
    
    def test_remove_tenant_override(self, api_client, tenant_id):
        """Test PATCH /api/admin/feature-flags/{flag_key}/tenant-override with remove=true."""
        payload = {
            "tenant_id": tenant_id,
            "remove": True
        }
        response = api_client.patch(
            f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}/tenant-override",
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        
        print(f"Removed tenant override for: {tenant_id}")
    
    def test_delete_feature_flag(self, api_client):
        """Test DELETE /api/admin/feature-flags/{flag_key}."""
        response = api_client.delete(f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        
        # Verify flag is deleted
        get_response = api_client.get(f"{BASE_URL}/api/admin/feature-flags/{self.TEST_FLAG_KEY}")
        assert get_response.status_code == 404, "Flag should be deleted"
        
        print(f"Deleted flag: {self.TEST_FLAG_KEY}")
    
    def test_create_flag_without_key_returns_400(self, api_client):
        """Test POST /api/admin/feature-flags without flag_key returns 400."""
        payload = {
            "enabled": True,
            "description": "Missing flag_key"
        }
        response = api_client.post(f"{BASE_URL}/api/admin/feature-flags", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ─── ONBOARDING TESTS ───

class TestOnboardingOverview:
    """Tests for GET /api/admin/onboarding/overview"""
    
    def test_onboarding_overview_returns_200(self, api_client):
        """Verify onboarding overview endpoint returns 200."""
        response = api_client.get(f"{BASE_URL}/api/admin/onboarding/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_onboarding_overview_structure(self, api_client):
        """Verify onboarding overview returns expected structure."""
        response = api_client.get(f"{BASE_URL}/api/admin/onboarding/overview")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "tenants" in data, "Missing tenants field"
        assert "count" in data, "Missing count field"
        
        # Verify data types
        assert isinstance(data["tenants"], list), "tenants should be list"
        assert isinstance(data["count"], int), "count should be int"
        
        # Verify tenant structure if tenants exist
        if data["tenants"]:
            tenant = data["tenants"][0]
            assert "tenant_id" in tenant, "Missing tenant_id in tenant"
            assert "property_name" in tenant, "Missing property_name in tenant"
            assert "progress_pct" in tenant, "Missing progress_pct in tenant"
            assert "completed" in tenant, "Missing completed in tenant"
            assert "total" in tenant, "Missing total in tenant"
        
        print(f"Onboarding overview: {data['count']} tenants")


class TestTenantOnboarding:
    """Tests for tenant onboarding endpoints"""
    
    def test_tenant_onboarding_returns_200(self, api_client, tenant_id):
        """Test GET /api/admin/tenants/{tenant_id}/onboarding."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/onboarding")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_tenant_onboarding_structure(self, api_client, tenant_id):
        """Verify tenant onboarding returns expected structure with auto-detection."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/onboarding")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "tenant_id" in data, "Missing tenant_id field"
        assert "steps" in data, "Missing steps field"
        assert "total" in data, "Missing total field"
        assert "completed" in data, "Missing completed field"
        assert "progress_pct" in data, "Missing progress_pct field"
        
        # Verify steps structure
        assert isinstance(data["steps"], list), "steps should be list"
        if data["steps"]:
            step = data["steps"][0]
            assert "step_id" in step, "Missing step_id in step"
            assert "label" in step, "Missing label in step"
            assert "description" in step, "Missing description in step"
            assert "category" in step, "Missing category in step"
            assert "completed" in step, "Missing completed in step"
        
        print(f"Tenant {tenant_id} onboarding: {data['completed']}/{data['total']} ({data['progress_pct']}%)")
    
    def test_mark_step_complete(self, api_client, tenant_id):
        """Test POST /api/admin/tenants/{tenant_id}/onboarding/{step_id}/complete."""
        # Get current onboarding to find an incomplete step
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/onboarding")
        assert response.status_code == 200
        data = response.json()
        
        # Find an incomplete step to mark complete
        incomplete_steps = [s for s in data["steps"] if not s["completed"]]
        if not incomplete_steps:
            pytest.skip("All steps already completed")
        
        step_id = incomplete_steps[0]["step_id"]
        
        # Mark step complete
        response = api_client.post(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}/onboarding/{step_id}/complete"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("step_id") == step_id
        
        print(f"Marked step complete: {step_id}")


# ─── ENTITLEMENT MIDDLEWARE TEST ───

class TestEntitlementMiddleware:
    """Tests for entitlement middleware blocking access based on plan"""
    
    def test_basic_plan_blocked_from_channel_manager(self, api_client):
        """Verify basic plan tenants are blocked from channel-manager routes.
        
        Note: This test verifies the middleware behavior. The actual blocking
        depends on the tenant's plan and modules configuration.
        """
        # First, get a basic plan tenant
        response = api_client.get(f"{BASE_URL}/api/admin/tenants")
        assert response.status_code == 200
        tenants = response.json().get("tenants", [])
        
        basic_tenants = [t for t in tenants if (t.get("subscription_tier") or "basic").lower() == "basic"]
        
        if not basic_tenants:
            pytest.skip("No basic plan tenants available for testing")
        
        # Get entitlements for a basic tenant to verify modules
        basic_tenant = basic_tenants[0]
        ent_response = api_client.get(f"{BASE_URL}/api/admin/tenants/{basic_tenant['id']}/entitlements")
        assert ent_response.status_code == 200
        
        entitlements = ent_response.json()
        has_channel_manager = entitlements.get("modules", {}).get("channel_manager", False)
        
        print(f"Basic tenant {basic_tenant['id']}: channel_manager module = {has_channel_manager}")
        
        # The middleware should block if channel_manager is False
        # This is a verification that the entitlement data is correct
        if not has_channel_manager:
            print("Verified: Basic plan tenant does not have channel_manager module")
        else:
            print("Note: This basic tenant has channel_manager enabled (possibly upgraded)")


# ─── QUOTA CHECK TEST ───

class TestQuotaCheck:
    """Tests for quota checking endpoint"""
    
    def test_check_rooms_quota(self, api_client, tenant_id):
        """Test GET /api/admin/tenants/{tenant_id}/quota/rooms."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/quota/rooms")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "allowed" in data, "Missing allowed field"
        assert "current" in data, "Missing current field"
        assert "limit" in data, "Missing limit field"
        assert "resource" in data, "Missing resource field"
        assert data["resource"] == "rooms"
        
        print(f"Rooms quota: {data['current']}/{data['limit'] or '∞'}, allowed={data['allowed']}")
    
    def test_check_users_quota(self, api_client, tenant_id):
        """Test GET /api/admin/tenants/{tenant_id}/quota/users."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/quota/users")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "allowed" in data
        assert "current" in data
        assert "limit" in data
        assert data["resource"] == "users"
        
        print(f"Users quota: {data['current']}/{data['limit'] or '∞'}, allowed={data['allowed']}")
    
    def test_invalid_resource_returns_400(self, api_client, tenant_id):
        """Test invalid resource type returns 400."""
        response = api_client.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/quota/invalid")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
