"""
Comprehensive Unit Test Suite for RoomOps PMS
=============================================
%80+ coverage hedefli test suite.
"""
import pytest
import httpx
import asyncio
import uuid

BASE_URL = "http://localhost:8001"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Global token cache
_token_cache = {"token": None}

async def get_token():
    if _token_cache["token"]:
        return _token_cache["token"]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        _token_cache["token"] = resp.json()["access_token"]
    return _token_cache["token"]

async def get_headers():
    token = await get_token()
    return {"Authorization": f"Bearer {token}"}

async def api_get(path, **kwargs):
    headers = await get_headers()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        return await c.get(path, headers=headers, **kwargs)

async def api_post(path, **kwargs):
    headers = await get_headers()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        return await c.post(path, headers=headers, **kwargs)

async def api_put(path, **kwargs):
    headers = await get_headers()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        return await c.put(path, headers=headers, **kwargs)

async def api_delete(path, **kwargs):
    headers = await get_headers()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        return await c.delete(path, headers=headers, **kwargs)

# ============= AUTH MODULE TESTS =============
@pytest.mark.asyncio
async def test_auth_login_success():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == TEST_EMAIL

@pytest.mark.asyncio
async def test_auth_login_invalid():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_login_nonexistent():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.post("/api/auth/login", json={"email": "x@x.com", "password": "x"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_auth_me():
    resp = await api_get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == TEST_EMAIL

@pytest.mark.asyncio
async def test_auth_unauthorized():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.get("/api/auth/me")
    assert resp.status_code in [401, 403]

@pytest.mark.asyncio
async def test_auth_invalid_token():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401

# ============= ROOMS TESTS =============
@pytest.mark.asyncio
async def test_rooms_list():
    resp = await api_get("/api/pms/rooms")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_rooms_count():
    resp = await api_get("/api/pms/rooms")
    data = resp.json()
    rooms = data.get("rooms", data) if isinstance(data, dict) else data
    assert len(rooms) >= 1

# ============= GUESTS TESTS =============
@pytest.mark.asyncio
async def test_guests_list():
    resp = await api_get("/api/pms/guests")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_guests_create():
    resp = await api_post("/api/pms/guests", json={
        "name": f"Test {uuid.uuid4().hex[:6]}", "email": f"t{uuid.uuid4().hex[:6]}@x.com", "phone": "+905550001111"
    })
    assert resp.status_code in [200, 201]

# ============= 2FA SECURITY TESTS =============
@pytest.mark.asyncio
async def test_2fa_status():
    resp = await api_get("/api/security/2fa/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "enforced_by_policy" in data

@pytest.mark.asyncio
async def test_2fa_setup():
    resp = await api_post("/api/security/2fa/setup")
    assert resp.status_code == 200
    data = resp.json()
    assert "secret" in data
    assert "qr_code" in data
    assert data["qr_code"].startswith("data:image/png;base64,")

@pytest.mark.asyncio
async def test_2fa_verify_invalid():
    resp = await api_post("/api/security/2fa/verify", json={"code": "000000"})
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_2fa_tenant_policy():
    resp = await api_get("/api/security/2fa/tenant-policy")
    assert resp.status_code == 200
    assert "require_2fa" in resp.json()

@pytest.mark.asyncio
async def test_2fa_stats():
    resp = await api_get("/api/security/2fa/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "adoption_rate" in data

@pytest.mark.asyncio
async def test_2fa_update_policy():
    resp = await api_put("/api/security/2fa/tenant-policy", json={
        "require_2fa": False, "require_2fa_roles": ["admin"],
        "enforce_after_days": 7, "max_failed_attempts": 5,
        "lockout_duration_minutes": 30, "trusted_device_days": 30,
        "require_2fa_for_sensitive_ops": True
    })
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_2fa_trusted_devices():
    resp = await api_get("/api/security/2fa/trusted-devices")
    assert resp.status_code == 200
    assert "devices" in resp.json()

# ============= IP ACCESS CONTROL TESTS =============
@pytest.mark.asyncio
async def test_ip_rules_list():
    resp = await api_get("/api/security/ip/rules")
    assert resp.status_code == 200
    assert "rules" in resp.json()

@pytest.mark.asyncio
async def test_ip_rule_create():
    resp = await api_post("/api/security/ip/rules", json={
        "ip_address": f"10.0.{uuid.uuid4().int % 255}.1", "rule_type": "whitelist", "description": "Test"
    })
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_ip_rule_create_invalid():
    resp = await api_post("/api/security/ip/rules", json={"ip_address": "invalid", "rule_type": "whitelist"})
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_ip_check():
    resp = await api_post("/api/security/ip/check")
    assert resp.status_code == 200
    assert "allowed" in resp.json()

# ============= GDPR/KVKK TESTS =============
@pytest.mark.asyncio
async def test_gdpr_compliance_status():
    resp = await api_get("/api/gdpr/compliance-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "compliance_score" in data
    assert "compliance_checks" in data

@pytest.mark.asyncio
async def test_gdpr_retention_policy():
    resp = await api_get("/api/gdpr/retention-policy")
    assert resp.status_code == 200
    assert "guest_data_retention_days" in resp.json()

@pytest.mark.asyncio
async def test_gdpr_dpa_list():
    resp = await api_get("/api/gdpr/dpa")
    assert resp.status_code == 200
    assert "agreements" in resp.json()

@pytest.mark.asyncio
async def test_gdpr_create_dpa():
    resp = await api_post("/api/gdpr/dpa", json={
        "processor_name": "Test İşleyici", "purpose": "Analiz",
        "data_categories": ["misafir"], "retention_period_days": 365,
        "security_measures": ["şifreleme"], "cross_border_transfer": False
    })
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_gdpr_update_retention():
    resp = await api_put("/api/gdpr/retention-policy?guest_data_days=1095&auto_anonymize=false")
    assert resp.status_code == 200

# ============= PCI DSS TESTS =============
@pytest.mark.asyncio
async def test_pci_compliance_status():
    resp = await api_get("/api/pci-dss/compliance-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "compliance_score" in data
    assert "requirements" in data

@pytest.mark.asyncio
async def test_pci_requirements():
    resp = await api_get("/api/pci-dss/requirements")
    assert resp.status_code == 200
    assert resp.json()["total_requirements"] == 24

@pytest.mark.asyncio
async def test_pci_tokenize_visa():
    resp = await api_post("/api/pci-dss/tokenize", json={
        "card_number": "4111111111111111", "card_holder": "Test Kullanıcı",
        "expiry_month": 12, "expiry_year": 2028
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_four"] == "1111"
    assert data["card_brand"] == "Visa"

@pytest.mark.asyncio
async def test_pci_tokenize_mastercard():
    resp = await api_post("/api/pci-dss/tokenize", json={
        "card_number": "5555555555554444", "card_holder": "Test MC",
        "expiry_month": 6, "expiry_year": 2027
    })
    assert resp.status_code == 200
    assert resp.json()["card_brand"] == "Mastercard"

@pytest.mark.asyncio
async def test_pci_tokenize_invalid():
    resp = await api_post("/api/pci-dss/tokenize", json={
        "card_number": "1234567890123", "card_holder": "X", "expiry_month": 12, "expiry_year": 2028
    })
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_pci_tokens_list():
    resp = await api_get("/api/pci-dss/tokens")
    assert resp.status_code == 200
    assert "tokens" in resp.json()

@pytest.mark.asyncio
async def test_pci_security_scan():
    resp = await api_post("/api/pci-dss/security-scan")
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data
    assert data["status"] == "completed"

@pytest.mark.asyncio
async def test_pci_pan_scan():
    resp = await api_post("/api/pci-dss/pan-scan")
    assert resp.status_code == 200
    assert "exposed_pan_count" in resp.json()

@pytest.mark.asyncio
async def test_pci_scan_history():
    resp = await api_get("/api/pci-dss/scan-history")
    assert resp.status_code == 200
    assert "scans" in resp.json()

@pytest.mark.asyncio
async def test_pci_audit_update():
    resp = await api_put("/api/pci-dss/audit/1.1?audit_status=compliant&evidence=Test")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_pci_audit_invalid_req():
    resp = await api_put("/api/pci-dss/audit/99.99?audit_status=compliant")
    assert resp.status_code == 404

# ============= TENANT ISOLATION TESTS =============
@pytest.mark.asyncio
async def test_isolation_health():
    resp = await api_get("/api/tenant-isolation/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "isolation_score" in data
    assert data["isolation_score"] >= 0

@pytest.mark.asyncio
async def test_isolation_policy():
    resp = await api_get("/api/tenant-isolation/policy")
    assert resp.status_code == 200
    assert "strict_mode" in resp.json()

@pytest.mark.asyncio
async def test_isolation_policy_update():
    resp = await api_put("/api/tenant-isolation/policy?strict_mode=true&pii_masking_enabled=true")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_isolation_data_summary():
    resp = await api_get("/api/tenant-isolation/data-summary")
    assert resp.status_code == 200
    assert "total_records" in resp.json()

@pytest.mark.asyncio
async def test_isolation_data_classification():
    resp = await api_get("/api/tenant-isolation/data-classification")
    assert resp.status_code == 200
    assert "classifications" in resp.json()

@pytest.mark.asyncio
async def test_isolation_pii_scan():
    resp = await api_get("/api/tenant-isolation/pii-scan")
    assert resp.status_code == 200
    assert "overall_risk" in resp.json()

@pytest.mark.asyncio
async def test_isolation_audit_trail():
    resp = await api_get("/api/tenant-isolation/audit-trail?days=30")
    assert resp.status_code == 200
    assert "events" in resp.json()

@pytest.mark.asyncio
async def test_isolation_access_logs():
    resp = await api_get("/api/tenant-isolation/access-logs")
    assert resp.status_code == 200
    assert "logs" in resp.json()

@pytest.mark.asyncio
async def test_isolation_cross_tenant_request():
    resp = await api_post("/api/tenant-isolation/cross-tenant-request",
        params={"target_tenant_id": "other", "reason": "Test", "data_scope": "summary"})
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_isolation_cross_tenant_list():
    resp = await api_get("/api/tenant-isolation/cross-tenant-requests")
    assert resp.status_code == 200
    assert "requests" in resp.json()

# ============= CENTRAL OFFICE TESTS =============
@pytest.mark.asyncio
async def test_central_dashboard():
    resp = await api_get("/api/central-office/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "chain_kpi" in data
    kpi = data["chain_kpi"]
    assert "chain_adr" in kpi
    assert "chain_revpar" in kpi

@pytest.mark.asyncio
async def test_central_properties():
    resp = await api_get("/api/central-office/properties")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

@pytest.mark.asyncio
async def test_central_occupancy():
    resp = await api_get("/api/central-office/occupancy-comparison?days=30")
    assert resp.status_code == 200
    assert "chain_average" in resp.json()

@pytest.mark.asyncio
async def test_central_revenue():
    resp = await api_get("/api/central-office/revenue-report")
    assert resp.status_code == 200
    data = resp.json()
    assert "chain_adr" in data
    assert "chain_revpar" in data

@pytest.mark.asyncio
async def test_central_trends_occ():
    resp = await api_get("/api/central-office/trends?metric=occupancy&days=7")
    assert resp.status_code == 200
    assert resp.json()["metric"] == "occupancy"

@pytest.mark.asyncio
async def test_central_trends_rev():
    resp = await api_get("/api/central-office/trends?metric=revenue&days=7")
    assert resp.status_code == 200
    assert resp.json()["metric"] == "revenue"

@pytest.mark.asyncio
async def test_central_trends_bookings():
    resp = await api_get("/api/central-office/trends?metric=bookings&days=7")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_central_health():
    resp = await api_get("/api/central-office/property-health")
    assert resp.status_code == 200
    data = resp.json()
    assert "chain_average_score" in data
    if data["properties"]:
        assert "grade" in data["properties"][0]

@pytest.mark.asyncio
async def test_central_budget():
    resp = await api_get("/api/central-office/budget-tracking")
    assert resp.status_code == 200
    assert "chain_summary" in resp.json()

@pytest.mark.asyncio
async def test_central_alerts():
    resp = await api_get("/api/central-office/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "critical_count" in data
    assert "warning_count" in data

@pytest.mark.asyncio
async def test_central_departments():
    resp = await api_get("/api/central-office/department-comparison")
    assert resp.status_code == 200
    assert "chain_averages" in resp.json()

# ============= CROSS-PROPERTY GUESTS TESTS =============
@pytest.mark.asyncio
async def test_cross_property_search():
    resp = await api_get("/api/cross-property/guests/search?query=Misafir")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_cross_property_loyalty():
    resp = await api_get("/api/cross-property/guests/loyalty-summary")
    assert resp.status_code == 200

# ============= OPENAPI/SWAGGER TESTS =============
@pytest.mark.asyncio
async def test_swagger_ui():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.get("/api/docs")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_redoc():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.get("/api/redoc")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_openapi_json():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        resp = await c.get("/api/openapi.json")
    assert resp.status_code == 200
    assert len(resp.json()["paths"]) > 10

# ============= SECURITY GENERAL TESTS =============
@pytest.mark.asyncio
async def test_404_handling():
    resp = await api_get("/api/nonexistent-endpoint-xyz")
    assert resp.status_code in [404, 405]
