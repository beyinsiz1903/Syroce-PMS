"""
Test Suite: AWS KMS / Vault Integration + PII Masking for Hotel PMS
=====================================================================
Tests for:
- POST /api/auth/login — login still works, returns access_token
- GET /api/ops/pii/policy — returns PII policy with 31+ fields and categories
- GET /api/ops/secrets/classification — returns 7 secret type classifications
- GET /api/ops/secrets/inventory — returns classified secret inventory
- GET /api/ops/kms/status — returns KMS status (unavailable in dev)
- GET /api/ops/pii/audit — returns PII audit trail
- GET /api/ops/pii/anomalies — returns anomaly detection results
- GET /api/ops/pii/metrics — returns PII metrics with field counts
- GET /api/pms/guests — guest data still returned correctly
- GET /api/ops/secrets/status — secrets subsystem health status
- PII masking logic — verify mask_dict masks email/phone/identity correctly
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestAuthLogin:
    """Test authentication endpoint returns access_token."""

    def test_login_returns_access_token(self):
        """POST /api/auth/login should return access_token (not 'token')."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify access_token is returned (not 'token')
        assert "access_token" in data, f"Expected 'access_token' in response, got: {data.keys()}"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        
        # Verify user info
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        assert data["user"]["role"] == "super_admin"
        print(f"Login successful: access_token received, user role={data['user']['role']}")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for protected endpoints."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/json"},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with Bearer token for authenticated requests."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


class TestPIIPolicy:
    """Test PII policy endpoint returns 31+ fields with categories."""

    def test_pii_policy_returns_fields(self, auth_headers):
        """GET /api/ops/pii/policy should return PII policy with 31+ fields."""
        response = requests.get(
            f"{BASE_URL}/api/ops/pii/policy",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"PII policy failed: {response.text}"
        data = response.json()
        
        # Verify policy structure
        assert "policy" in data
        policy = data["policy"]
        
        # Verify total_pii_fields >= 31
        assert "total_pii_fields" in policy
        assert policy["total_pii_fields"] >= 31, f"Expected 31+ PII fields, got {policy['total_pii_fields']}"
        
        # Verify categories exist
        assert "categories" in policy
        categories = policy["categories"]
        expected_categories = ["identity", "contact", "financial", "authentication"]
        for cat in expected_categories:
            assert cat in categories, f"Missing category: {cat}"
        
        # Verify masking_levels
        assert "masking_levels" in policy
        assert "full" in policy["masking_levels"]
        assert "partial" in policy["masking_levels"]
        
        # Verify secret_lifecycle
        assert "secret_lifecycle" in policy
        
        print(f"PII Policy: {policy['total_pii_fields']} fields, categories: {list(categories.keys())}")


class TestSecretsClassification:
    """Test secrets classification endpoint returns 7 secret types."""

    def test_secrets_classification_returns_7_types(self, auth_headers):
        """GET /api/ops/secrets/classification should return 7 secret types."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/classification",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Secrets classification failed: {response.text}"
        data = response.json()
        
        # Verify classification structure
        assert "classification" in data
        classification = data["classification"]
        
        # Verify 7 secret types
        expected_types = [
            "jwt_app", "connector", "webhook", "encryption",
            "third_party", "database", "internal"
        ]
        assert len(classification) == 7, f"Expected 7 secret types, got {len(classification)}"
        
        for secret_type in expected_types:
            assert secret_type in classification, f"Missing secret type: {secret_type}"
            # Verify lifecycle rules exist
            assert "lifecycle" in classification[secret_type]
            lifecycle = classification[secret_type]["lifecycle"]
            assert "rotation_max_days" in lifecycle
            assert "auto_rotation" in lifecycle
        
        # Verify metadata
        assert "policy_version" in data
        assert "enforcement" in data
        assert data["enforcement"] == "active"
        
        print(f"Secrets Classification: {len(classification)} types, enforcement={data['enforcement']}")


class TestSecretsInventory:
    """Test secrets inventory endpoint returns classified inventory."""

    def test_secrets_inventory_returns_inventory(self, auth_headers):
        """GET /api/ops/secrets/inventory should return classified inventory."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/inventory",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Secrets inventory failed: {response.text}"
        data = response.json()
        
        # Verify inventory structure
        assert "inventory" in data
        inventory = data["inventory"]
        
        # Verify all 7 secret types are present
        expected_types = [
            "jwt_app", "connector", "webhook", "encryption",
            "third_party", "database", "internal"
        ]
        for secret_type in expected_types:
            assert secret_type in inventory, f"Missing inventory type: {secret_type}"
            assert "count" in inventory[secret_type]
            assert "items" in inventory[secret_type]
        
        # Verify total_secrets
        assert "total_secrets" in data
        assert isinstance(data["total_secrets"], int)
        
        # Verify environment
        assert "environment" in data
        
        print(f"Secrets Inventory: {data['total_secrets']} total secrets, env={data['environment']}")


class TestKMSStatus:
    """Test KMS status endpoint returns status (unavailable in dev)."""

    def test_kms_status_returns_status(self, auth_headers):
        """GET /api/ops/kms/status should return KMS status."""
        response = requests.get(
            f"{BASE_URL}/api/ops/kms/status",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"KMS status failed: {response.text}"
        data = response.json()
        
        # Verify status structure
        assert "provider" in data
        assert data["provider"] == "kms"
        
        assert "status" in data
        # In dev environment, KMS is expected to be unavailable
        assert data["status"] in ["unavailable", "healthy", "unhealthy"]
        
        # Verify envelope_format
        assert "envelope_format" in data
        assert data["envelope_format"] == "KMS1:"
        
        # Verify config
        assert "config" in data
        assert "key_arn_configured" in data["config"]
        
        print(f"KMS Status: provider={data['provider']}, status={data['status']}")


class TestPIIAudit:
    """Test PII audit trail endpoint."""

    def test_pii_audit_returns_trail(self, auth_headers):
        """GET /api/ops/pii/audit should return audit trail (empty initially)."""
        response = requests.get(
            f"{BASE_URL}/api/ops/pii/audit",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"PII audit failed: {response.text}"
        data = response.json()
        
        # Verify audit structure
        assert "items" in data
        assert isinstance(data["items"], list)
        
        assert "total" in data
        assert isinstance(data["total"], int)
        
        assert "limit" in data
        assert "skip" in data
        
        print(f"PII Audit: {data['total']} total items, returned {len(data['items'])}")


class TestPIIAnomalies:
    """Test PII anomaly detection endpoint."""

    def test_pii_anomalies_returns_results(self, auth_headers):
        """GET /api/ops/pii/anomalies should return anomaly detection results."""
        response = requests.get(
            f"{BASE_URL}/api/ops/pii/anomalies",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"PII anomalies failed: {response.text}"
        data = response.json()
        
        # Verify anomalies structure
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)
        
        assert "window_hours" in data
        assert data["window_hours"] == 24  # default
        
        assert "threshold" in data
        
        print(f"PII Anomalies: {len(data['anomalies'])} anomalies detected, window={data['window_hours']}h")


class TestPIIMetrics:
    """Test PII metrics endpoint."""

    def test_pii_metrics_returns_field_counts(self, auth_headers):
        """GET /api/ops/pii/metrics should return PII metrics with field counts."""
        response = requests.get(
            f"{BASE_URL}/api/ops/pii/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"PII metrics failed: {response.text}"
        data = response.json()
        
        # Verify metrics structure
        assert "middleware" in data
        assert data["middleware"] == "active"
        
        assert "pii_fields_registered" in data
        assert data["pii_fields_registered"] >= 31
        
        assert "categories" in data
        categories = data["categories"]
        assert "identity" in categories
        assert "contact" in categories
        assert "financial" in categories
        assert "authentication" in categories
        
        print(f"PII Metrics: {data['pii_fields_registered']} fields, categories={categories}")


class TestGuestsEndpoint:
    """Test guests endpoint still works after middleware changes."""

    def test_guests_endpoint_returns_data(self, auth_headers):
        """GET /api/pms/guests should return guest data correctly."""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Guests endpoint failed: {response.text}"
        data = response.json()
        
        # Verify response is a list or has items
        if isinstance(data, list):
            print(f"Guests: returned {len(data)} guests")
        elif isinstance(data, dict):
            if "items" in data:
                print(f"Guests: returned {len(data['items'])} guests")
            elif "guests" in data:
                print(f"Guests: returned {len(data['guests'])} guests")
            else:
                print(f"Guests: response keys={list(data.keys())}")
        
        # Endpoint should not error
        assert response.status_code == 200


class TestSecretsStatus:
    """Test secrets subsystem health status endpoint."""

    def test_secrets_status_endpoint(self, auth_headers):
        """GET /api/ops/secrets/status should return secrets subsystem health."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/status",
            headers=auth_headers,
        )
        # This endpoint may or may not exist - check gracefully
        if response.status_code == 404:
            pytest.skip("Secrets status endpoint not implemented")
        
        assert response.status_code == 200, f"Secrets status failed: {response.text}"
        data = response.json()
        print(f"Secrets Status: {data}")


class TestPIIMaskingLogic:
    """Test PII masking logic directly via mask_dict function."""

    def test_mask_dict_masks_email_for_anonymous(self):
        """mask_dict should mask email for anonymous users."""
        from security.pii_registry import mask_dict
        
        data = {"email": "test@example.com", "name": "John Doe"}
        masked = mask_dict(data, user_role="", context="api")
        
        # Email should be partially masked
        assert masked["email"] != "test@example.com"
        assert "***" in masked["email"] or "REDACTED" in masked["email"]
        # Name is not PII, should remain
        assert masked["name"] == "John Doe"
        print(f"Masked email: {masked['email']}")

    def test_mask_dict_masks_phone_for_anonymous(self):
        """mask_dict should mask phone for anonymous users."""
        from security.pii_registry import mask_dict
        
        data = {"phone": "+905551234567", "status": "active"}
        masked = mask_dict(data, user_role="", context="api")
        
        # Phone should be partially masked (last 4 visible)
        assert masked["phone"] != "+905551234567"
        assert "***" in masked["phone"] or "REDACTED" in masked["phone"] or masked["phone"].endswith("4567")
        # Status is not PII
        assert masked["status"] == "active"
        print(f"Masked phone: {masked['phone']}")

    def test_mask_dict_masks_identity_for_anonymous(self):
        """mask_dict should mask identity fields for anonymous users."""
        from security.pii_registry import mask_dict
        
        data = {"tc_kimlik": "12345678901", "passport_number": "AB1234567"}
        masked = mask_dict(data, user_role="", context="api")
        
        # Identity fields should be fully masked
        assert masked["tc_kimlik"] == "***REDACTED***"
        assert masked["passport_number"] == "***REDACTED***"
        print(f"Masked identity: tc_kimlik={masked['tc_kimlik']}, passport={masked['passport_number']}")

    def test_mask_dict_unmasks_for_admin(self):
        """mask_dict should unmask email/phone for admin role."""
        from security.pii_registry import mask_dict
        
        data = {"email": "test@example.com", "phone": "+905551234567"}
        masked = mask_dict(data, user_role="admin", context="api")
        
        # Admin should see unmasked email and phone
        assert masked["email"] == "test@example.com"
        assert masked["phone"] == "+905551234567"
        print(f"Admin sees: email={masked['email']}, phone={masked['phone']}")

    def test_mask_dict_unmasks_for_super_admin(self):
        """mask_dict should unmask all fields for super_admin role."""
        from security.pii_registry import mask_dict
        
        data = {
            "email": "test@example.com",
            "phone": "+905551234567",
            "tc_kimlik": "12345678901",
        }
        masked = mask_dict(data, user_role="super_admin", context="api")
        
        # Super admin should see all unmasked
        assert masked["email"] == "test@example.com"
        assert masked["phone"] == "+905551234567"
        assert masked["tc_kimlik"] == "12345678901"
        print(f"Super admin sees all unmasked")

    def test_mask_dict_always_masks_passwords(self):
        """mask_dict should always mask passwords regardless of role."""
        from security.pii_registry import mask_dict
        
        data = {"password": "secret123", "hashed_password": "hash123"}
        
        # Even super_admin cannot see passwords
        masked = mask_dict(data, user_role="super_admin", context="api")
        assert masked["password"] == "***REDACTED***"
        assert masked["hashed_password"] == "***REDACTED***"
        print(f"Passwords always masked: {masked}")

    def test_mask_dict_handles_nested_data(self):
        """mask_dict should handle nested dictionaries."""
        from security.pii_registry import mask_dict
        
        data = {
            "guest": {
                "email": "guest@example.com",
                "phone": "+905551234567",
            },
            "booking_id": "12345",
        }
        masked = mask_dict(data, user_role="", context="api")
        
        # Nested email/phone should be masked
        assert masked["guest"]["email"] != "guest@example.com"
        assert masked["guest"]["phone"] != "+905551234567"
        # Non-PII should remain
        assert masked["booking_id"] == "12345"
        print(f"Nested masking works: {masked}")


class TestScrubText:
    """Test scrub_text function for free-text PII detection."""

    def test_scrub_text_removes_email(self):
        """scrub_text should remove email patterns from text."""
        from security.pii_registry import scrub_text
        
        text = "Contact user at test@example.com for details"
        scrubbed = scrub_text(text)
        
        assert "test@example.com" not in scrubbed
        assert "***EMAIL***" in scrubbed
        print(f"Scrubbed: {scrubbed}")

    def test_scrub_text_removes_jwt(self):
        """scrub_text should remove JWT tokens from text."""
        from security.pii_registry import scrub_text
        
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIn0.abc123"
        text = f"Token: {jwt}"
        scrubbed = scrub_text(text)
        
        assert jwt not in scrubbed
        assert "***JWT***" in scrubbed
        print(f"JWT scrubbed: {scrubbed}")

    def test_scrub_text_removes_credit_card(self):
        """scrub_text should remove credit card patterns from text."""
        from security.pii_registry import scrub_text
        
        text = "Card: 4111-1111-1111-1111"
        scrubbed = scrub_text(text)
        
        assert "4111-1111-1111-1111" not in scrubbed
        assert "***CARD***" in scrubbed
        print(f"Card scrubbed: {scrubbed}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
