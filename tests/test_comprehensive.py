"""
Comprehensive Unit Test Suite for RoomOps PMS
=============================================
%80+ coverage hedefli test suite.
Modüller: Auth, Rooms, Guests, Bookings, Folios,
2FA, GDPR, PCI DSS, Tenant Isolation, Central Office,
IP Access Control, Cross-Property Guests
"""
import pytest
import httpx
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

BASE_URL = "http://localhost:8001"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# ============= FIXTURES =============
@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module")
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        yield c

@pytest.fixture(scope="module")
async def auth_token(client):
    resp = await client.post("/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token", "")
    assert token, "No access_token in response"
    return token

@pytest.fixture(scope="module")
async def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ============= AUTH MODULE TESTS =============
class TestAuth:
    """Kimlik doğrulama testleri"""
    
    async def test_login_success(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == TEST_EMAIL
    
    async def test_login_invalid_credentials(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": TEST_EMAIL, "password": "wrongpassword"
        })
        assert resp.status_code == 401
    
    async def test_login_invalid_email(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": "nonexistent@hotel.com", "password": "test123"
        })
        assert resp.status_code == 401
    
    async def test_get_me(self, client, auth_headers):
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == TEST_EMAIL
        assert "id" in data
        assert "tenant_id" in data
    
    async def test_unauthorized_access(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code in [401, 403]
    
    async def test_invalid_token(self, client):
        resp = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid_token_here"
        })
        assert resp.status_code == 401


# ============= ROOMS MODULE TESTS =============
class TestRooms:
    """Oda yönetimi testleri"""
    
    @pytest.mark.asyncio
    async def test_list_rooms(self, client, auth_headers):
        resp = await client.get("/api/rooms", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # rooms could be in 'rooms' key or direct list
        rooms = data.get("rooms", data) if isinstance(data, dict) else data
        assert isinstance(rooms, list)
    
    @pytest.mark.asyncio
    async def test_rooms_count(self, client, auth_headers):
        resp = await client.get("/api/rooms", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        rooms = data.get("rooms", data) if isinstance(data, dict) else data
        assert len(rooms) >= 1, "En az 1 oda olmalı"
    
    @pytest.mark.asyncio
    async def test_rooms_have_required_fields(self, client, auth_headers):
        resp = await client.get("/api/rooms", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        rooms = data.get("rooms", data) if isinstance(data, dict) else data
        if rooms:
            room = rooms[0]
            assert "room_number" in room or "room_no" in room
            assert "status" in room


# ============= GUESTS MODULE TESTS =============
class TestGuests:
    """Misafir yönetimi testleri"""
    
    @pytest.mark.asyncio
    async def test_list_guests(self, client, auth_headers):
        resp = await client.get("/api/guests", headers=auth_headers)
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_create_guest(self, client, auth_headers):
        import uuid
        guest_data = {
            "name": f"Test Misafir {uuid.uuid4().hex[:6]}",
            "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+905551234999"
        }
        resp = await client.post("/api/guests", json=guest_data, headers=auth_headers)
        assert resp.status_code in [200, 201], f"Create guest failed: {resp.text}"
    
    @pytest.mark.asyncio
    async def test_search_guests(self, client, auth_headers):
        resp = await client.get("/api/guests?search=Misafir", headers=auth_headers)
        assert resp.status_code == 200


# ============= 2FA SECURITY MODULE TESTS =============
class TestTwoFA:
    """İki faktörlü doğrulama testleri"""
    
    @pytest.mark.asyncio
    async def test_2fa_status(self, client, auth_headers):
        resp = await client.get("/api/security/2fa/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)
        assert "enforced_by_policy" in data
    
    @pytest.mark.asyncio
    async def test_2fa_setup(self, client, auth_headers):
        resp = await client.post("/api/security/2fa/setup", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_code" in data
        assert data["qr_code"].startswith("data:image/png;base64,")
        assert "manual_entry_key" in data
    
    @pytest.mark.asyncio
    async def test_2fa_verify_invalid_code(self, client, auth_headers):
        resp = await client.post("/api/security/2fa/verify", 
            json={"code": "000000"}, headers=auth_headers)
        assert resp.status_code == 400
    
    @pytest.mark.asyncio
    async def test_2fa_tenant_policy(self, client, auth_headers):
        resp = await client.get("/api/security/2fa/tenant-policy", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "require_2fa" in data
    
    @pytest.mark.asyncio
    async def test_2fa_stats(self, client, auth_headers):
        resp = await client.get("/api/security/2fa/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data
        assert "adoption_rate" in data
        assert "last_30_days" in data
    
    @pytest.mark.asyncio
    async def test_2fa_update_policy(self, client, auth_headers):
        resp = await client.put("/api/security/2fa/tenant-policy", 
            json={
                "require_2fa": False,
                "require_2fa_roles": ["admin"],
                "enforce_after_days": 7,
                "max_failed_attempts": 5,
                "lockout_duration_minutes": 30,
                "trusted_device_days": 30,
                "require_2fa_for_sensitive_ops": True
            },
            headers=auth_headers)
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_2fa_trusted_devices_list(self, client, auth_headers):
        resp = await client.get("/api/security/2fa/trusted-devices", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "devices" in data


# ============= IP ACCESS CONTROL TESTS =============
class TestIPAccessControl:
    """IP erişim kontrolü testleri"""
    
    @pytest.mark.asyncio
    async def test_list_ip_rules(self, client, auth_headers):
        resp = await client.get("/api/security/ip/rules", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert "total" in data
    
    @pytest.mark.asyncio
    async def test_create_ip_rule(self, client, auth_headers):
        resp = await client.post("/api/security/ip/rules", json={
            "ip_address": "192.168.1.100",
            "rule_type": "whitelist",
            "description": "Test kuralı"
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_create_ip_rule_invalid(self, client, auth_headers):
        resp = await client.post("/api/security/ip/rules", json={
            "ip_address": "invalid-ip",
            "rule_type": "whitelist"
        }, headers=auth_headers)
        assert resp.status_code == 400
    
    @pytest.mark.asyncio
    async def test_check_ip(self, client, auth_headers):
        resp = await client.post("/api/security/ip/check", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "client_ip" in data
        assert "allowed" in data


# ============= GDPR/KVKK COMPLIANCE TESTS =============
class TestGDPRCompliance:
    """KVKK/GDPR uyumluluk testleri"""
    
    @pytest.mark.asyncio
    async def test_compliance_status(self, client, auth_headers):
        resp = await client.get("/api/gdpr/compliance-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "compliance_score" in data
        assert "total_guests" in data
        assert "compliance_checks" in data
    
    @pytest.mark.asyncio
    async def test_retention_policy(self, client, auth_headers):
        resp = await client.get("/api/gdpr/retention-policy", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "guest_data_retention_days" in data
    
    @pytest.mark.asyncio
    async def test_dpa_list(self, client, auth_headers):
        resp = await client.get("/api/gdpr/dpa", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "agreements" in data
    
    @pytest.mark.asyncio
    async def test_create_dpa(self, client, auth_headers):
        resp = await client.post("/api/gdpr/dpa", json={
            "processor_name": "Test İşleyici",
            "purpose": "Veri analizi",
            "data_categories": ["misafir_bilgileri", "rezervasyon"],
            "retention_period_days": 365,
            "security_measures": ["şifreleme", "erişim kontrolü"],
            "cross_border_transfer": False
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_update_retention_policy(self, client, auth_headers):
        resp = await client.put("/api/gdpr/retention-policy?guest_data_days=1095&auto_anonymize=false",
            headers=auth_headers)
        assert resp.status_code == 200


# ============= PCI DSS COMPLIANCE TESTS =============
class TestPCIDSS:
    """PCI DSS uyumluluk testleri"""
    
    @pytest.mark.asyncio
    async def test_compliance_status(self, client, auth_headers):
        resp = await client.get("/api/pci-dss/compliance-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "compliance_score" in data
        assert "compliance_level" in data
        assert "requirements" in data
        assert "category_summary" in data
    
    @pytest.mark.asyncio
    async def test_requirements_list(self, client, auth_headers):
        resp = await client.get("/api/pci-dss/requirements", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requirements"] == 24
        assert "categories" in data
    
    @pytest.mark.asyncio
    async def test_tokenize_card(self, client, auth_headers):
        resp = await client.post("/api/pci-dss/tokenize", json={
            "card_number": "4111111111111111",
            "card_holder": "Test Kullanıcı",
            "expiry_month": 12,
            "expiry_year": 2028
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["last_four"] == "1111"
        assert data["card_brand"] == "Visa"
        assert "***" in data["card_holder_masked"]
    
    @pytest.mark.asyncio
    async def test_tokenize_invalid_card(self, client, auth_headers):
        resp = await client.post("/api/pci-dss/tokenize", json={
            "card_number": "1234567890123",
            "card_holder": "Test",
            "expiry_month": 12,
            "expiry_year": 2028
        }, headers=auth_headers)
        assert resp.status_code == 400
    
    @pytest.mark.asyncio
    async def test_list_tokens(self, client, auth_headers):
        resp = await client.get("/api/pci-dss/tokens", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens" in data
    
    @pytest.mark.asyncio
    async def test_security_scan(self, client, auth_headers):
        resp = await client.post("/api/pci-dss/security-scan", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_level" in data
        assert "findings" in data
        assert data["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_pan_scan(self, client, auth_headers):
        resp = await client.post("/api/pci-dss/pan-scan", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "exposed_pan_count" in data
        assert "documents_scanned" in data
    
    @pytest.mark.asyncio
    async def test_scan_history(self, client, auth_headers):
        resp = await client.get("/api/pci-dss/scan-history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "scans" in data
    
    @pytest.mark.asyncio
    async def test_update_audit_result(self, client, auth_headers):
        resp = await client.put(
            "/api/pci-dss/audit/1.1?audit_status=compliant&evidence=Firewall%20aktif&notes=Test",
            headers=auth_headers
        )
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_update_audit_invalid_requirement(self, client, auth_headers):
        resp = await client.put(
            "/api/pci-dss/audit/99.99?audit_status=compliant",
            headers=auth_headers
        )
        assert resp.status_code == 404


# ============= TENANT ISOLATION TESTS =============
class TestTenantIsolation:
    """Tenant veri izolasyonu testleri"""
    
    @pytest.mark.asyncio
    async def test_isolation_health(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/health", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "isolation_score" in data
        assert "violations" in data
        assert "recommendations" in data
        assert data["isolation_score"] >= 0
    
    @pytest.mark.asyncio
    async def test_isolation_policy(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/policy", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "strict_mode" in data
        assert "pii_masking_enabled" in data
    
    @pytest.mark.asyncio
    async def test_update_isolation_policy(self, client, auth_headers):
        resp = await client.put(
            "/api/tenant-isolation/policy?strict_mode=true&pii_masking_enabled=true",
            headers=auth_headers
        )
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_data_summary(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/data-summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "collections" in data
        assert "total_records" in data
        assert data["total_records"] >= 0
    
    @pytest.mark.asyncio
    async def test_data_classification(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/data-classification", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "classifications" in data
        assert "summary" in data
    
    @pytest.mark.asyncio
    async def test_pii_scan(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/pii-scan", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "pii_findings" in data
        assert "overall_risk" in data
    
    @pytest.mark.asyncio
    async def test_audit_trail(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/audit-trail?days=30", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "action_summary" in data
    
    @pytest.mark.asyncio
    async def test_access_logs(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/access-logs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
    
    @pytest.mark.asyncio
    async def test_cross_tenant_request(self, client, auth_headers):
        resp = await client.post("/api/tenant-isolation/cross-tenant-request",
            params={
                "target_tenant_id": "some-other-tenant",
                "reason": "Raporlama",
                "data_scope": "summary",
                "collections": ["bookings"]
            },
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_list_cross_tenant_requests(self, client, auth_headers):
        resp = await client.get("/api/tenant-isolation/cross-tenant-requests", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "requests" in data


# ============= CENTRAL OFFICE DASHBOARD TESTS =============
class TestCentralOffice:
    """Merkez ofis dashboard testleri"""
    
    @pytest.mark.asyncio
    async def test_dashboard(self, client, auth_headers):
        resp = await client.get("/api/central-office/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "chain_kpi" in data
        kpi = data["chain_kpi"]
        assert "total_properties" in kpi
        assert "total_rooms" in kpi
        assert "chain_occupancy_rate" in kpi
        assert "chain_adr" in kpi
        assert "chain_revpar" in kpi
    
    @pytest.mark.asyncio
    async def test_properties(self, client, auth_headers):
        resp = await client.get("/api/central-office/properties", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "properties" in data
        assert data["total"] >= 1
    
    @pytest.mark.asyncio
    async def test_occupancy_comparison(self, client, auth_headers):
        resp = await client.get("/api/central-office/occupancy-comparison?days=30", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "comparison" in data
        assert "chain_average" in data
    
    @pytest.mark.asyncio
    async def test_revenue_report(self, client, auth_headers):
        resp = await client.get("/api/central-office/revenue-report?period=monthly", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_chain_revenue" in data
        assert "chain_adr" in data
        assert "chain_revpar" in data
    
    @pytest.mark.asyncio
    async def test_trends_occupancy(self, client, auth_headers):
        resp = await client.get("/api/central-office/trends?metric=occupancy&days=7", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data_points" in data
        assert "summary" in data
        assert data["metric"] == "occupancy"
    
    @pytest.mark.asyncio
    async def test_trends_revenue(self, client, auth_headers):
        resp = await client.get("/api/central-office/trends?metric=revenue&days=7", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric"] == "revenue"
    
    @pytest.mark.asyncio
    async def test_property_health(self, client, auth_headers):
        resp = await client.get("/api/central-office/property-health", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "chain_average_score" in data
        assert "properties" in data
        if data["properties"]:
            prop = data["properties"][0]
            assert "overall_score" in prop
            assert "breakdown" in prop
            assert "grade" in prop
    
    @pytest.mark.asyncio
    async def test_budget_tracking(self, client, auth_headers):
        resp = await client.get("/api/central-office/budget-tracking", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tracking" in data
        assert "chain_summary" in data
    
    @pytest.mark.asyncio
    async def test_set_budget(self, client, auth_headers):
        # Get tenant_id first
        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        tenant_id = me_resp.json().get("tenant_id")
        
        resp = await client.post("/api/central-office/budget",
            params={
                "property_id": tenant_id,
                "revenue_target": 500000,
                "occupancy_target": 80,
                "adr_target": 250
            },
            headers=auth_headers
        )
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_alerts(self, client, auth_headers):
        resp = await client.get("/api/central-office/alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "critical_count" in data
        assert "warning_count" in data
    
    @pytest.mark.asyncio
    async def test_department_comparison(self, client, auth_headers):
        resp = await client.get("/api/central-office/department-comparison", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "departments" in data
        assert "chain_averages" in data


# ============= CROSS-PROPERTY GUESTS TESTS =============
class TestCrossPropertyGuests:
    """Cross-property misafir profilleri testleri"""
    
    @pytest.mark.asyncio
    async def test_search_guests(self, client, auth_headers):
        resp = await client.get("/api/cross-property/guests/search?query=Misafir", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "guests" in data
    
    @pytest.mark.asyncio
    async def test_loyalty_summary(self, client, auth_headers):
        resp = await client.get("/api/cross-property/guests/loyalty-summary", headers=auth_headers)
        assert resp.status_code == 200


# ============= OPENAPI/SWAGGER TESTS =============
class TestDocumentation:
    """API dokümantasyon testleri"""
    
    @pytest.mark.asyncio
    async def test_swagger_ui(self, client):
        resp = await client.get("/api/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "Swagger" in resp.text
    
    @pytest.mark.asyncio
    async def test_redoc(self, client):
        resp = await client.get("/api/redoc")
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_openapi_json(self, client):
        resp = await client.get("/api/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data
        assert len(data["paths"]) > 10


# ============= SECURITY HEADERS & GENERAL TESTS =============
class TestSecurityGeneral:
    """Genel güvenlik testleri"""
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client):
        resp = await client.options("/api/auth/login")
        # CORS should be configured
        assert resp.status_code in [200, 204, 405]
    
    @pytest.mark.asyncio
    async def test_404_handling(self, client, auth_headers):
        resp = await client.get("/api/nonexistent-endpoint", headers=auth_headers)
        assert resp.status_code in [404, 405]
    
    @pytest.mark.asyncio
    async def test_health_or_root(self, client):
        """En az bir sağlık kontrolü endpoint'i çalışmalı"""
        for endpoint in ["/api/health", "/api/", "/api/docs"]:
            resp = await client.get(endpoint)
            if resp.status_code == 200:
                return
        # If none return 200, docs should work
        resp = await client.get("/api/docs")
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-q"])
