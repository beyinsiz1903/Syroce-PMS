"""Auth endpoints: login, me, change-password, validate-password."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import (
    ACCOUNT_LOCKOUT_THRESHOLD,
    check_account_lockout, hash_password, record_login_attempt,
    require_auth, validate_password_strength, verify_password, create_token,
)
from db import db, users_col
from helpers import (
    _chgpw_throttle_check, _chgpw_throttle_reset,
    create_auth_audit_log, serialize_doc,
)
from rate_limit import limiter
from schemas import LoginRequest, PasswordChange

router = APIRouter()
logger = logging.getLogger("quickid")


@router.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest):
    client_ip = request.client.host if request.client else "unknown"

    lockout = await check_account_lockout(db, req.email)
    if lockout.get("locked"):
        logger.warning(f"🔒 Kilitli hesaba giriş denemesi: {req.email} (IP: {client_ip})")
        await create_auth_audit_log("login_blocked_locked", actor_email=req.email,
            target_email=req.email, outcome="blocked", reason="account_locked", ip_address=client_ip)
        raise HTTPException(status_code=423, detail={
            "message": lockout["message"],
            "locked": True,
            "remaining_minutes": lockout["remaining_minutes"],
        })

    user = await users_col.find_one({"email": req.email})
    # v108 (Bug DAI): timing-attack defense — user yoksa dummy bcrypt verify çalıştır.
    if not user:
        from auth import dummy_verify_password
        dummy_verify_password()
    if not user or not verify_password(req.password, user["password_hash"]):
        await record_login_attempt(db, req.email, success=False, ip_address=client_ip)
        remaining = lockout.get("remaining_attempts", ACCOUNT_LOCKOUT_THRESHOLD) - 1
        logger.warning(f"🔒 Başarısız giriş denemesi: {req.email} (kalan: {remaining}, IP: {client_ip})")
        await create_auth_audit_log("login_failed", actor_email=req.email,
            target_email=req.email, outcome="blocked",
            reason=("user_not_found" if not user else "wrong_password"),
            ip_address=client_ip, metadata={"remaining_attempts": max(remaining, 0)})
        detail_msg = "Geçersiz e-posta veya şifre"
        if 0 < remaining <= 2:
            detail_msg += f". {remaining} deneme hakkınız kaldı."
        elif remaining <= 0:
            detail_msg = "Hesap kilitlendi. 15 dakika sonra tekrar deneyin."
        raise HTTPException(status_code=401, detail=detail_msg)

    if not user.get("is_active", True):
        logger.warning(f"🔒 Devre dışı hesap ile giriş denemesi: {req.email}")
        await create_auth_audit_log("login_blocked_inactive",
            actor_id=str(user["_id"]), actor_email=req.email,
            target_id=str(user["_id"]), target_email=req.email,
            outcome="blocked", reason="account_disabled", ip_address=client_ip)
        raise HTTPException(status_code=403, detail="Hesap devre dışı")

    await record_login_attempt(db, req.email, success=True, ip_address=client_ip)
    await create_auth_audit_log("login_success",
        actor_id=str(user["_id"]), actor_email=req.email,
        target_id=str(user["_id"]), target_email=req.email,
        outcome="success", ip_address=client_ip, metadata={"role": user.get("role")})
    token = create_token({"sub": str(user["_id"]), "email": user["email"], "name": user["name"], "role": user["role"]})
    logger.info(f"✅ Giriş başarılı: {req.email} (rol: {user['role']}, IP: {client_ip})")
    return {
        "token": token,
        "user": {"id": str(user["_id"]), "email": user["email"], "name": user["name"], "role": user["role"]},
    }


@router.get("/api/auth/me")
async def get_me(user=Depends(require_auth)):
    db_user = await users_col.find_one({"email": user["email"]})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": serialize_doc(db_user)}


@router.post("/api/auth/change-password")
async def change_password(request: Request, req: PasswordChange, user=Depends(require_auth)):
    ip = request.client.host if request.client else None
    db_user = await users_col.find_one({"email": user["email"]})
    if not db_user:
        raise HTTPException(status_code=404)
    actor_id = str(db_user.get("_id"))
    actor_email = user["email"]
    # v48 (Bug CF): current_password is MANDATORY for self-change.
    if not req.current_password:
        await create_auth_audit_log(
            "password_change_failed",
            actor_id=actor_id, actor_email=actor_email,
            target_id=actor_id, target_email=actor_email,
            outcome="blocked", reason="current_password_missing", ip_address=ip)
        raise HTTPException(status_code=400, detail="Mevcut şifre zorunludur")
    try:
        await _chgpw_throttle_check(str(db_user.get("id") or db_user.get("_id") or user["email"]))
    except HTTPException as e:
        if e.status_code == 429:
            await create_auth_audit_log(
                "password_change_throttled",
                actor_id=actor_id, actor_email=actor_email,
                target_id=actor_id, target_email=actor_email,
                outcome="blocked", reason="rate_limit", ip_address=ip)
        raise
    if not verify_password(req.current_password, db_user["password_hash"]):
        await create_auth_audit_log(
            "password_change_failed",
            actor_id=actor_id, actor_email=actor_email,
            target_id=actor_id, target_email=actor_email,
            outcome="blocked", reason="wrong_password", ip_address=ip)
        raise HTTPException(status_code=401, detail="Mevcut şifre yanlış")
    _chgpw_throttle_reset(str(db_user.get("id") or db_user.get("_id") or user["email"]))
    # v108 (Bug DAI): same-password reuse engelle.
    if req.new_password == req.current_password:
        await create_auth_audit_log(
            "password_change_failed",
            actor_id=actor_id, actor_email=actor_email,
            target_id=actor_id, target_email=actor_email,
            outcome="blocked", reason="same_as_current", ip_address=ip)
        raise HTTPException(status_code=400, detail={
            "message": "Yeni şifre eskisinden farklı olmalı",
            "error_code": "SAME_AS_CURRENT_PASSWORD",
        })
    pwd_check = validate_password_strength(req.new_password)
    if not pwd_check["valid"]:
        await create_auth_audit_log(
            "password_change_failed",
            actor_id=actor_id, actor_email=actor_email,
            target_id=actor_id, target_email=actor_email,
            outcome="blocked", reason="weak_password", ip_address=ip,
            metadata={"strength": pwd_check.get("strength")})
        raise HTTPException(status_code=400, detail={
            "message": "Şifre gereksinimleri karşılanmadı",
            "errors": pwd_check["errors"],
            "strength": pwd_check["strength"],
        })
    # v107 EK-2: clear force_password_change on success.
    await users_col.update_one(
        {"email": user["email"]},
        {"$set": {
            "password_hash": hash_password(req.new_password),
            "updated_at": datetime.now(timezone.utc),
            "password_changed_at": datetime.now(timezone.utc),
            "force_password_change": False,
        }},
    )
    await create_auth_audit_log(
        "password_change_success",
        actor_id=actor_id, actor_email=actor_email,
        target_id=actor_id, target_email=actor_email,
        outcome="success", ip_address=ip)
    logger.info(f"🔑 Şifre değiştirildi: {user['email']}")
    return {"success": True, "message": "Şifre güncellendi"}


@router.post("/api/auth/validate-password", tags=["Kimlik Doğrulama"], summary="Şifre güçlülük kontrolü")
async def validate_password_endpoint(req: PasswordChange):
    """Şifre güçlülük kurallarını kontrol eder (kayıt/değişiklik öncesi)"""
    return validate_password_strength(req.new_password)
