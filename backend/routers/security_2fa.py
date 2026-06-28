"""Two-Factor Authentication endpoints (TOTP).

Flow:
  1. User → POST /api/2fa/setup        → returns secret + otpauth URI + QR (data URL)
                                          (NOT yet enabled — held in pending state)
  2. User scans QR, enters 6-digit code
  3. User → POST /api/2fa/setup/confirm → enables 2FA, returns one-time backup codes
  4. On future logins, /auth/login returns {requires_2fa: true, challenge_token}
  5. User → POST /api/auth/2fa/verify  → exchanges challenge for real access_token

Disable / regenerate require both password AND a valid current TOTP code.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import generate_qr_code, get_current_user, verify_password
from core.twofa import (
    consume_backup_code,
    consume_totp_counters,
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    generate_secret,
    hash_backup_codes,
    provisioning_uri,
    verify_totp,
    verify_totp_matching_counters,
)
from models.schemas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/2fa", tags=["2fa"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _user_doc(user_id: str) -> dict:
    doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return doc


# ── Status ────────────────────────────────────────────────────────
@router.get("/status")
async def status_2fa(current_user: User = Depends(get_current_user)) -> dict:
    doc = await _user_doc(current_user.id)
    return {
        "enabled": bool(doc.get("two_factor_enabled")),
        "pending_setup": bool(doc.get("two_factor_secret_pending_enc")),
        "backup_codes_remaining": len(doc.get("two_factor_backup_codes") or []),
        "enabled_at": doc.get("two_factor_enabled_at"),
        "last_used_at": doc.get("two_factor_last_used_at"),
    }


# ── Setup (pending) ───────────────────────────────────────────────
@router.post("/setup")
async def setup_2fa(current_user: User = Depends(get_current_user)) -> dict:
    """Generate a fresh secret and return QR + URI for the user to scan.

    The secret is held in a *pending* slot and is only promoted to
    `two_factor_secret_enc` after `setup/confirm` succeeds. This means
    repeated calls just rotate the pending secret — safe to retry.
    """
    doc = await _user_doc(current_user.id)
    if doc.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA zaten etkin")

    secret = generate_secret()
    label = current_user.email or current_user.username or current_user.id
    uri = provisioning_uri(secret, label)
    qr_data_url = generate_qr_code(uri)

    await db.users.update_one(
        {"id": current_user.id},
        {
            "$set": {
                "two_factor_secret_pending_enc": encrypt_secret(secret),
                "two_factor_setup_started_at": _now(),
            }
        },
    )
    return {
        "secret": secret,  # shown to user as manual fallback
        "otpauth_uri": uri,
        "qr_code": qr_data_url,  # data:image/png;base64,...
        "issuer": "Syroce PMS",
        "account": label,
    }


class ConfirmIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


@router.post("/setup/confirm")
async def confirm_setup(
    payload: ConfirmIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    doc = await _user_doc(current_user.id)
    if doc.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA zaten etkin")
    pending = doc.get("two_factor_secret_pending_enc")
    if not pending:
        raise HTTPException(status_code=400, detail="Önce /setup çağrılmalı")
    try:
        secret = decrypt_secret(pending)
    except ValueError:
        raise HTTPException(status_code=500, detail="2FA gizli anahtar şifre çözülemedi")
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Doğrulama kodu hatalı")

    backup_plain = generate_backup_codes()
    await db.users.update_one(
        {"id": current_user.id},
        {
            "$set": {
                "two_factor_enabled": True,
                "two_factor_secret_enc": pending,
                "two_factor_backup_codes": hash_backup_codes(backup_plain),
                "two_factor_enabled_at": _now(),
            },
            "$unset": {
                "two_factor_secret_pending_enc": "",
                "two_factor_setup_started_at": "",
            },
        },
    )
    await db.audit_logs.insert_one(
        {
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_enabled",
            "resource_type": "auth",
            "timestamp": _now(),
        }
    )
    return {
        "ok": True,
        "enabled": True,
        "backup_codes": backup_plain,
        "warning": "Bu kodlar bir daha gösterilmeyecek. Güvenli bir yere kaydedin.",
    }


# ── Disable ───────────────────────────────────────────────────────
class DisableIn(BaseModel):
    password: str
    code: str = Field(..., min_length=6, max_length=10)


@router.post("/disable")
async def disable_2fa(
    payload: DisableIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    doc = await _user_doc(current_user.id)
    if not doc.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA etkin değil")

    # v48 (Bug CE): per-user throttle on the password verify. A stolen
    # access_token would otherwise let an attacker brute-force the password
    # here at bcrypt-throttled speed, completely bypassing login throttles.
    from security.auth_throttle import SENSITIVE_AUTH_USER
    from security.auth_throttle import enforce as _throttle

    await _throttle(SENSITIVE_AUTH_USER, f"2fadis:{current_user.id}", "2FA kapatma denemesi")

    hashed = doc.get("hashed_password") or doc.get("password_hash") or doc.get("password", "")
    if not verify_password(payload.password, hashed):
        raise HTTPException(status_code=401, detail="Parola hatalı")
    # success → reset throttle so legitimate UX isn't penalised
    try:
        await SENSITIVE_AUTH_USER.reset(f"2fadis:{current_user.id}")
    except Exception:
        pass

    secret = decrypt_secret(doc.get("two_factor_secret_enc", ""))
    backup_hashes = doc.get("two_factor_backup_codes") or []
    totp_counters = verify_totp_matching_counters(secret, payload.code)
    matched_totp = bool(totp_counters)
    matched_backup = False
    if not matched_totp:
        matched_backup, _ = consume_backup_code(backup_hashes, payload.code)
    if not (matched_totp or matched_backup):
        raise HTTPException(status_code=401, detail="2FA kodu hatalı")

    # Bug CB v45: claim ALL matching TOTP counters atomically so the same
    # code cannot be reused for /disable, /regenerate-backup-codes, or
    # /auth/2fa/verify within the same window (incl. adjacent-counter
    # collisions).
    if matched_totp:
        won = await consume_totp_counters(db, current_user.id, totp_counters)
        if not won:
            raise HTTPException(status_code=401, detail="Bu doğrulama kodu zaten kullanıldı")

    await db.users.update_one(
        {"id": current_user.id},
        {
            "$unset": {
                "two_factor_enabled": "",
                "two_factor_secret_enc": "",
                "two_factor_backup_codes": "",
                "two_factor_enabled_at": "",
                "two_factor_last_used_at": "",
            }
        },
    )
    await db.audit_logs.insert_one(
        {
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_disabled",
            "resource_type": "auth",
            "timestamp": _now(),
        }
    )
    return {"ok": True, "enabled": False}


# ── Regenerate backup codes ───────────────────────────────────────
class RegenIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


@router.post("/regenerate-backup-codes")
async def regenerate_backup_codes(
    payload: RegenIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    doc = await _user_doc(current_user.id)
    if not doc.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA etkin değil")

    # v48 (Bug CE): per-user throttle on TOTP brute-force surface.
    from security.auth_throttle import SENSITIVE_AUTH_USER
    from security.auth_throttle import enforce as _throttle

    await _throttle(SENSITIVE_AUTH_USER, f"2farb:{current_user.id}", "yedek kod yenileme denemesi")

    secret = decrypt_secret(doc.get("two_factor_secret_enc", ""))
    totp_counters = verify_totp_matching_counters(secret, payload.code)
    if not totp_counters:
        raise HTTPException(status_code=401, detail="2FA kodu hatalı")
    try:
        await SENSITIVE_AUTH_USER.reset(f"2farb:{current_user.id}")
    except Exception:
        pass
    # Bug CB v45: claim ALL matching TOTP slots atomically (closes
    # adjacent-counter collisions and cross-endpoint replay).
    if not await consume_totp_counters(db, current_user.id, totp_counters):
        raise HTTPException(status_code=401, detail="Bu doğrulama kodu zaten kullanıldı")

    new_codes = generate_backup_codes()
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"two_factor_backup_codes": hash_backup_codes(new_codes)}},
    )
    await db.audit_logs.insert_one(
        {
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_backup_regenerated",
            "resource_type": "auth",
            "timestamp": _now(),
        }
    )
    return {
        "ok": True,
        "backup_codes": new_codes,
        "warning": "Önceki yedek kodlar geçersiz oldu.",
    }


# ── Admin policy hint (read-only): is 2FA required for this tenant? ─
@router.get("/policy")
async def get_policy(current_user: User = Depends(get_current_user)) -> dict:
    """Return effective 2FA policy: required_for_admins (default: false)."""
    if not current_user.tenant_id:
        return {"required_for_admins": False}
    t = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0, "security_policy": 1})
    pol = (t or {}).get("security_policy") or {}
    return {
        "required_for_admins": bool(pol.get("require_2fa_for_admins")),
    }
