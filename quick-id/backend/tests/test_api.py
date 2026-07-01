"""
Quick ID Reader - API Entegrasyon Testleri
Tüm endpoint'lerin HTTP düzeyinde testi

Kullanım: cd /app/backend && python -m pytest tests/test_api.py -v
"""
import pytest
import asyncio
import httpx
import os
import sys

# Backend URL
BASE_URL = "http://localhost:8001"

# Test credentials
ADMIN_EMAIL = "admin@quickid.com"
ADMIN_PASSWORD = "admin123"
RECEPTION_EMAIL = "resepsiyon@quickid.com"
RECEPTION_PASSWORD = "resepsiyon123"


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def admin_token():
    """Admin JWT token al"""
    import httpx as httpx_sync
    with httpx_sync.Client(base_url=BASE_URL) as client:
        res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert res.status_code == 200
        return res.json()["token"]


@pytest.fixture(scope="module")
def reception_token():
    """Resepsiyon JWT token al"""
    import httpx as httpx_sync
    with httpx_sync.Client(base_url=BASE_URL) as client:
        res = client.post("/api/auth/login", json={"email": RECEPTION_EMAIL, "password": RECEPTION_PASSWORD})
        assert res.status_code == 200
        return res.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============== Health & Public Tests ==============

class TestHealth:
    """Sağlık kontrol testleri"""

    def test_health(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/health")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "healthy"
            assert "version" in data

    def test_rate_limits(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/rate-limits")
            assert res.status_code == 200
            data = res.json()
            assert "limits" in data

    def test_api_guide(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guide")
            assert res.status_code == 200
            data = res.json()
            assert "title" in data
            assert "endpoints" in data
            assert "authentication" in data
            assert "pms_integration_guide" in data


# ============== Auth Tests ==============

class TestAuthAPI:
    """Kimlik doğrulama API testleri"""

    def test_login_admin(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            assert res.status_code == 200
            data = res.json()
            assert "token" in data
            assert data["user"]["role"] == "admin"

    def test_login_reception(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.post("/api/auth/login", json={"email": RECEPTION_EMAIL, "password": RECEPTION_PASSWORD})
            assert res.status_code == 200
            data = res.json()
            assert data["user"]["role"] == "reception"

    def test_login_invalid(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.post("/api/auth/login", json={"email": "wrong@test.com", "password": "wrong"})
            assert res.status_code == 401

    def test_get_me(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/auth/me", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert data["user"]["email"] == ADMIN_EMAIL

    def test_unauthorized_access(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests", headers={"Content-Type": "application/json"})
            assert res.status_code == 401

    def test_invalid_token(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests", headers=auth_headers("invalid.token"))
            assert res.status_code == 401


# ============== User Management Tests ==============

class TestUserManagement:
    """Kullanıcı yönetimi API testleri"""

    def test_list_users_admin(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/users", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "users" in data
            assert data["total"] >= 2

    def test_list_users_reception_denied(self, reception_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/users", headers=auth_headers(reception_token))
            assert res.status_code == 403


# ============== Guest Tests ==============

class TestGuestAPI:
    """Misafir yönetimi API testleri"""

    def test_list_guests(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "guests" in data
            assert "total" in data

    def test_create_and_manage_guest(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            # Create
            guest_data = {
                "first_name": "Test",
                "last_name": "Misafir",
                "id_number": "99999999999",
                "birth_date": "1990-05-15",
                "gender": "M",
                "nationality": "TC",
                "document_type": "tc_kimlik",
                "kvkk_consent": True,
                "force_create": True
            }
            res = client.post("/api/guests", json=guest_data, headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            guest_id = data["guest"]["id"]

            # Get
            res = client.get(f"/api/guests/{guest_id}", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["guest"]["first_name"] == "Test"

            # Update
            res = client.patch(f"/api/guests/{guest_id}",
                             json={"first_name": "TestUpdated"},
                             headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["guest"]["first_name"] == "TestUpdated"

            # Check-in
            res = client.post(f"/api/guests/{guest_id}/checkin", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["guest"]["status"] == "checked_in"

            # Check-out
            res = client.post(f"/api/guests/{guest_id}/checkout", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["guest"]["status"] == "checked_out"

            # Audit trail
            res = client.get(f"/api/guests/{guest_id}/audit", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert len(res.json()["audit_logs"]) > 0

            # Delete
            res = client.delete(f"/api/guests/{guest_id}", headers=auth_headers(admin_token))
            assert res.status_code == 200

    def test_duplicate_detection(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            # Create first guest
            guest_data = {
                "first_name": "Duplicate",
                "last_name": "Test",
                "id_number": "88888888888",
                "force_create": True,
                "kvkk_consent": True
            }
            res = client.post("/api/guests", json=guest_data, headers=auth_headers(admin_token))
            assert res.status_code == 200
            guest_id = res.json()["guest"]["id"]

            # Try creating duplicate (without force)
            dup_data = {
                "first_name": "Duplicate",
                "last_name": "Test",
                "id_number": "88888888888",
            }
            res = client.post("/api/guests", json=dup_data, headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert data.get("duplicate_detected") is True

            # Check duplicate endpoint
            res = client.get("/api/guests/check-duplicate?id_number=88888888888",
                           headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["has_duplicates"] is True

            # Cleanup
            client.delete(f"/api/guests/{guest_id}", headers=auth_headers(admin_token))

    def test_guest_search(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests?search=nonexistent&page=1&limit=10",
                           headers=auth_headers(admin_token))
            assert res.status_code == 200

    def test_guest_status_filter(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests?status=pending",
                           headers=auth_headers(admin_token))
            assert res.status_code == 200

    def test_invalid_guest_id(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/guests/invalid-id", headers=auth_headers(admin_token))
            assert res.status_code == 400


# ============== KVKK Settings Tests ==============

class TestKvkkSettingsAPI:
    """KVKK ayarları API testleri"""

    def test_get_settings(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/settings/kvkk", headers=auth_headers(admin_token))
            assert res.status_code == 200
            settings = res.json()["settings"]
            assert "retention_days_scans" in settings
            assert "kvkk_consent_required" in settings
            assert "kvkk_consent_text" in settings

    def test_update_settings_admin(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.patch("/api/settings/kvkk",
                             json={"retention_days_scans": 60},
                             headers=auth_headers(admin_token))
            assert res.status_code == 200
            # Restore
            client.patch("/api/settings/kvkk",
                        json={"retention_days_scans": 90},
                        headers=auth_headers(admin_token))

    def test_update_settings_reception_denied(self, reception_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.patch("/api/settings/kvkk",
                             json={"retention_days_scans": 60},
                             headers=auth_headers(reception_token))
            assert res.status_code == 403


# ============== KVKK Compliance Tests ==============

class TestKvkkComplianceAPI:
    """KVKK uyumluluk API testleri"""

    def test_create_rights_request(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.post("/api/kvkk/rights-request",
                            json={
                                "request_type": "access",
                                "requester_name": "Test Kullanıcı",
                                "requester_email": "test@test.com",
                                "description": "Verilerime erişim istiyorum"
                            },
                            headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["request"]["request_type"] == "access"
            assert data["request"]["status"] == "pending"

    def test_list_rights_requests(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/kvkk/rights-requests", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert "requests" in res.json()

    def test_process_rights_request(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            # Create request first
            create_res = client.post("/api/kvkk/rights-request",
                                   json={
                                       "request_type": "erasure",
                                       "requester_name": "İşlenecek Test",
                                       "requester_email": "process@test.com",
                                       "description": "Silme talebi"
                                   },
                                   headers=auth_headers(admin_token))
            request_id = create_res.json()["request"]["request_id"]

            # Process it
            res = client.patch(f"/api/kvkk/rights-requests/{request_id}",
                             json={
                                 "status": "completed",
                                 "response_note": "Talep işlendi ve veriler silindi"
                             },
                             headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert res.json()["request"]["status"] == "completed"

    def test_invalid_request_type(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.post("/api/kvkk/rights-request",
                            json={
                                "request_type": "invalid_type",
                                "requester_name": "Test",
                                "requester_email": "t@t.com",
                                "description": "Test"
                            },
                            headers=auth_headers(admin_token))
            assert res.status_code == 400

    def test_verbis_report(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/kvkk/verbis-report", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "veri_kategorileri" in data
            assert "teknik_tedbirler" in data
            assert "istatistikler" in data
            assert "uyumluluk_durumu" in data

    def test_data_inventory(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/kvkk/data-inventory", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "koleksiyonlar" in data
            assert "veri_akisi" in data
            assert len(data["koleksiyonlar"]) >= 4

    def test_retention_warnings(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/kvkk/retention-warnings", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "warnings" in data
            assert "total_warnings" in data

    def test_reception_cannot_access_kvkk_admin(self, reception_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/kvkk/rights-requests", headers=auth_headers(reception_token))
            assert res.status_code == 403

            res = client.get("/api/kvkk/verbis-report", headers=auth_headers(reception_token))
            assert res.status_code == 403


# ============== Dashboard Tests ==============

class TestDashboardAPI:
    """Dashboard API testleri"""

    def test_dashboard_stats(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/dashboard/stats", headers=auth_headers(admin_token))
            assert res.status_code == 200
            data = res.json()
            assert "total_guests" in data
            assert "today_checkins" in data
            assert "weekly_stats" in data


# ============== Export Tests ==============

class TestExportAPI:
    """Dışa aktarım API testleri"""

    def test_export_json(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/exports/guests.json", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert "guests" in res.json()

    def test_export_csv(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/exports/guests.csv", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert "text/csv" in res.headers.get("content-type", "")


# ============== Audit Tests ==============

class TestAuditAPI:
    """Denetim izi API testleri"""

    def test_recent_audit(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/audit/recent?limit=10", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert "audit_logs" in res.json()


# ============== Scan Review Queue Tests ==============

class TestReviewQueueAPI:
    """Tarama inceleme kuyruğu API testleri"""

    def test_review_queue(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/scans/review-queue", headers=auth_headers(admin_token))
            assert res.status_code == 200
            assert "scans" in res.json()

    def test_review_queue_filtered(self, admin_token):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/scans/review-queue?review_status=auto_approved",
                           headers=auth_headers(admin_token))
            assert res.status_code == 200


# ============== OpenAPI Docs Tests ==============

class TestOpenAPIDocs:
    """API dokümantasyon erişim testleri"""

    def test_openapi_json(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/openapi.json")
            assert res.status_code == 200
            data = res.json()
            assert "openapi" in data
            assert "paths" in data
            assert "info" in data

    def test_swagger_docs(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/docs")
            assert res.status_code == 200

    def test_redoc(self):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/redoc")
            assert res.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
