import os
import re
from pathlib import Path
import pytest
from motor.motor_asyncio import AsyncIOMotorCollection

from core.database import db, _raw_db
from core.tenant_db import (
    set_tenant_context, 
    clear_tenant_context, 
    TenantViolationError, 
    STRICT_TENANT_MODE,
    TenantScopedCollection,
    SchemaOnlyCollection
)

@pytest.fixture(autouse=True)
def ensure_strict_mode():
    assert STRICT_TENANT_MODE is True, "STRICT_TENANT_MODE must be enabled for these tests!"

def test_tenant_scoped_collection_without_context_raises_error():
    """Scenario A: Tenant context olmadan tenant-scoped collection query -> RuntimeError"""
    clear_tenant_context()
    
    # In STRICT_TENANT_MODE, db.bookings returns a SchemaOnlyCollection when context is missing
    coll = db.bookings
    assert isinstance(coll, SchemaOnlyCollection)
    
    # Accessing a data method should raise TenantViolationError (which is a runtime error subclass)
    with pytest.raises(TenantViolationError) as exc:
        _ = coll.find_one
    
    assert "without tenant context is forbidden (STRICT_TENANT_MODE=true)" in str(exc.value)

def test_tenant_scoped_collection_with_context_auto_injects():
    """Scenario B: Tenant context ile query -> tenant_id auto-inject"""
    set_tenant_context("hotel_abc")
    try:
        coll = db.bookings
        # Must return a TenantScopedCollection, which automatically injects tenant_id
        assert isinstance(coll, TenantScopedCollection)
        assert getattr(coll, "_tenant_id") == "hotel_abc"
        
        # Verify the injection logic directly
        injected = coll._inject_filter({"status": "active"})
        assert injected == {"status": "active", "tenant_id": "hotel_abc"}
    finally:
        clear_tenant_context()

def test_system_db_access_bypasses_guard():
    """Scenario C: Explicit system DB kullanımı -> sadece izinli system operations"""
    clear_tenant_context()
    
    # Using _raw_db bypasses the proxy entirely
    coll = _raw_db.reservations
    assert isinstance(coll, AsyncIOMotorCollection)
    
    # Ensure it's not wrapped in any guard
    assert not isinstance(coll, TenantScopedCollection)
    assert not isinstance(coll, SchemaOnlyCollection)

def test_raw_db_usage_static_audit():
    """Scenario D: Raw DB usage static audit / CI guard"""
    backend_dir = Path(__file__).parent.parent.parent
    
    # These files legitimately need raw DB access (startup, sysadmin, legacy tech debt)
    # New endpoints MUST use TenantAwareDBProxy.
    allowed_raw_db_files = {
        "core/",
        "bootstrap/",
        "conftest.py",
        "tests/",
        "ops/",
        "scripts/",
        "load_tests/",
        "workers/",
        "modules/",
        "integrations/",
        "security/",
        "controlplane/",
        ".venv/",
        "server.py",
        "app.py",
        "celery_tasks.py",
        "create_demo_users.py",
        # Legacy router exceptions that need refactoring:
        "routers/auth.py",
        "routers/onboarding.py",
        "routers/room_qr_requests.py",
        "routers/production_golive.py",
        "routers/pms_outbound.py",
        "routers/marketplace.py",
        "routers/report_scheduler.py",
        "routers/db_admin.py",
        "routers/quick_id_proxy.py",
        "domains/admin/entitlement_router.py",
        "domains/hr/router.py",
        "domains/guest/messaging/guest_requests_router.py",
        "domains/guest/messaging/guest_requests.py",
    }
    
    violations = []
    for py_file in backend_dir.rglob("*.py"):
        rel_path = py_file.relative_to(backend_dir).as_posix()
        
        if any(rel_path.startswith(a) or rel_path == a for a in allowed_raw_db_files):
            continue
            
        content = py_file.read_text(encoding="utf-8")
        if "_raw_db" in content:
            violations.append(f"{rel_path} uses _raw_db directly")
        if "AsyncIOMotorClient" in content:
            violations.append(f"{rel_path} uses AsyncIOMotorClient directly")
            
    assert not violations, "Found illegal raw DB access bypassing TenantAwareDBProxy:\\n" + "\\n".join(violations)
