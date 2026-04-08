"""
P2 Field Encryption Tests - Testing 100% encryption coverage for users and bookings collections.

Tests:
- Auth login with encrypted email lookups (hash-based dual-read)
- GET /api/auth/me returns decrypted email
- GET /api/ops/field-encryption/status shows 100% coverage
- GET /api/pms/guests returns decrypted fields
- GET /api/pms/bookings returns booking list without errors
- POST /api/auth/login with wrong password returns 401
- POST /api/ops/field-encryption/migrate-all reports 0 unencrypted
- GET /api/admin/users returns decrypted user list
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://channel-sync-hub-2.preview.emergentagent.com"


class TestAuthLoginEncryption:
    """Test auth login with encrypted email lookups."""

    def test_login_demo_user_success(self):
        """POST /api/auth/login with demo@hotel.com / demo123 returns access_token with correct email."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify access_token is present
        assert "access_token" in data, "access_token missing from response"
        assert len(data["access_token"]) > 0, "access_token is empty"
        
        # Verify user email is decrypted correctly
        assert "user" in data, "user object missing from response"
        user = data["user"]
        assert user.get("email") == "demo@hotel.com", f"Email mismatch: expected demo@hotel.com, got {user.get('email')}"
        
        print(f"✓ Login successful for demo@hotel.com, token length: {len(data['access_token'])}")

    def test_login_frontdesk_user_success(self):
        """POST /api/auth/login with frontdesk@hotel.com / staff123 returns access_token with correct email."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "frontdesk@hotel.com", "password": "staff123"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify access_token is present
        assert "access_token" in data, "access_token missing from response"
        assert len(data["access_token"]) > 0, "access_token is empty"
        
        # Verify user email is decrypted correctly
        assert "user" in data, "user object missing from response"
        user = data["user"]
        assert user.get("email") == "frontdesk@hotel.com", f"Email mismatch: expected frontdesk@hotel.com, got {user.get('email')}"
        
        print(f"✓ Login successful for frontdesk@hotel.com, role: {user.get('role')}")

    def test_login_wrong_password_returns_401(self):
        """POST /api/auth/login with wrong password returns 401."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "wrongpassword"},
            timeout=30,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ Wrong password correctly returns 401")


class TestAuthMeDecryption:
    """Test GET /api/auth/me returns decrypted user data."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for demo user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_auth_me_returns_decrypted_email(self, auth_token):
        """GET /api/auth/me with valid token returns decrypted email (demo@hotel.com)."""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"GET /api/auth/me failed: {response.text}"
        data = response.json()
        
        # Verify email is decrypted (not encrypted with aes256gcm: prefix)
        email = data.get("email", "")
        assert email == "demo@hotel.com", f"Email mismatch: expected demo@hotel.com, got {email}"
        assert not email.startswith("aes256gcm:"), f"Email is still encrypted: {email}"
        assert not email.startswith("SYR1:"), f"Email is still encrypted: {email}"
        
        print(f"✓ GET /api/auth/me returns decrypted email: {email}")


class TestFieldEncryptionStatus:
    """Test field encryption status endpoint shows 100% coverage."""

    @pytest.fixture
    def admin_token(self):
        """Get auth token for admin user (demo@hotel.com is super_admin)."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_encryption_status_shows_100_percent_coverage(self, admin_token):
        """GET /api/ops/field-encryption/status shows guests, users, bookings at 100% coverage."""
        response = requests.get(
            f"{BASE_URL}/api/ops/field-encryption/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"GET encryption status failed: {response.text}"
        data = response.json()
        
        assert "collections" in data, "collections field missing from response"
        collections = data["collections"]
        
        # Check guests collection
        if "guests" in collections:
            guests_coverage = collections["guests"].get("coverage_percent", 0)
            print(f"  guests coverage: {guests_coverage}%")
            # Allow some tolerance for newly created documents
            assert guests_coverage >= 99, f"guests coverage too low: {guests_coverage}%"
        
        # Check users collection
        if "users" in collections:
            users_coverage = collections["users"].get("coverage_percent", 0)
            print(f"  users coverage: {users_coverage}%")
            assert users_coverage >= 99, f"users coverage too low: {users_coverage}%"
        
        # Check bookings collection
        if "bookings" in collections:
            bookings_coverage = collections["bookings"].get("coverage_percent", 0)
            print(f"  bookings coverage: {bookings_coverage}%")
            assert bookings_coverage >= 99, f"bookings coverage too low: {bookings_coverage}%"
        
        print("✓ Field encryption status shows high coverage for all collections")


class TestMigrateAll:
    """Test migrate-all endpoint reports 0 unencrypted documents."""

    @pytest.fixture
    def admin_token(self):
        """Get auth token for admin user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_migrate_all_reports_zero_unencrypted(self, admin_token):
        """POST /api/ops/field-encryption/migrate-all should report 0 unencrypted documents."""
        response = requests.post(
            f"{BASE_URL}/api/ops/field-encryption/migrate-all",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,  # Migration can take time
        )
        assert response.status_code == 200, f"migrate-all failed: {response.text}"
        data = response.json()
        
        assert "migrations" in data, "migrations field missing from response"
        migrations = data["migrations"]
        
        total_unencrypted = 0
        for collection_name, result in migrations.items():
            unencrypted = result.get("total_unencrypted", 0)
            total_unencrypted += unencrypted
            print(f"  {collection_name}: {unencrypted} unencrypted documents")
        
        # All collections should have 0 unencrypted documents
        assert total_unencrypted == 0, f"Found {total_unencrypted} unencrypted documents"
        print("✓ migrate-all reports 0 unencrypted documents")


class TestPMSGuestsDecryption:
    """Test GET /api/pms/guests returns decrypted guest fields."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for demo user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_pms_guests_returns_decrypted_fields(self, auth_token):
        """GET /api/pms/guests returns guest list with decrypted fields."""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests?limit=10",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"GET /api/pms/guests failed: {response.text}"
        guests = response.json()
        
        # Should return a list
        assert isinstance(guests, list), f"Expected list, got {type(guests)}"
        
        if len(guests) > 0:
            # Check first guest has decrypted fields
            guest = guests[0]
            
            # Check email is not encrypted
            email = guest.get("email", "")
            if email:
                assert not email.startswith("aes256gcm:"), f"Guest email is still encrypted: {email}"
                assert not email.startswith("SYR1:"), f"Guest email is still encrypted: {email}"
            
            # Check phone is not encrypted
            phone = guest.get("phone", "")
            if phone:
                assert not phone.startswith("aes256gcm:"), f"Guest phone is still encrypted: {phone}"
                assert not phone.startswith("SYR1:"), f"Guest phone is still encrypted: {phone}"
            
            print(f"✓ GET /api/pms/guests returns {len(guests)} guests with decrypted fields")
        else:
            print("✓ GET /api/pms/guests returns empty list (no guests in tenant)")


class TestPMSBookings:
    """Test GET /api/pms/bookings returns booking list without errors."""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for demo user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_pms_bookings_returns_without_errors(self, auth_token):
        """GET /api/pms/bookings?limit=5 returns booking list without errors."""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings?limit=5",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"GET /api/pms/bookings failed: {response.text}"
        data = response.json()
        
        # Response can be a list or dict with bookings key
        if isinstance(data, list):
            bookings = data
        elif isinstance(data, dict):
            bookings = data.get("bookings", [])
        else:
            pytest.fail(f"Unexpected response type: {type(data)}")
        
        print(f"✓ GET /api/pms/bookings returns {len(bookings)} bookings without errors")


class TestAdminUsersDecryption:
    """Test GET /api/admin/users returns decrypted user list."""

    @pytest.fixture
    def admin_token(self):
        """Get auth token for admin user (demo@hotel.com is super_admin)."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30,
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]

    def test_admin_users_returns_decrypted_list(self, admin_token):
        """GET /api/admin/users returns decrypted user list (admin access)."""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert response.status_code == 200, f"GET /api/admin/users failed: {response.text}"
        data = response.json()
        
        assert "users" in data, "users field missing from response"
        users = data["users"]
        
        if len(users) > 0:
            # Check first user has decrypted email
            user = users[0]
            email = user.get("email", "")
            
            if email:
                assert not email.startswith("aes256gcm:"), f"User email is still encrypted: {email}"
                assert not email.startswith("SYR1:"), f"User email is still encrypted: {email}"
            
            # Check phone is not encrypted
            phone = user.get("phone", "")
            if phone:
                assert not phone.startswith("aes256gcm:"), f"User phone is still encrypted: {phone}"
                assert not phone.startswith("SYR1:"), f"User phone is still encrypted: {phone}"
            
            print(f"✓ GET /api/admin/users returns {len(users)} users with decrypted fields")
        else:
            print("✓ GET /api/admin/users returns empty list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
