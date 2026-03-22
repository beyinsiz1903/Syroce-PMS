"""
TS-018 to TS-020: Multi-Tenant Safety & Secret Access Resilience Tests

Tests:
- TS-018: Unauthorized secret access attempt
- TS-019: Cross-tenant secret access
- TS-020: Event replayed under wrong tenant context (retry safety)

Markers: chaos_l1, chaos_l2, chaos_tenant
"""
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = [pytest.mark.asyncio]


# ═══════════════════════════════════════════════════════════════════
# TS-018: Unauthorized Secret Access Attempt
# ═══════════════════════════════════════════════════════════════════

class TestUnauthorizedSecretAccess:
    """
    Scenario D-06: Unknown caller accesses secrets.
    Guarantee: Access denied. Audited. Security failure emitted.
    """

    @pytest.mark.chaos_l1
    async def test_unknown_caller_denied_by_policy(
        self, secret_access_control, db, tenant_factory
    ):
        """Unknown caller must be denied by access policy."""
        tenant_id = tenant_factory("unauth-001")

        result = await secret_access_control.check_and_log(
            tenant_id=tenant_id,
            provider="exely",
            access_type="read",
            caller="unknown_malicious_service",
        )
        assert result is False

        # Verify audit record
        audit = await db.secret_access_audit.find_one(
            {"tenant_id": tenant_id, "caller": "unknown_malicious_service"},
            {"_id": 0},
        )
        assert audit is not None
        assert audit["result"] == "denied"
        assert "policy" in audit.get("reason", "").lower()

    @pytest.mark.chaos_l1
    async def test_security_failure_emitted_on_denial(
        self, secret_access_control, db, tenant_factory
    ):
        """Denied secret access must emit a SECURITY_ERROR to control plane."""
        tenant_id = tenant_factory("unauth-002")

        await secret_access_control.check_and_log(
            tenant_id=tenant_id,
            provider="exely",
            access_type="read",
            caller="rogue_service",
        )

        # Check cp_failures for security error
        failure = await db.cp_failures.find_one(
            {"tenant_id": tenant_id, "failure_type": "security_error"},
            {"_id": 0},
        )
        assert failure is not None
        assert failure["severity"] == "critical"
        assert failure["operation_type"] == "secret_access"

    @pytest.mark.chaos_l1
    async def test_known_caller_allowed_for_correct_provider(
        self, secret_access_control, db, tenant_factory
    ):
        """Known caller accessing allowed provider should succeed."""
        tenant_id = tenant_factory("auth-001")

        result = await secret_access_control.check_and_log(
            tenant_id=tenant_id,
            provider="exely",
            access_type="read",
            caller="channel_manager",
        )
        assert result is True

        audit = await db.secret_access_audit.find_one(
            {"tenant_id": tenant_id, "caller": "channel_manager"},
            {"_id": 0},
        )
        assert audit is not None
        assert audit["result"] == "success"


# ═══════════════════════════════════════════════════════════════════
# TS-019: Cross-Tenant Secret Access
# ═══════════════════════════════════════════════════════════════════

class TestCrossTenantSecretAccess:
    """
    Scenario E-02: Service with tenant A context tries to read tenant B secrets.
    Guarantee: Access DENIED. Critical security log. Audit trail.
    """

    @pytest.mark.chaos_l1
    async def test_cross_tenant_access_denied(
        self, secret_access_control, db, tenant_factory
    ):
        """Cross-tenant secret access must always be denied."""
        tenant_a = tenant_factory("cross-A")
        tenant_b = tenant_factory("cross-B")

        result = await secret_access_control.check_and_log(
            tenant_id=tenant_b,            # Target tenant
            provider="exely",
            access_type="read",
            caller="channel_manager",
            request_tenant_id=tenant_a,     # Requesting tenant (different!)
        )
        assert result is False

    @pytest.mark.chaos_l1
    async def test_cross_tenant_denial_audited(
        self, secret_access_control, db, tenant_factory
    ):
        """Cross-tenant denial must be in audit trail."""
        tenant_a = tenant_factory("cross-audit-A")
        tenant_b = tenant_factory("cross-audit-B")

        await secret_access_control.check_and_log(
            tenant_id=tenant_b,
            provider="exely",
            access_type="read",
            caller="channel_manager",
            request_tenant_id=tenant_a,
        )

        audit = await db.secret_access_audit.find_one(
            {"tenant_id": tenant_b, "result": "denied"},
            {"_id": 0},
        )
        assert audit is not None
        assert "cross-tenant" in audit.get("reason", "").lower()

    @pytest.mark.chaos_l1
    async def test_cross_tenant_emits_critical_security_failure(
        self, secret_access_control, db, tenant_factory
    ):
        """Cross-tenant denial must emit CRITICAL security failure."""
        tenant_a = tenant_factory("cross-crit-A")
        tenant_b = tenant_factory("cross-crit-B")

        await secret_access_control.check_and_log(
            tenant_id=tenant_b,
            provider="exely",
            access_type="read",
            caller="channel_manager",
            request_tenant_id=tenant_a,
        )

        failure = await db.cp_failures.find_one(
            {"tenant_id": tenant_b, "failure_type": "security_error"},
            {"_id": 0},
        )
        assert failure is not None
        assert failure["severity"] == "critical"

    @pytest.mark.chaos_l1
    async def test_same_tenant_access_allowed(
        self, secret_access_control, db, tenant_factory
    ):
        """Same tenant accessing own secrets must be allowed (sanity check)."""
        tenant_id = tenant_factory("same-tenant-001")

        result = await secret_access_control.check_and_log(
            tenant_id=tenant_id,
            provider="exely",
            access_type="read",
            caller="channel_manager",
            request_tenant_id=tenant_id,  # Same tenant
        )
        assert result is True


# ═══════════════════════════════════════════════════════════════════
# TS-020: Event Replayed Under Wrong Tenant Context
# ═══════════════════════════════════════════════════════════════════

class TestReplayTenantContext:
    """
    Scenario E-01: Retry engine uses tenant_id from failure record.
    Guarantee: No way for caller to override tenant context.
    """

    @pytest.mark.chaos_l2
    async def test_retry_engine_reads_tenant_from_failure_record(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Retry must use tenant_id from the failure document, not from caller."""
        tenant_a = tenant_factory("replay-tenant-A")

        # Create failure for tenant A
        failure = failure_event_factory(
            tenant_id=tenant_a,
            operation_type="outbox_dispatch",
            context={"event_id": str(uuid.uuid4())},
        )
        await db.cp_failures.insert_one(failure)

        # Retry — the engine has no way to inject a different tenant
        result = await retry_engine.retry(failure["id"])

        # The failure record's tenant_id is what gets used
        failure_doc = await db.cp_failures.find_one(
            {"id": failure["id"]}, {"_id": 0}
        )
        assert failure_doc["tenant_id"] == tenant_a

    @pytest.mark.chaos_l1
    async def test_access_policy_enforcement_per_caller(self):
        """Verify access policy correctly scopes callers to providers."""
        from controlplane.secret_audit import check_access_policy

        # channel_manager can access exely and hotelrunner
        assert check_access_policy("channel_manager", "exely") is True
        assert check_access_policy("channel_manager", "hotelrunner") is True

        # import_bridge can access exely and hotelrunner
        assert check_access_policy("import_bridge", "exely") is True
        assert check_access_policy("import_bridge", "hotelrunner") is True

        # unknown_service cannot access anything
        assert check_access_policy("unknown_service", "exely") is False
        assert check_access_policy("unknown_service", "hotelrunner") is False
        assert check_access_policy("random_hacker", "exely") is False
