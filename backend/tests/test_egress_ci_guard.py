"""CI guard: prevent regressions of the v109 round-7 SSRF/DNS-rebinding closure.

Scans the backend for new uses of ``httpx.AsyncClient`` against an explicit
allowlist. The allowlist contains files where the outbound HTTP target is
either:
  (a) an operator-controlled environment variable (not tenant input),
  (b) a hardcoded server constant or third-party fixed URL, or
  (c) a test-only/internal infrastructure call.

If a new tenant-configurable callsite appears outside the allowlist, this
test fails and the developer must either migrate the callsite to
``backend.integrations.xchange.safety.safe_request_async`` (or
``safe_post_async``) or justify the addition by extending the allowlist.

Run: ``pytest backend/tests/test_egress_ci_guard.py``
"""
from __future__ import annotations

import re
from pathlib import Path

# Files allowed to use raw ``httpx.AsyncClient`` directly. Each entry MUST
# include a one-line justification — the trust-boundary classification.
ALLOWED_RAW_HTTPX = {
    # Operator env QUICKID_URL — internal sister service URL
    "backend/routers/quick_id_proxy.py",
    # Server constants for HotelRunner partner endpoints
    "backend/channel_manager/connectors/hotelrunner_v2/client.py",
    "backend/channel_manager/connectors/hotelrunner_v2/hr_client.py",
    "backend/domains/channel_manager/providers/hotelrunner/client.py",
    # Operator env CM_PARTNER_WEBHOOK_URL
    "backend/domains/channel_manager/router.py",
    # Server constant — Expo Push Service public endpoint (env override allowed)
    "backend/services/expo_push.py",
    # Operator env CAPX_BASE_URL — partner PMS integration endpoint
    "backend/integrations/capx/client.py",
    # Operator env CM_PARTNER_BASE_URL — outbox dispatcher
    "backend/core/outbox_dispatcher.py",
    # Operator env AFSADAKAT_PROVISIONER_URL (NOT tenant — installer)
    "backend/core/afsadakat_provisioner.py",
    # Legacy unused (superseded by adapter migration)
    "backend/domains/channel_manager/providers/exely/exely_client_legacy.py",
    # Operator env OPS_*_WEBHOOK_URL / PAGERDUTY_URL / SLACK_OPS_URL
    "backend/infra/live_ops_alerts.py",
    # Operator env OPS_VAULT_URL — secrets infrastructure
    "backend/infra/secrets_manager.py",
    # Operator-only "test connection" feature: SENDGRID_API_KEY env / fixed Twilio URL
    "backend/infra/provider_test_connection.py",
    # Hardcoded https://graph.facebook.com — fixed third-party constant (Meta)
    "backend/modules/messaging/providers.py",
    "backend/domains/ai/whatsapp_service.py",
    # Hardcoded http://localhost:8001/health — internal liveness probe
    "backend/ops/auto_rollback_engine.py",
    # Operator-run smoke test runner against env BASE_URL
    "backend/ops/smoke_test_runner.py",
    # Load test scaffolding (test-only)
    "backend/load_tests/conftest.py",
    "backend/load_tests/test_availability_invariants.py",
    "backend/load_tests/test_booking_integrity.py",
    "backend/load_tests/test_concurrent_mutations.py",
    "backend/load_tests/test_failure_injection.py",
    "backend/load_tests/test_multi_tenant_load.py",
}

# Round-7 follow-up #2 (architect 2026-04-24): also scan aiohttp.ClientSession,
# which has the same DNS-rebinding risk as httpx.AsyncClient. requests.* is
# synchronous and only used in tests, so we don't gate it (yet).
_RE_HTTPX_CLIENT = re.compile(r"\bhttpx\s*\.\s*AsyncClient\b")
_RE_AIOHTTP_SESSION = re.compile(r"\baiohttp\s*\.\s*ClientSession\b")
BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BACKEND_ROOT.parent  # workspace root

# aiohttp.ClientSession sites with operator-controlled URLs.
ALLOWED_RAW_AIOHTTP = {
    # Operator env CONTROLPLANE_ALERT_WEBHOOK_URL — Slack/PagerDuty webhook
    "backend/controlplane/alerting.py",
    # Operator env DRIFT_ALERT_WEBHOOK_URL — Slack drift webhook
    "backend/controlplane/drift_alerting.py",
}


def _scan_backend(pattern: re.Pattern, marker: str) -> dict[str, list[int]]:
    findings: dict[str, list[int]] = {}
    for py in BACKEND_ROOT.rglob("*.py"):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or rel.endswith("test_egress_ci_guard.py"):
            continue
        if "/.venv/" in rel:
            continue
        if rel.endswith("integrations/xchange/safety.py"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if marker not in text:
            continue
        lines = []
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                lines.append(i)
        if lines:
            findings[rel] = lines
    return findings


def test_no_unjustified_raw_httpx_async_client():
    """Fail if a non-allowlisted file introduces a raw ``httpx.AsyncClient``."""
    findings = _scan_backend(_RE_HTTPX_CLIENT, "httpx.AsyncClient")
    unjustified = {f: ls for f, ls in findings.items() if f not in ALLOWED_RAW_HTTPX}
    assert not unjustified, (
        "Raw httpx.AsyncClient found outside allowlist. New tenant-configurable "
        "outbound HTTP calls MUST use safe_request_async / safe_post_async from "
        "backend.integrations.xchange.safety. If this file is operator/server-"
        "controlled, add it to ALLOWED_RAW_HTTPX with a one-line justification.\n"
        f"Offending files: {unjustified}"
    )


def test_no_unjustified_raw_aiohttp_client_session():
    """Fail if a non-allowlisted file introduces a raw ``aiohttp.ClientSession``."""
    findings = _scan_backend(_RE_AIOHTTP_SESSION, "aiohttp.ClientSession")
    unjustified = {f: ls for f, ls in findings.items() if f not in ALLOWED_RAW_AIOHTTP}
    assert not unjustified, (
        "Raw aiohttp.ClientSession found outside allowlist. Same DNS-rebinding "
        "risk as httpx.AsyncClient — migrate to backend.integrations.xchange."
        "safety.safe_request_async (which uses httpx) or add to "
        "ALLOWED_RAW_AIOHTTP with operator-controlled justification.\n"
        f"Offending files: {unjustified}"
    )


def test_allowlist_entries_still_exist():
    """Sanity: prevent stale allowlist entries (file moved/deleted)."""
    missing = [
        f for f in ALLOWED_RAW_HTTPX
        if not (REPO_ROOT / f).exists()
    ]
    assert not missing, (
        f"Allowlist references files that no longer exist (please prune): {missing}"
    )
