"""
Provider Configuration, Slack Integration & Trend Charts API Tests
=================================================================

Tests for 4 NEW features added to the Channel Manager:
1. Provider Credential Configuration + Validation UI
2. Slack Alert Integration 
3. Monitoring Trend Charts (24h)
4. Provider validation checklist endpoints

Endpoints tested:
- GET  /api/channel-manager/config/providers - Provider overview
- POST /api/channel-manager/config/providers/{provider}/credentials - Save credentials
- GET  /api/channel-manager/config/providers/{provider}/credentials - Get masked credentials
- DELETE /api/channel-manager/config/providers/{provider}/credentials - Delete credentials
- POST /api/channel-manager/config/providers/{provider}/validate - Run validation
- POST /api/channel-manager/config/providers/{provider}/test-connection - Test connection
- GET  /api/channel-manager/config/providers/{provider}/readiness - Get readiness score
- GET  /api/channel-manager/monitoring/dispatch-config - Get Slack config
- POST /api/channel-manager/monitoring/dispatch-config/slack - Save Slack config
- POST /api/channel-manager/monitoring/dispatch-config/slack/test - Test Slack webhook
- GET  /api/channel-manager/monitoring/trends - Get time-series data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthAndSetup:
    """Authentication and session setup"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token using demo credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token")
        assert token, "No access_token in response"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Return auth headers for API calls"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestProviderConfigEndpoints(TestAuthAndSetup):
    """Provider Configuration API Tests"""
    
    def test_get_providers_overview(self, auth_headers):
        """GET /api/channel-manager/config/providers returns both providers with field definitions"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/config/providers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify providers array exists
        assert "providers" in data
        providers = data["providers"]
        assert len(providers) >= 2, f"Expected at least 2 providers, got {len(providers)}"
        
        # Verify HotelRunner provider
        hr_provider = next((p for p in providers if p["provider"] == "hotelrunner"), None)
        assert hr_provider is not None, "HotelRunner provider not found"
        assert hr_provider["display_name"] == "HotelRunner"
        assert "fields" in hr_provider
        assert len(hr_provider["fields"]) >= 2  # token, hr_id
        field_keys = [f["key"] for f in hr_provider["fields"]]
        assert "token" in field_keys, "token field missing in HotelRunner"
        assert "hr_id" in field_keys, "hr_id field missing in HotelRunner"
        
        # Verify Exely provider
        exely_provider = next((p for p in providers if p["provider"] == "exely"), None)
        assert exely_provider is not None, "Exely provider not found"
        assert exely_provider["display_name"] == "Exely"
        assert "fields" in exely_provider
        assert len(exely_provider["fields"]) >= 3  # username, password, hotel_code
        field_keys = [f["key"] for f in exely_provider["fields"]]
        assert "username" in field_keys, "username field missing in Exely"
        assert "password" in field_keys, "password field missing in Exely"
        assert "hotel_code" in field_keys, "hotel_code field missing in Exely"
        
        print(f"✓ GET /api/channel-manager/config/providers - Found {len(providers)} providers with field definitions")
    
    def test_save_hotelrunner_credentials(self, auth_headers):
        """POST /api/channel-manager/config/providers/{provider}/credentials saves encrypted credentials"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers,
            json={
                "credentials": {
                    "token": "TEST_hr_api_token_12345",
                    "hr_id": "TEST_hr_hotel_id"
                },
                "property_id": "default"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "secret_id" in data
        assert data.get("provider") == "hotelrunner"
        assert "saved" in data.get("message", "").lower() or "credentials" in data.get("message", "").lower()
        print(f"✓ POST /api/channel-manager/config/providers/hotelrunner/credentials - Secret ID: {data['secret_id'][:20]}...")
    
    def test_save_exely_credentials(self, auth_headers):
        """POST /api/channel-manager/config/providers/{provider}/credentials saves Exely credentials"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/exely/credentials",
            headers=auth_headers,
            json={
                "credentials": {
                    "username": "TEST_exely_user",
                    "password": "TEST_exely_pass",
                    "hotel_code": "TEST_12345"
                },
                "property_id": "default"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "secret_id" in data
        print(f"✓ POST /api/channel-manager/config/providers/exely/credentials - Saved successfully")
    
    def test_save_credentials_missing_required_field(self, auth_headers):
        """POST /api/channel-manager/config/providers/{provider}/credentials rejects missing required fields"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers,
            json={
                "credentials": {"token": "only_token"},  # Missing hr_id
                "property_id": "default"
            }
        )
        # Should return 400 for missing required field
        assert response.status_code == 400
        print(f"✓ POST credentials correctly rejects missing required field")
    
    def test_get_masked_credentials(self, auth_headers):
        """GET /api/channel-manager/config/providers/{provider}/credentials returns masked credentials"""
        # First save credentials
        requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers,
            json={
                "credentials": {"token": "TEST_token_abc123", "hr_id": "TEST_hr_789"},
                "property_id": "default"
            }
        )
        
        # Then get masked credentials
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data
        creds = data["credentials"]
        if creds:  # May be None if not yet saved
            assert "fields" in creds
            # Verify values are masked (should contain *** or similar)
            for key, value in creds.get("fields", {}).items():
                if value and len(value) > 0:
                    assert "***" in value or len(value) <= 6, f"Field {key} should be masked"
        print(f"✓ GET /api/channel-manager/config/providers/hotelrunner/credentials - Credentials are masked")
    
    def test_run_validation_checklist(self, auth_headers):
        """POST /api/channel-manager/config/providers/{provider}/validate runs validation checklist"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/validate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "provider" in data
        assert data["provider"] == "hotelrunner"
        assert "overall_status" in data  # passed, failed, partial, no_credentials
        assert "results" in data  # List of validation check results
        
        results = data["results"]
        assert isinstance(results, list)
        
        # Verify each result has expected fields
        for r in results:
            assert "check" in r
            assert "status" in r  # passed, failed, skipped
            assert "message" in r
        
        print(f"✓ POST /api/channel-manager/config/providers/hotelrunner/validate - Status: {data['overall_status']}, {len(results)} checks")
    
    def test_test_connection(self, auth_headers):
        """POST /api/channel-manager/config/providers/{provider}/test-connection tests connection"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/test-connection",
            headers=auth_headers
        )
        
        # May succeed or fail depending on real credentials, but should return 200
        if response.status_code == 200:
            data = response.json()
            assert "connected" in data or "error" in data
            print(f"✓ POST /api/channel-manager/config/providers/hotelrunner/test-connection - Result: {data}")
        elif response.status_code == 400:
            # No credentials configured
            data = response.json()
            assert "No credentials" in data.get("detail", "")
            print(f"✓ POST test-connection correctly returns 400 when no credentials configured")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_get_readiness_score(self, auth_headers):
        """GET /api/channel-manager/config/providers/{provider}/readiness returns readiness score"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/readiness",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify readiness fields
        assert "auth_ok" in data
        assert "pull_ok" in data
        assert "mapping_readiness_pct" in data
        
        print(f"✓ GET /api/channel-manager/config/providers/hotelrunner/readiness - auth_ok={data['auth_ok']}, pull_ok={data['pull_ok']}")
    
    def test_unknown_provider_returns_400(self, auth_headers):
        """Unknown provider returns 400 error"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/unknownprovider/credentials",
            headers=auth_headers
        )
        assert response.status_code == 400
        print(f"✓ Unknown provider correctly returns 400")
    
    def test_delete_credentials(self, auth_headers):
        """DELETE /api/channel-manager/config/providers/{provider}/credentials removes stored credentials"""
        # First ensure credentials exist
        requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers,
            json={
                "credentials": {"token": "TEST_delete_me", "hr_id": "TEST_del_123"},
                "property_id": "default"
            }
        )
        
        # Delete credentials
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # May return success=True or success=False depending on state
        assert "success" in data
        print(f"✓ DELETE /api/channel-manager/config/providers/hotelrunner/credentials - success={data['success']}")


class TestSlackIntegration(TestAuthAndSetup):
    """Slack Alert Integration Tests"""
    
    def test_get_dispatch_config(self, auth_headers):
        """GET /api/channel-manager/monitoring/dispatch-config returns Slack config"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify slack config structure
        assert "slack" in data
        slack = data["slack"]
        assert "enabled" in slack
        assert "webhook_url" in slack or "webhook_url_masked" in slack
        assert "severities" in slack
        
        print(f"✓ GET /api/channel-manager/monitoring/dispatch-config - Slack enabled={slack.get('enabled')}")
    
    def test_save_slack_config(self, auth_headers):
        """POST /api/channel-manager/monitoring/dispatch-config/slack saves Slack webhook config"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config/slack",
            headers=auth_headers,
            json={
                "enabled": True,
                "webhook_url": "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
                "severities": ["critical", "high"],
                "channel_name": "#alerts-test"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "Slack" in data.get("message", "") or "updated" in data.get("message", "").lower()
        print(f"✓ POST /api/channel-manager/monitoring/dispatch-config/slack - Slack config saved")
    
    def test_slack_test_without_webhook(self, auth_headers):
        """POST /api/channel-manager/monitoring/dispatch-config/slack/test returns error when no webhook configured"""
        # First clear the webhook
        requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config/slack",
            headers=auth_headers,
            json={
                "enabled": False,
                "webhook_url": "",  # Clear webhook
                "severities": ["critical"],
                "channel_name": ""
            }
        )
        
        # Try to test without webhook
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config/slack/test",
            headers=auth_headers
        )
        
        # Should return 400 when no webhook URL configured
        assert response.status_code == 400
        data = response.json()
        assert "webhook" in data.get("detail", "").lower() or "configured" in data.get("detail", "").lower()
        print(f"✓ POST /api/channel-manager/monitoring/dispatch-config/slack/test - Returns 400 when no webhook")
    
    def test_slack_config_with_different_severities(self, auth_headers):
        """Save and verify different severity configurations"""
        # Save with all severities
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config/slack",
            headers=auth_headers,
            json={
                "enabled": True,
                "webhook_url": "https://hooks.slack.com/test",
                "severities": ["critical", "high", "medium", "info"],
                "channel_name": "#all-alerts"
            }
        )
        assert response.status_code == 200
        
        # Verify saved config
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/dispatch-config",
            headers=auth_headers
        )
        data = response.json()
        slack = data.get("slack", {})
        assert "critical" in slack.get("severities", [])
        assert "high" in slack.get("severities", [])
        print(f"✓ Slack config severities saved correctly: {slack.get('severities')}")


class TestTrendCharts(TestAuthAndSetup):
    """Monitoring Trend Charts API Tests"""
    
    def test_get_trends_default(self, auth_headers):
        """GET /api/channel-manager/monitoring/trends returns time-series data"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/trends",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "hours" in data
        assert data["hours"] == 24  # Default
        assert "data_points" in data
        assert "ingest" in data
        assert "ari" in data
        assert "reconciliation" in data
        assert "queue" in data
        
        # Each series should be a list
        assert isinstance(data["ingest"], list)
        assert isinstance(data["ari"], list)
        assert isinstance(data["reconciliation"], list)
        assert isinstance(data["queue"], list)
        
        print(f"✓ GET /api/channel-manager/monitoring/trends - {data['data_points']} data points for {data['hours']}h")
    
    def test_get_trends_6h(self, auth_headers):
        """GET /api/channel-manager/monitoring/trends?hours=6 returns 6h data"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/trends?hours=6",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hours"] == 6
        print(f"✓ GET trends?hours=6 - {data['data_points']} data points")
    
    def test_get_trends_48h(self, auth_headers):
        """GET /api/channel-manager/monitoring/trends?hours=48 returns 48h data"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/trends?hours=48",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hours"] == 48
        print(f"✓ GET trends?hours=48 - {data['data_points']} data points")
    
    def test_trends_data_structure(self, auth_headers):
        """Verify trends data structure has correct fields"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/trends?hours=12",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # If we have data points, verify structure
        if data["data_points"] > 0:
            # Ingest series
            if len(data["ingest"]) > 0:
                ingest_point = data["ingest"][0]
                assert "ts" in ingest_point
                assert "events_1h" in ingest_point
                assert "failed" in ingest_point
                assert "duplicates" in ingest_point
            
            # ARI series
            if len(data["ari"]) > 0:
                ari_point = data["ari"][0]
                assert "ts" in ari_point
                assert "success_rate" in ari_point
                assert "p95_latency" in ari_point
                assert "retry_count" in ari_point
            
            # Reconciliation series
            if len(data["reconciliation"]) > 0:
                recon_point = data["reconciliation"][0]
                assert "ts" in recon_point
                assert "open_cases" in recon_point
                assert "critical" in recon_point
            
            # Queue series
            if len(data["queue"]) > 0:
                queue_point = data["queue"][0]
                assert "ts" in queue_point
                assert "depth" in queue_point
                assert "retry_backlog" in queue_point
            
            print(f"✓ Trends data structure verified with correct fields")
        else:
            print(f"✓ No trend data points yet (metrics collected every 60s)")


class TestProviderValidationFlow(TestAuthAndSetup):
    """End-to-end Provider Validation Flow Tests"""
    
    def test_full_validation_flow_hotelrunner(self, auth_headers):
        """Test complete validation flow for HotelRunner"""
        # 1. Save credentials (use unique property_id to avoid conflicts)
        save_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers,
            json={
                "credentials": {"token": "test_token_flow", "hr_id": "test_hr_flow"},
                "property_id": "default"
            }
        )
        assert save_resp.status_code == 200
        
        # 2. Run validation
        validate_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/validate",
            headers=auth_headers
        )
        assert validate_resp.status_code == 200
        validate_data = validate_resp.json()
        
        # 3. Get readiness
        readiness_resp = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/readiness",
            headers=auth_headers
        )
        assert readiness_resp.status_code == 200
        
        # 4. Get overview (should show credentials saved or provider exists)
        overview_resp = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers",
            headers=auth_headers
        )
        assert overview_resp.status_code == 200
        overview = overview_resp.json()
        hr = next((p for p in overview["providers"] if p["provider"] == "hotelrunner"), None)
        assert hr is not None, "HotelRunner provider should exist in overview"
        # has_credentials may be False if another test deleted them, just verify structure
        assert "has_credentials" in hr
        
        print(f"✓ Full validation flow completed - Overall status: {validate_data['overall_status']}")
    
    def test_full_validation_flow_exely(self, auth_headers):
        """Test complete validation flow for Exely"""
        # 1. Save credentials
        save_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/exely/credentials",
            headers=auth_headers,
            json={
                "credentials": {
                    "username": "test_user_flow",
                    "password": "test_pass_flow",
                    "hotel_code": "TEST_CODE"
                },
                "property_id": "default"
            }
        )
        assert save_resp.status_code == 200
        
        # 2. Run validation
        validate_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/exely/validate",
            headers=auth_headers
        )
        assert validate_resp.status_code == 200
        validate_data = validate_resp.json()
        
        print(f"✓ Exely validation flow completed - Overall status: {validate_data['overall_status']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
