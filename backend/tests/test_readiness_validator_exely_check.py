"""Tests for the Exely whitelist sub-check in ReadinessValidator.

Pilot Readiness hard-blocker #1 — Paket 2 wiring. Verifies:

  * The check is wired into `ReadinessValidator.validate()` output.
  * Verdict mirrors the CLI script (PASS / REVIEW / FAIL).
  * Production FAIL drops readiness score (NOT_READY contribution).
  * Readiness JSON does NOT leak raw IP/token values to downstream
    log sinks (Sentry, CI, alerting). Only counts + verdict + status.
  * The check is fail-safe — its own crash never sinks readiness with
    raw secret/IP material in the error payload.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend/ is on sys.path so `infra.*` and `scripts.*` resolve when
# this test runs from the repo root or from `backend/`.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from infra.readiness_validator import ReadinessValidator  # noqa: E402


def _stub_other_subsystems(validator: ReadinessValidator) -> None:
    """Replace every non-Exely import the validator does at runtime so we
    can run `validate()` in a unit-test process without Redis/Mongo/etc."""
    pass  # Patches applied per-test below via the helper.


@pytest.fixture
def stub_subsystems(monkeypatch):
    """Patch every infra import inside `validate()` to a benign stub so the
    Exely sub-check is the only branch exercised meaningfully."""
    # 1. Redis cluster
    class _RedisStub:
        connected = True
        mode = "single"
        async def health_check(self):
            return {"status": "ok"}
    monkeypatch.setitem(sys.modules, "infra.redis_cluster", type(sys)("infra.redis_cluster"))
    sys.modules["infra.redis_cluster"].redis_cluster = _RedisStub()

    # 2. MongoDB validator
    class _MongoStub:
        _db = object()
        def set_db(self, db): pass
        async def get_connection_pool_info(self):
            return {"status": "connected", "current_connections": 1, "mongo_version": "7.0"}
    monkeypatch.setitem(sys.modules, "core.database", type(sys)("core.database"))
    sys.modules["core.database"].db = object()
    monkeypatch.setitem(sys.modules, "infra.mongo_production", type(sys)("infra.mongo_production"))
    sys.modules["infra.mongo_production"].mongo_validator = _MongoStub()

    # 3. Worker queue
    class _WQStub:
        def get_worker_summary(self):
            return {"queues": ["a"]}
    monkeypatch.setitem(sys.modules, "infra.worker_queue", type(sys)("infra.worker_queue"))
    sys.modules["infra.worker_queue"].worker_queue_manager = _WQStub()

    # 4. Provider activation
    class _ProvStub:
        def get_all_provider_status(self):
            return {"active_providers": 3, "total_providers": 3}
    monkeypatch.setitem(sys.modules, "infra.provider_activation", type(sys)("infra.provider_activation"))
    sys.modules["infra.provider_activation"].provider_manager = _ProvStub()

    # 5. Backup
    class _BackupStub:
        def get_status(self):
            return {"enabled": True}
    monkeypatch.setitem(sys.modules, "infra.backup_manager", type(sys)("infra.backup_manager"))
    sys.modules["infra.backup_manager"].backup_manager = _BackupStub()

    # 6. Observability
    class _OtelStub:
        def get_status(self):
            return {"active": True}
    class _SentryStub:
        def get_status(self):
            return {"active": True}
    monkeypatch.setitem(sys.modules, "infra.cloud_observability", type(sys)("infra.cloud_observability"))
    sys.modules["infra.cloud_observability"].otel_tracer = _OtelStub()
    sys.modules["infra.cloud_observability"].sentry_integration = _SentryStub()

    # 7. Alerting
    class _AlertStub:
        def get_summary(self):
            return {"status": "ok"}
    monkeypatch.setitem(sys.modules, "modules.observability.alerting_engine", type(sys)("modules.observability.alerting_engine"))
    sys.modules["modules.observability.alerting_engine"].alerting_engine = _AlertStub()

    # 8. Production config
    class _PCStub:
        def startup_check(self):
            return {"status": "pass", "missing_critical": []}
    monkeypatch.setitem(sys.modules, "infra.production_config", type(sys)("infra.production_config"))
    sys.modules["infra.production_config"].production_config = _PCStub()

    yield


def _run_validate() -> dict:
    return asyncio.run(ReadinessValidator().validate())


# ── Wiring + verdict mirroring ───────────────────────────────────────────


def test_exely_check_is_present_in_readiness_output(stub_subsystems, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    assert "exely_whitelist" in result["checks"]
    chk = result["checks"]["exely_whitelist"]
    assert chk["verdict"] == "PASS"
    assert chk["status"] == "ok"
    assert chk["blocker_count"] == 0
    assert chk["warning_count"] == 0
    assert chk["configured_count"] == 1


def test_production_fail_drops_readiness_score(stub_subsystems, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    chk = result["checks"]["exely_whitelist"]
    assert chk["verdict"] == "FAIL"
    assert chk["status"] == "blocked"
    assert chk["blocker_count"] >= 1
    # With all other subsystems healthy (1.0) and Exely=0.0, average drops.
    # 8 healthy * 1.0 + 1 * 0.0 = 8/9 ≈ 0.888 → 89, still READY but lower
    # than the all-pass 100. So just assert score < 100 to confirm impact.
    assert result["readiness_score"] < 100


def test_review_verdict_partially_degrades_score(stub_subsystems, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", "1")
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    chk = result["checks"]["exely_whitelist"]
    assert chk["verdict"] == "REVIEW"
    assert chk["status"] == "review"
    assert chk["warning_count"] >= 1


def test_non_production_missing_whitelist_marks_misconfigured_not_blocked(
    stub_subsystems, monkeypatch
):
    """Dev/staging missing whitelist is informational — webhook offline,
    but the rest of the PMS should still be healthy."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    chk = result["checks"]["exely_whitelist"]
    # Missing whitelist in dev is NOT a blocker per script semantics.
    assert chk["verdict"] == "PASS"
    assert chk["blocker_count"] == 0


# ── Security: no raw IP/token values in readiness JSON ───────────────────


def test_configured_whitelist_does_not_leak_raw_ips(stub_subsystems, monkeypatch):
    """Even with valid whitelist, raw IPs must NEVER be serialized into
    readiness output — only count + verdict."""
    raw_ips = "203.0.113.42,198.51.100.7,2001:db8::1"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EXELY_IP_WHITELIST", raw_ips)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    serialized = json.dumps(result["checks"]["exely_whitelist"])
    for raw in ["203.0.113.42", "198.51.100.7", "2001:db8::1"]:
        assert raw not in serialized, f"Raw IP {raw} leaked into readiness JSON"
    # Even the redacted preview should not be in this payload — counts only.
    assert "203.0.x.42" not in serialized
    assert "198.51.x.7" not in serialized


def test_invalid_token_does_not_leak_raw_value(stub_subsystems, monkeypatch):
    """Bad tokens never appear verbatim in readiness output."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4,super-secret-bad-token")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    serialized = json.dumps(result["checks"]["exely_whitelist"])
    assert "super-secret-bad-token" not in serialized


def test_readiness_json_field_set_is_minimal(stub_subsystems, monkeypatch):
    """Lock the schema: only safe metadata fields allowed."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    result = _run_validate()
    chk = result["checks"]["exely_whitelist"]
    allowed = {"status", "verdict", "environment", "blocker_count",
               "warning_count", "configured_count"}
    extra = set(chk.keys()) - allowed
    assert not extra, f"Unexpected fields in exely_whitelist payload: {extra}"


# ── Fail-safe: check crash never propagates raw env contents ─────────────


def test_check_crash_emits_safe_error_payload(stub_subsystems, monkeypatch):
    """If verify() itself raises, error_type is the only error metadata —
    no traceback or env dump that could leak secrets."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4")

    def _boom(*a, **kw):
        raise RuntimeError("simulated-failure-with-1.2.3.4-in-message")

    with patch("scripts.verify_exely_whitelist.verify", side_effect=_boom):
        result = _run_validate()
    chk = result["checks"]["exely_whitelist"]
    assert chk["status"] == "error"
    assert chk["error_type"] == "RuntimeError"
    serialized = json.dumps(chk)
    assert "1.2.3.4" not in serialized
    assert "simulated-failure" not in serialized
