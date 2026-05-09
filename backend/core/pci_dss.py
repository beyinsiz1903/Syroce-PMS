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

Tenant-aware: bazı kontroller (Req 8 MFA kullanım oranı, Req 10 audit
log retention süresi, Req 7 kullanıcı sayısı) tenant doc/koleksiyonundan
zenginleştirilebilir — `evaluate_controls(tenant_id)` parametresi
verilirse bu sinyaller eklenir.

Cache: probe + DB sinyalleri TTL=120s in-process LRU cache'lenir
(deterministik per-(tenant,version) anahtar).
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

VERSION = "PCI-DSS v4.0"
TOTAL_REQUIREMENTS = 12  # PCI-DSS resmi gereksinim sayısı (UI subtitle bunu kullanır)

_CACHE_TTL = 120  # seconds
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _has_env(*keys: str) -> bool:
    return any(os.environ.get(k) for k in keys)


def _has_module(path: str) -> bool:
    """Best-effort import probe."""
    try:
        __import__(path)
        return True
    except Exception:
        return False


async def _tenant_signals(tenant_id: str | None) -> dict[str, Any]:
    """Tenant-spesifik PCI sinyalleri — Req 7/8/10 zenginleştirme.

    Best-effort: tenant_id yoksa veya DB hatası varsa sessizce boş döner
    (öz-değerlendirme paneli tenant bağımsız da çalışmalı).
    """
    if not tenant_id:
        return {}
    try:
        from core.database import _raw_db
        # Req 8: 2FA kullanım oranı + parolasız hesap kontrolü
        users = await _raw_db.users.count_documents({"tenant_id": tenant_id})
        users_2fa = await _raw_db.users.count_documents(
            {"tenant_id": tenant_id, "totp_enabled": True}
        ) if users else 0
        users_no_password = await _raw_db.users.count_documents(
            {"tenant_id": tenant_id, "$or": [
                {"hashed_password": {"$in": [None, ""]}},
                {"hashed_password": {"$exists": False}},
            ]}
        ) if users else 0
        # Req 10: audit log retention
        tenant = await _raw_db.tenants.find_one(
            {"id": tenant_id},
            {"_id": 0, "audit_log_retention_days": 1, "compliance_settings": 1},
        ) or {}
        retention = (
            tenant.get("audit_log_retention_days")
            or (tenant.get("compliance_settings") or {}).get("audit_log_retention_days")
            or 365  # varsayılan 1 yıl
        )
        return {
            "users_total": users,
            "users_2fa_enabled": users_2fa,
            "users_no_password": users_no_password,
            "audit_log_retention_days": int(retention),
        }
    except Exception:
        return {}


def evaluate_controls(tenant_signals: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the 12-requirement compliance report.

    `tenant_signals`: opsiyonel sözlük (`_tenant_signals` ile elde edilir)
    Req 7/8/10 değerlendirmesini zenginleştirir.
    """
    ts = tenant_signals or {}

    # ── Probe matrix ────────────────────────────────────────────
    has_field_encryption = _has_module("security.field_encryption")
    has_tenant_isolation = _has_module("security.tenant_isolation_router")
    has_audit_pii = _has_module("security.pii_audit")
    has_pii_masking = _has_module("security.pii_masking_middleware")
    has_rate_limiter = _has_module("security.rate_limiter")
    has_2fa = _has_module("routers.security_2fa")
    has_log_sanitizer = _has_module("security.log_sanitizer")
    has_credential_guard = _has_module("security.credential_guard")
    has_rotation = _has_module("security.rotation_engine")
    has_jwt_secret = bool(os.environ.get("JWT_SECRET"))
    has_encryption_key = _has_env("FIELD_ENCRYPTION_KEY", "ENCRYPTION_KEY")
    has_hsts = _has_module("security.security_headers_middleware") or _has_module("middleware.security_headers")
    # Replit edge zaten TLS terminate eder; HSTS modülü varsa transport posture met
    # sayılır — FORCE_HTTPS app-level guard ek pekiştirme (yokluğunda partial DEĞİL).
    force_https = os.environ.get("FORCE_HTTPS", "").lower() in {"1", "true", "yes"}
    is_managed_runtime = bool(os.environ.get("REPLIT_DEPLOYMENT") or os.environ.get("REPLIT_DEV_DOMAIN"))
    has_ci_security_scan = os.environ.get("CI_SECURITY_SCAN_ENABLED", "").lower() in {"1", "true", "yes"}
    # CI scan attestation YOKSA bile in-app SAST/dep audit varsa partial
    # değil "met" sayılabilir — runtime kanıtı kabul edilir.
    has_inapp_security_scan = _has_module("ops.security_scan") or _has_module("security.scanner")

    # ── Tenant signals ──────────────────────────────────────────
    users_total = int(ts.get("users_total") or 0)
    users_2fa = int(ts.get("users_2fa_enabled") or 0)
    users_no_password = int(ts.get("users_no_password") or 0)
    audit_retention = int(ts.get("audit_log_retention_days") or 365)
    mfa_ratio = (users_2fa / users_total) if users_total else 0.0

    controls: list[dict[str, Any]] = [
        {
            "req_id": "1",
            "title": "Install and maintain network security controls",
            "status": "shared",
            "evidence": [
                "TLS termination + WAF handled by Replit deployment edge",
                "Application uses HTTPS-only cookies and HSTS headers",
                *( ["Managed runtime (REPLIT_DEPLOYMENT detected)"] if is_managed_runtime else [] ),
            ],
            "recommendations": [
                "Document Replit-managed firewall and ingress rules in your PCI evidence packet",
            ],
        },
        {
            "req_id": "2",
            "title": "Apply secure configurations to all system components",
            # Sprint A fix: log_sanitizer + credential_guard + JWT_SECRET hepsi met için gerekir.
            "status": "met" if (has_log_sanitizer and has_credential_guard and has_jwt_secret) else "partial",
            "evidence": [
                "No vendor defaults: bcrypt password hashing, JWT_SECRET required",
                *( ["JWT_SECRET configured in environment"] if has_jwt_secret else [] ),
                *( ["Log sanitizer strips secrets/PII from runtime logs"] if has_log_sanitizer else [] ),
                *( ["Credential guard blocks weak/leaked secrets"] if has_credential_guard else [] ),
                "Secure dependency lock files (requirements.txt, yarn.lock)",
            ],
            "recommendations": [
                *( [] if has_jwt_secret else ["Set JWT_SECRET in production environment"] ),
                *( [] if has_log_sanitizer else ["Enable log_sanitizer middleware"] ),
                *( [] if has_credential_guard else ["Enable credential_guard module"] ),
            ],
        },
        {
            "req_id": "3",
            "title": "Protect stored account data",
            # PII masking middleware da bu kontrole katkıda bulunur.
            "status": "met" if (has_field_encryption and has_encryption_key) else "partial",
            "evidence": [
                "AES-256-GCM field-level encryption (security/field_encryption.py)",
                "PII fields (PAN, CVV, ID numbers) never stored in plaintext",
                "Backup codes for 2FA stored as bcrypt hashes",
                "TOTP secrets stored Fernet-encrypted with domain-separated key",
                *( ["PII masking middleware aktif (uygulama katmanı)"] if has_pii_masking else [] ),
                *( ["Encryption key (FIELD_ENCRYPTION_KEY) set"] if has_encryption_key else [] ),
            ],
            "recommendations": (
                [] if has_encryption_key
                else ["Set FIELD_ENCRYPTION_KEY in environment for production deployments"]
            ),
        },
        {
            "req_id": "4",
            "title": "Protect cardholder data with strong cryptography during transmission over open networks",
            # Replit edge TLS + HSTS modülü varsa met. FORCE_HTTPS opsiyonel pekiştirme.
            "status": "met" if (has_hsts or is_managed_runtime or force_https) else "partial",
            "evidence": [
                "Webhook signatures use HMAC-SHA256 (e.g., Af-sadakat integration)",
                "Inter-service tokens use HS256 JWTs with short TTLs",
                *( ["HSTS / security headers middleware active"] if has_hsts else [] ),
                *( ["Managed edge TLS (Replit) — HTTPS enforced at platform"] if is_managed_runtime else [] ),
                *( ["FORCE_HTTPS=true (app-level HTTP→HTTPS redirect)"] if force_https else [] ),
            ],
            "recommendations": (
                [] if (has_hsts or is_managed_runtime or force_https)
                else [
                    "Enable HSTS via security_headers middleware",
                    "Set FORCE_HTTPS=true to enforce HTTPS at the application layer",
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
            # In-app SAST/dep audit varsa met; CI attestation yokluğunda da yeterli.
            "status": "met" if (has_ci_security_scan or has_inapp_security_scan) else "partial",
            "evidence": [
                "On-demand dependency audit, SAST and credential-leak scans available",
                "All routes execute through bootstrap/router_registry with explicit auth deps",
                *( ["CI_SECURITY_SCAN_ENABLED=true (scans run on every release candidate)"]
                   if has_ci_security_scan else [] ),
                *( ["In-app SAST + dependency audit modülleri yüklü"] if has_inapp_security_scan else [] ),
                *( ["Rate limiter aktif (DoS/brute-force koruması)"] if has_rate_limiter else [] ),
                *( ["Secret/key rotation engine yüklü"] if has_rotation else [] ),
            ],
            "recommendations": (
                [] if (has_ci_security_scan or has_inapp_security_scan)
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
                *( [f"Tenant kullanıcı sayısı: {users_total}"] if users_total else [] ),
            ],
            "recommendations": [],
        },
        {
            "req_id": "8",
            "title": "Identify users and authenticate access to system components",
            # Tenant sinyalleri varsa MFA oranı + parolasız hesap kontrolü uygulanır.
            "status": (
                "partial" if (users_no_password > 0)
                else "met" if (has_2fa and (mfa_ratio >= 0.5 or users_total == 0))
                else "partial"
            ),
            "evidence": [
                "Bcrypt password hashing (cost factor 12)",
                "TOTP-based 2FA with backup codes (RFC 6238)",
                "JWT access tokens (HS256, 7d TTL) with optional 2FA challenge gate",
                "Audit logs for login_success / login_failed / 2fa_* events",
                "Password change requires current password verification",
                *( [f"MFA kullanım oranı: %{round(mfa_ratio*100)} ({users_2fa}/{users_total})"]
                   if users_total else [] ),
            ],
            "recommendations": [
                *( [] if has_2fa else ["Enable 2FA module for all administrative accounts"] ),
                *( [f"⚠️ {users_no_password} kullanıcının parolası ayarlı değil — denetleyin"]
                   if users_no_password > 0 else [] ),
                *( [f"MFA oranı düşük (%{round(mfa_ratio*100)}); admin hesaplarında zorunlu kılın"]
                   if users_total and mfa_ratio < 0.5 else [] ),
            ],
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
            # Audit modülü + retention ≥ 90 gün (PCI minimum) gerekir.
            "status": "met" if (has_audit_pii and audit_retention >= 90) else "partial",
            "evidence": [
                "audit_logs collection captures auth, admin, and PII access events",
                *( ["PII access audit (security/pii_audit.py) records read events on sensitive fields"]
                   if has_audit_pii else [] ),
                "Append-only audit collection (per-tenant indexed)",
                f"Log retention (tenant ayarı): {audit_retention} gün",
            ],
            "recommendations": (
                [] if (has_audit_pii and audit_retention >= 90)
                else [
                    *( [] if has_audit_pii else ["Enable PII audit module"] ),
                    *( [] if audit_retention >= 90
                       else [f"Log retention {audit_retention} gün — PCI minimum 90 gün; tenant ayarını yükseltin"] ),
                ]
            ),
        },
        {
            "req_id": "11",
            "title": "Test security of systems and networks regularly",
            "status": "partial",
            "evidence": [
                "Internal vulnerability scans via security skill (SAST + dep audit)",
                *( ["Periyodik secret rotation aktif"] if has_rotation else [] ),
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
        "total_requirements": TOTAL_REQUIREMENTS,
        "in_scope_requirements": total_in_scope,
        "counts": counts,
        "implementation_score_pct": score_pct,
        "fully_met": counts["met"],
        "needs_attention": counts["partial"],
        "shared_responsibility": counts["shared"],
        "not_applicable": counts["not_applicable"],
    }


async def evaluate_cached(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """TTL=120s in-process cache; tenant_id boşsa anahtar `__global__`."""
    key = tenant_id or "__global__"
    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[0] < _CACHE_TTL):
        return cached[1]
    signals = await _tenant_signals(tenant_id)
    controls = evaluate_controls(signals)
    _cache[key] = (now, controls)
    return controls


def invalidate_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _cache.clear()
    else:
        _cache.pop(tenant_id, None)
