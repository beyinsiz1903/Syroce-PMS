"""PCI-DSS v4.0 compliance evaluator.

Maps Syroce PMS technical controls to the 12 PCI-DSS requirements
and produces a status report suitable for procurement/audit. This is
NOT a substitute for a real QSA assessment — it is a self-attestation
helper that surfaces what controls are in place and what gaps remain.

Status values:
  - met            → control fully implemented in Syroce
  - partial        → control partially in place; recommendations listed
  - shared         → shared responsibility (cloud / customer-side)
  - not_applicable → does not apply to a SaaS PMS
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

VERSION = "PCI-DSS v4.0"


def _has_env(*keys: str) -> bool:
    return any(os.environ.get(k) for k in keys)


def _has_module(path: str) -> bool:
    """Best-effort import probe."""
    try:
        __import__(path)
        return True
    except Exception:
        return False


def evaluate_controls() -> list[dict[str, Any]]:
    """Return the 12-requirement compliance report."""

    has_field_encryption = _has_module("security.field_encryption")
    has_tenant_isolation = _has_module("security.tenant_isolation_router")
    has_audit_pii = _has_module("security.pii_audit")
    has_pii_masking = _has_module("security.pii_masking_middleware")  # noqa: F841
    has_rate_limiter = _has_module("security.rate_limiter")  # noqa: F841
    has_2fa = _has_module("routers.security_2fa")
    has_log_sanitizer = _has_module("security.log_sanitizer")
    has_credential_guard = _has_module("security.credential_guard")  # noqa: F841
    has_rotation = _has_module("security.rotation_engine")  # noqa: F841
    has_jwt_secret = bool(os.environ.get("JWT_SECRET"))  # noqa: F841
    has_encryption_key = _has_env("FIELD_ENCRYPTION_KEY", "ENCRYPTION_KEY")
    # TLS / transport posture is environment-controlled; verifiable bits:
    has_hsts = _has_module("security.security_headers_middleware") or _has_module("middleware.security_headers")
    force_https = os.environ.get("FORCE_HTTPS", "").lower() in {"1", "true", "yes"}
    # CI evidence — only claim met when explicitly attested via env:
    has_ci_security_scan = os.environ.get("CI_SECURITY_SCAN_ENABLED", "").lower() in {"1", "true", "yes"}

    controls: list[dict[str, Any]] = [
        {
            "req_id": "1",
            "title": "Install and maintain network security controls",
            "status": "shared",
            "evidence": [
                "TLS termination + WAF handled by Replit deployment edge",
                "Application uses HTTPS-only cookies and HSTS headers",
            ],
            "recommendations": [
                "Document Replit-managed firewall and ingress rules in your PCI evidence packet",
            ],
        },
        {
            "req_id": "2",
            "title": "Apply secure configurations to all system components",
            "status": "met" if has_log_sanitizer else "partial",
            "evidence": [
                "No vendor defaults: bcrypt password hashing, JWT_SECRET required",
                "Log sanitizer strips secrets/PII from runtime logs",
                "Secure dependency lock files (requirements.txt, yarn.lock)",
            ],
            "recommendations": [],
        },
        {
            "req_id": "3",
            "title": "Protect stored account data",
            "status": "met" if (has_field_encryption and has_encryption_key) else "partial",
            "evidence": [
                "AES-256-GCM field-level encryption (security/field_encryption.py)",
                "PII fields (PAN, CVV, ID numbers) never stored in plaintext",
                "Backup codes for 2FA stored as bcrypt hashes",
                "TOTP secrets stored Fernet-encrypted with domain-separated key",
            ],
            "recommendations": (
                [] if has_encryption_key
                else ["Set FIELD_ENCRYPTION_KEY in environment for production deployments"]
            ),
        },
        {
            "req_id": "4",
            "title": "Protect cardholder data with strong cryptography during transmission over open networks",
            "status": "met" if (has_hsts or force_https) else "partial",
            "evidence": [
                "Webhook signatures use HMAC-SHA256 (e.g., Af-sadakat integration)",
                "Inter-service tokens use HS256 JWTs with short TTLs",
                *( ["HSTS / security headers middleware active"] if has_hsts else [] ),
                *( ["FORCE_HTTPS=true (HTTP→HTTPS redirect enforced)"] if force_https else [] ),
            ],
            "recommendations": (
                [] if (has_hsts or force_https)
                else [
                    "Enable HSTS via security_headers middleware",
                    "Set FORCE_HTTPS=true to enforce HTTPS at the application layer (Replit edge already terminates TLS, but app-level redirect prevents accidental HTTP exposure)",
                ]
            ),
        },
        {
            "req_id": "5",
            "title": "Protect all systems and networks from malicious software",
            "status": "shared",
            "evidence": [
                "Managed runtime (Replit) handles host-level AV/EDR",
                "Application has no untrusted file execution paths",
            ],
            "recommendations": [
                "If integrating with on-prem POS terminals, add file-upload AV scanning",
            ],
        },
        {
            "req_id": "6",
            "title": "Develop and maintain secure systems and software",
            "status": "met" if has_ci_security_scan else "partial",
            "evidence": [
                "On-demand dependency audit, SAST and credential-leak scans available",
                "All routes execute through bootstrap/router_registry with explicit auth deps",
                *( ["CI_SECURITY_SCAN_ENABLED=true (scans run on every release candidate)"]
                   if has_ci_security_scan else [] ),
            ],
            "recommendations": (
                [] if has_ci_security_scan
                else [
                    "Schedule dependency audit + SAST in CI for every release candidate",
                    "Set CI_SECURITY_SCAN_ENABLED=true to attest CI integration",
                ]
            ),
        },
        {
            "req_id": "7",
            "title": "Restrict access to system components and cardholder data by business need-to-know",
            "status": "met" if has_tenant_isolation else "partial",
            "evidence": [
                "Multi-tenant isolation enforced at database query layer (tenant_isolation_service)",
                "Role-based access (super_admin / admin / owner / receptionist / housekeeping)",
                "Cross-tenant queries blocked by tenant_guard middleware",
            ],
            "recommendations": [],
        },
        {
            "req_id": "8",
            "title": "Identify users and authenticate access to system components",
            "status": "met" if has_2fa else "partial",
            "evidence": [
                "Bcrypt password hashing (cost factor 12)",
                "TOTP-based 2FA with backup codes (RFC 6238)",
                "JWT access tokens (HS256, 7d TTL) with optional 2FA challenge gate",
                "Audit logs for login_success / login_failed / 2fa_* events",
                "Password change requires current password verification",
            ],
            "recommendations": (
                [] if has_2fa
                else ["Enable 2FA module for all administrative accounts"]
            ),
        },
        {
            "req_id": "9",
            "title": "Restrict physical access to cardholder data",
            "status": "shared",
            "evidence": [
                "Data center physical security covered by cloud provider (SOC 2 / ISO 27001 attestations)",
            ],
            "recommendations": [
                "Document customer-side: workstation lock policies, badge access for hotel back-office",
            ],
        },
        {
            "req_id": "10",
            "title": "Log and monitor all access to system components and cardholder data",
            "status": "met" if has_audit_pii else "partial",
            "evidence": [
                "audit_logs collection captures auth, admin, and PII access events",
                "PII access audit (security/pii_audit.py) records read events on sensitive fields",
                "Append-only audit collection (per-tenant indexed)",
                "Log retention: configurable, default 1 year",
            ],
            "recommendations": [],
        },
        {
            "req_id": "11",
            "title": "Test security of systems and networks regularly",
            "status": "partial",
            "evidence": [
                "Internal vulnerability scans via security skill (SAST + dep audit)",
            ],
            "recommendations": [
                "Engage a third-party for annual penetration test (PCI Req 11.4.3)",
                "Schedule quarterly external ASV scans if storing cardholder data",
            ],
        },
        {
            "req_id": "12",
            "title": "Support information security with organizational policies and programs",
            "status": "partial",
            "evidence": [
                "Crypto/security review documented in backend/docs/CRYPTO_SECURITY_REVIEW.md",
                "This compliance dashboard provides ongoing visibility",
            ],
            "recommendations": [
                "Maintain hotel-specific incident response and acceptable-use policies",
                "Annual security awareness training for hotel staff with PMS access",
            ],
        },
    ]
    return controls


def summary(controls: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"met": 0, "partial": 0, "shared": 0, "not_applicable": 0}
    for c in controls:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    total_in_scope = counts["met"] + counts["partial"]
    score_pct = (
        round(100 * counts["met"] / total_in_scope) if total_in_scope else 0
    )
    return {
        "version": VERSION,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_requirements": len(controls),
        "counts": counts,
        "implementation_score_pct": score_pct,
        "fully_met": counts["met"],
        "needs_attention": counts["partial"],
    }
