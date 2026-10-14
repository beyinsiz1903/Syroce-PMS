"""Syroce Marketplace v1 — Cross-tenant B2B köprüsü.

Bu modül, Syroce Agent (acente otomasyonu) gibi dış uygulamaların birden çok
Syroce-PMS otelini tek API anahtarı ile aramasına, fiyatları görmesine ve
rezervasyon oluşturmasına olanak tanır.

Mimari farklar (mevcut /api/b2b ile karşılaştırma):
  • API key TENANT-BAĞIMSIZ tutulur (sysdb.marketplace_api_keys).
  • Otel kendi marketplace listing'ini açar/kapar (db.marketplace_listings, per-tenant).
  • Tüm agency endpoint'leri her istekte hangi otele yönelik olduğunu kabul eder
    (`tenant_id` veya `hotel_code` parametresi). Her istek için tenant context
    geçici olarak set edilir, sonra resetlenir.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import html
import io
import json
import logging
import os
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

import jwt as pyjwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field, model_validator

from core.agency_completion import pending_completion, public_booking
from core.agency_credit import assert_credit_capacity
from core.atomic_booking import BookingConflictError, assign_room_atomic, create_booking_atomic
from core.database import db
from core.marketplace_ledger_sync import NON_REVENUE_STATUSES, refresh_ledger_from_pms
from core.occupancy_pricing import OccupancyPricingError, calculate_occupancy_quote, find_occupancy_rule
from core.security import _is_super_admin, get_current_user, verify_password
from core.stay_overlap import stay_overlap_filter
from core.tenant_db import get_system_db, tenant_context
from models.schemas import User
from shared_kernel.idempotency import (
    build_request_hash,
    claim_idempotency,
    complete_idempotency,
    release_idempotency,
)

# Server-side fiyat hesaplamasının istemciden gelen total_amount'tan tolerans
# (TRY) — bu eşiği aşan farklarda istek reddedilir (price-spoofing koruması).
PRICE_TOLERANCE = 0.50

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace/v1", tags=["Marketplace v1"])

ADMIN_AGENCY_CONTEXT_MINUTES = 15
AGENCY_CONNECT_CODE_MINUTES = 5


class AgencyConnectAuthorize(BaseModel):
    client_id: str = Field(..., min_length=3, max_length=120)
    redirect_uri: str = Field(..., min_length=10, max_length=500)
    code_challenge: str = Field(..., min_length=43, max_length=128)
    state: str = Field(..., min_length=8, max_length=256)


class AgencyConnectExchange(BaseModel):
    client_id: str = Field(..., min_length=3, max_length=120)
    redirect_uri: str = Field(..., min_length=10, max_length=500)
    code: str = Field(..., min_length=32, max_length=512)
    code_verifier: str = Field(..., min_length=43, max_length=128)


def _agency_connect_clients() -> dict[str, dict]:
    """Return exact-match first-party clients; wildcards are intentionally unsupported."""
    configured = os.environ.get("SYROCE_AGENCY_CONNECT_CLIENTS_JSON", "").strip()
    if configured:
        try:
            clients = json.loads(configured)
            if isinstance(clients, dict):
                return clients
        except (TypeError, ValueError):
            logger.error("SYROCE_AGENCY_CONNECT_CLIENTS_JSON geçerli JSON değil")
        return {}
    # Safe first-party defaults. Production may replace this list entirely via env.
    return {
        "syroce_agency": {
            "name": "Syroce Agency",
            "redirect_uris": [
                "https://agency.syroce.com/auth/syroce/callback",
                "http://localhost:3000/auth/syroce/callback",
            ],
        }
    }


def _registered_agency_connect_client(client_id: str, redirect_uri: str) -> dict:
    client = _agency_connect_clients().get(client_id)
    allowed = client.get("redirect_uris", []) if isinstance(client, dict) else []
    if not client or redirect_uri not in allowed:
        raise HTTPException(400, "İstemci veya dönüş adresi kayıtlı değil")
    return client


def _pkce_s256(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip("=")


def _create_admin_agency_context_token(*, actor_user_id: str, agency_id: str) -> tuple[str, int]:
    """Mint a short-lived agency portal session without borrowing an agency identity."""
    from core.security import JWT_ALGORITHM, JWT_SECRET

    now_ts = datetime.now(UTC).timestamp()
    exp_ts = int(now_ts + ADMIN_AGENCY_CONTEXT_MINUTES * 60)
    payload = {
        "user_id": f"admin-agency-context:{agency_id}",
        "agency_id": agency_id,
        "actor_user_id": actor_user_id,
        "impersonation": True,
        "purpose": "admin_agency_context",
        "iat": now_ts,
        "jti": secrets.token_urlsafe(24),
        "exp": exp_ts,
        "type": "access",
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), exp_ts

# ─── Global Extranet UI ───────────────────────────────────────────────────


class MarketplaceLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/extranet/auth/login")
async def marketplace_extranet_login(req: MarketplaceLoginRequest, request: Request):
    """Global B2B Extranet arayüzü (Marketplace UI) için giriş."""
    from core.security import create_token

    sysdb = get_system_db()
    normalized_email = req.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    attempt_key = hashlib.sha256(f"{normalized_email}|{client_ip}".encode()).hexdigest()
    window_start = datetime.now(UTC) - timedelta(minutes=15)
    recent_failures = await sysdb.marketplace_login_attempts.count_documents(
        {"key": attempt_key, "success": False, "created_at": {"$gte": window_start}}
    )
    if recent_failures >= 5:
        raise HTTPException(status_code=429, detail="Çok fazla başarısız giriş. 15 dakika sonra tekrar deneyin")

    # Global users (tenant_id = null or "SYROCE_GLOBAL" etc.)
    # Assuming marketplace_agent users are in the global users collection.
    from security.encrypted_lookup import build_user_email_query, decrypt_user_doc

    user = decrypt_user_doc(await sysdb.users.find_one(build_user_email_query(normalized_email)))

    if not user or user.get("is_active") is False or not verify_password(req.password, user.get("hashed_password", "")):
        await sysdb.marketplace_login_attempts.insert_one(
            {"key": attempt_key, "email_hash": hashlib.sha256(normalized_email.encode()).hexdigest(), "success": False, "created_at": datetime.now(UTC)}
        )
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")

    role = getattr(user.get("role"), "value", user.get("role"))
    roles = user.get("roles") or []
    if role != "marketplace_agent" and "marketplace_agent" not in roles:
        raise HTTPException(status_code=403, detail="Sadece global acente kullanıcıları girebilir")

    if not user.get("agency_id"):
        raise HTTPException(status_code=403, detail="Kullanıcıya atanmış bir marketplace acentesi yok")

    agency = await sysdb.marketplace_agencies.find_one({"id": user["agency_id"], "status": "active"})
    if not agency:
        raise HTTPException(status_code=403, detail="Marketplace acentesi aktif değil")

    token = create_token(user["id"], None)
    await sysdb.marketplace_login_attempts.delete_many({"key": attempt_key})

    return {
        "token": token,
        "user": {"id": user["id"], "name": user.get("name", ""), "email": user.get("email", ""), "role": "marketplace_agent", "agency_id": user["agency_id"]},
        "agency": {"id": agency["id"], "name": agency.get("name", "")},
    }


async def get_marketplace_agency(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> dict:
    """Cross-tenant API key veya JWT doğrulama.
    Acenteler Syroce Agency otomasyonu için X-API-Key,
    Global Extranet UI üzerinden giriş için JWT Bearer token kullanabilir."""
    sysdb = get_system_db()
    agency_id = None
    actor_user = None
    impersonation = None

    if authorization and authorization.lower().startswith("bearer "):
        try:
            from core.security import JWT_ALGORITHM, JWT_SECRET, is_jti_revoked

            token = authorization.split(" ", 1)[1]
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") not in (None, "access") or not payload.get("user_id"):
                raise HTTPException(401, "Geçersiz acente erişim token'ı")
            if payload.get("jti") and await is_jti_revoked(payload["jti"]):
                raise HTTPException(401, "Acente oturumu sonlandırılmış")
            if payload.get("impersonation") is True:
                if payload.get("purpose") != "admin_agency_context":
                    raise HTTPException(401, "Geçersiz acente görüntüleme oturumu")
                actor_id = payload.get("actor_user_id")
                agency_id = payload.get("agency_id")
                if not actor_id or not agency_id:
                    raise HTTPException(401, "Acente görüntüleme kapsamı geçersiz")
                actor = await sysdb.users.find_one(
                    {"$or": [{"id": actor_id}, {"user_id": actor_id}]},
                    {"_id": 0, "id": 1, "user_id": 1, "name": 1, "email": 1, "role": 1, "roles": 1, "is_active": 1},
                )
                actor_role = getattr((actor or {}).get("role"), "value", (actor or {}).get("role"))
                actor_roles = (actor or {}).get("roles") or []
                if not actor or actor.get("is_active") is False or (actor_role != "super_admin" and "super_admin" not in actor_roles):
                    raise HTTPException(401, "Süperadmin görüntüleme yetkisi artık geçerli değil")
                impersonation = {
                    "active": True,
                    "actor_id": actor.get("id") or actor.get("user_id"),
                    "actor_name": actor.get("name", ""),
                    "expires_at": int(payload.get("exp") or 0),
                    "jti": payload.get("jti"),
                }
                actor_user = {
                    "id": f"admin-agency-context:{agency_id}",
                    "name": "Süperadmin önizlemesi",
                    "email": actor.get("email", ""),
                    "role": "marketplace_agent",
                }
            else:
                user = await sysdb.users.find_one(
                    {"$or": [{"id": payload["user_id"]}, {"user_id": payload["user_id"]}]},
                    {"_id": 0},
                )
                if not user or user.get("is_active") is False:
                    raise HTTPException(401, "Acente kullanıcısı aktif değil")
                from security.encrypted_lookup import decrypt_user_doc

                user = decrypt_user_doc(user)
                invalid_before = user.get("tokens_invalid_before")
                if invalid_before and float(payload.get("iat") or 0) < float(invalid_before):
                    raise HTTPException(401, "Acente oturumu artık geçerli değil")
                raw_role = user.get("role")
                role = getattr(raw_role, "value", raw_role)
                roles = user.get("roles") or []
                if role != "marketplace_agent" and "marketplace_agent" not in roles:
                    raise HTTPException(403, "Kullanıcı bir global acente yetkilisi değil")
                agency_id = user.get("agency_id")
                actor_user = {
                    "id": user.get("id") or user.get("user_id"),
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "role": "marketplace_agent",
                }
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
            raise HTTPException(401, "Geçersiz veya süresi dolmuş acente token'ı")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(401, "Geçersiz token")
    elif x_api_key:
        if not x_api_key.startswith("syroce_mkt_"):
            raise HTTPException(401, "Marketplace API için syroce_mkt_ anahtarı gerekli")
        key_hash = _hash_key(x_api_key)
        key_doc = await sysdb.marketplace_api_keys.find_one({"key_hash": key_hash, "is_active": True}, {"_id": 0})
        if not key_doc:
            raise HTTPException(401, "Geçersiz veya devre dışı marketplace API key")
        agency_id = key_doc["agency_id"]

        await sysdb.marketplace_api_keys.update_one(
            {"key_hash": key_hash},
            {
                "$set": {
                    "last_used_at": _now_iso(),
                    "last_used_ip": request.client.host if request.client else None,
                },
                "$inc": {"usage_count": 1},
            },
        )
    else:
        raise HTTPException(401, "Kimlik doğrulama gereklidir (X-API-Key veya JWT)")

    if not agency_id:
        raise HTTPException(403, "Acente ID bulunamadı")

    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id, "status": "active"}, {"_id": 0})
    if not agency:
        raise HTTPException(403, "Marketplace acentesi aktif değil")

    # Determine source for %1 vs %2 billing differentiation
    source = "extranet_ui" if authorization else "syroce_agency_app"

    return {
        "agency_id": agency["id"],
        "agency_name": agency.get("name", ""),
        "default_commission_pct": agency.get("default_commission_pct", 12.0),
        "platform_fee_pct": agency.get("platform_fee_pct"),
        "contact_email": agency.get("contact_email", ""),
        "source": source,
        "user": actor_user,
        "impersonation": impersonation,
    }


@router.get("/connect/client")
async def marketplace_connect_client(client_id: str = Query(...), redirect_uri: str = Query(...)):
    """Validate and describe a first-party client before rendering consent."""
    client = _registered_agency_connect_client(client_id, redirect_uri)
    return {"client_id": client_id, "name": client.get("name") or client_id}


@router.post("/connect/authorize")
async def marketplace_connect_authorize(
    payload: AgencyConnectAuthorize,
    agency: dict = Depends(get_marketplace_agency),
):
    """Issue a five-minute, single-use authorization code protected by PKCE."""
    client = _registered_agency_connect_client(payload.client_id, payload.redirect_uri)
    if not payload.code_challenge.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "PKCE code_challenge geçersiz")

    sysdb = get_system_db()
    raw_code = secrets.token_urlsafe(48)
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=AGENCY_CONNECT_CODE_MINUTES)
    await sysdb.agency_connect_codes.insert_one(
        {
            "id": _uuid(),
            "code_hash": _hash_key(raw_code),
            "client_id": payload.client_id,
            "client_name": client.get("name") or payload.client_id,
            "redirect_uri": payload.redirect_uri,
            "code_challenge": payload.code_challenge,
            "code_challenge_method": "S256",
            "agency_id": agency["agency_id"],
            "created_by": (agency.get("user") or {}).get("id"),
            "created_at": now,
            "expires_at": expires_at,
            "used_at": None,
        }
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency["agency_id"],
        action="agency_connect_authorized",
        details={"client_id": payload.client_id},
    )
    return {"code": raw_code, "state": payload.state, "expires_in": AGENCY_CONNECT_CODE_MINUTES * 60}


@router.post("/connect/token")
async def marketplace_connect_token(payload: AgencyConnectExchange):
    """Exchange a PKCE code server-to-server; the browser never receives the API key."""
    client = _registered_agency_connect_client(payload.client_id, payload.redirect_uri)
    challenge = _pkce_s256(payload.code_verifier)
    sysdb = get_system_db()
    now = datetime.now(UTC)
    result = await sysdb.agency_connect_codes.update_one(
        {
            "code_hash": _hash_key(payload.code),
            "client_id": payload.client_id,
            "redirect_uri": payload.redirect_uri,
            "code_challenge": challenge,
            "used_at": None,
            "expires_at": {"$gt": now},
        },
        {"$set": {"used_at": now}},
    )
    if result.modified_count != 1:
        raise HTTPException(400, "Yetkilendirme kodu geçersiz, kullanılmış veya süresi dolmuş")

    code_doc = await sysdb.agency_connect_codes.find_one(
        {"code_hash": _hash_key(payload.code), "client_id": payload.client_id},
        {"_id": 0},
    )
    if not code_doc:
        raise HTTPException(400, "Yetkilendirme kaydı bulunamadı")

    await sysdb.marketplace_api_keys.update_many(
        {"agency_id": code_doc["agency_id"], "client_id": payload.client_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso(), "revocation_reason": "reconnected"}},
    )
    raw_key, key_doc = await _create_marketplace_api_key(
        sysdb,
        code_doc["agency_id"],
        label=f"{client.get('name') or payload.client_id} hesabıyla bağlantı",
    )
    await sysdb.marketplace_api_keys.update_one(
        {"id": key_doc["id"]},
        {"$set": {"client_id": payload.client_id, "grant_type": "authorization_code_pkce"}},
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=code_doc["agency_id"],
        action="agency_connect_token_issued",
        details={"client_id": payload.client_id, "key_id": key_doc["id"]},
    )
    return {
        "access_token": raw_key,
        "token_type": "X-API-Key",
        "agency_id": code_doc["agency_id"],
    }

@router.get("/extranet/my-hotels")
async def marketplace_my_hotels(agency: dict = Depends(get_marketplace_agency)):
    """Acentenin aktif sözleşmesi olan otelleri listeler."""
    from routers.agency_contracts import list_partner_tenant_ids

    sysdb = get_system_db()
    tenant_ids = await list_partner_tenant_ids(agency["agency_id"])

    hotels = []
    if tenant_ids:
        listings = await sysdb.marketplace_listings.find(
            {"tenant_id": {"$in": tenant_ids}, "is_listed": True}, {"_id": 0}
        ).to_list(1000)

        for listing in listings:
            hotels.append({
                "tenant_id": listing["tenant_id"],
                "name": listing.get("hotel_name", "Bilinmeyen Otel"),
                "city": listing.get("city", ""),
                "country": listing.get("country", ""),
                "currency": listing.get("currency", "TRY"),
            })

    return {"hotels": hotels}


class MarketplaceNotificationSettings(BaseModel):
    new_reservation: bool = True
    reservation_change: bool = True
    cancellation_request: bool = True
    payment_reconciliation: bool = True
    contract_updates: bool = True


class MarketplacePortalSettingsUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    contact_email: EmailStr
    contact_phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=300)
    notification_preferences: MarketplaceNotificationSettings = Field(default_factory=MarketplaceNotificationSettings)
    allowed_widget_origins: list[str] = Field(default_factory=list, max_length=20)
    widget_brand_color: str = Field(default="#047857", pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def normalize_widget_origins(self):
        normalized = []
        for value in self.allowed_widget_origins:
            origin = str(value or "").strip().rstrip("/")
            if not origin:
                continue
            if not origin.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                raise ValueError("Web sitesi adresi HTTPS ile başlamalıdır")
            normalized.append(origin)
        self.allowed_widget_origins = list(dict.fromkeys(normalized))
        return self


def _marketplace_widget_token(agency_doc: dict) -> str:
    """Create a public, strictly widget-scoped identifier (never an API key)."""
    from core.security import JWT_ALGORITHM, JWT_SECRET

    return pyjwt.encode(
        {
            "type": "marketplace_widget",
            "agency_id": agency_doc["id"],
            "version": int(agency_doc.get("widget_token_version") or 1),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


async def get_marketplace_widget_agency(
    x_widget_token: str | None = Header(None, alias="X-Widget-Token"),
    x_widget_origin: str | None = Header(None, alias="X-Widget-Origin"),
) -> dict:
    """Authenticate the public widget without granting extranet/API access."""
    if not x_widget_token:
        raise HTTPException(401, "Widget erişim anahtarı eksik")
    try:
        from core.security import JWT_ALGORITHM, JWT_SECRET

        payload = pyjwt.decode(x_widget_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "Widget erişim anahtarı geçersiz")
    if payload.get("type") != "marketplace_widget" or not payload.get("agency_id"):
        raise HTTPException(401, "Widget erişim kapsamı geçersiz")

    sysdb = get_system_db()
    agency_doc = await sysdb.marketplace_agencies.find_one(
        {"id": payload["agency_id"], "status": "active"}, {"_id": 0}
    )
    if not agency_doc:
        raise HTTPException(403, "Acente hesabı aktif değil")
    if int(payload.get("version") or 0) != int(agency_doc.get("widget_token_version") or 1):
        raise HTTPException(401, "Widget erişim anahtarı yenilenmiş")

    origin = str(x_widget_origin or "").strip().rstrip("/")
    allowed = {str(item).strip().rstrip("/") for item in agency_doc.get("allowed_widget_origins") or []}
    if not origin or origin not in allowed:
        raise HTTPException(403, "Bu web sitesi widget kullanımı için yetkilendirilmemiş")
    return {
        "agency_id": agency_doc["id"],
        "agency_name": agency_doc.get("name", ""),
        "default_commission_pct": agency_doc.get("default_commission_pct", 12.0),
        "platform_fee_pct": agency_doc.get("platform_fee_pct"),
        "contact_email": agency_doc.get("contact_email", ""),
        "source": "agency_website_widget",
        "widget_origin": origin,
        "widget_brand_color": agency_doc.get("widget_brand_color") or "#047857",
    }


@router.get("/extranet/profile")
async def marketplace_extranet_profile(agency: dict = Depends(get_marketplace_agency)):
    """Reload-safe identity for the multi-property agency portal."""
    hotel_result = await marketplace_my_hotels(agency)
    return {
        "agency": {
            "id": agency["agency_id"],
            "name": agency.get("agency_name", ""),
            "contact_email": agency.get("contact_email", ""),
        },
        "user": agency.get("user"),
        "hotels": hotel_result["hotels"],
        "impersonation": {
            key: value for key, value in (agency.get("impersonation") or {}).items() if key != "jti"
        } or None,
    }


@router.post("/extranet/admin-context/exit")
async def marketplace_admin_context_exit(agency: dict = Depends(get_marketplace_agency)):
    """Revoke an agency preview token and record its explicit close event."""
    context = agency.get("impersonation") or {}
    if not context.get("active") or not context.get("jti") or not context.get("expires_at"):
        raise HTTPException(409, "Etkin süperadmin acente görünümü bulunamadı")

    from core.security import revoke_jti

    revoked = await revoke_jti(
        context["jti"],
        int(context["expires_at"]),
        user_id=context.get("actor_id"),
        reason="admin_agency_context_exit",
    )
    if not revoked:
        raise HTTPException(401, "Acente görüntüleme oturumu daha önce kapatılmış")
    await _record_marketplace_audit(
        get_system_db(),
        agency_id=agency["agency_id"],
        action="admin_agency_context_exit",
        details={"actor_user_id": context.get("actor_id")},
    )
    return {"ok": True}


@router.get("/extranet/settings")
async def marketplace_extranet_settings(agency: dict = Depends(get_marketplace_agency)):
    """Return agency-scoped account settings without exposing credentials."""
    sysdb = get_system_db()
    agency_doc = await sysdb.marketplace_agencies.find_one(
        {"id": agency["agency_id"], "status": "active"}, {"_id": 0}
    )
    if not agency_doc:
        raise HTTPException(404, "Acente hesabı bulunamadı")
    users = await sysdb.users.find(
        {"agency_id": agency["agency_id"], "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "roles": 1, "last_login": 1, "created_at": 1},
    ).to_list(200)
    keys = await sysdb.marketplace_api_keys.find(
        {"agency_id": agency["agency_id"], "is_active": True},
        {"_id": 0, "id": 1, "key_prefix": 1, "created_at": 1, "last_used_at": 1, "usage_count": 1},
    ).to_list(50)
    return {
        "agency": {
            "id": agency_doc["id"],
            "name": agency_doc.get("name", ""),
            "contact_email": agency_doc.get("contact_email", ""),
            "contact_phone": agency_doc.get("contact_phone", ""),
            "address": agency_doc.get("address", ""),
            "website": agency_doc.get("website", ""),
            "status": agency_doc.get("status", "active"),
        },
        "notification_preferences": agency_doc.get("notification_preferences") or MarketplaceNotificationSettings().model_dump(),
        "widget": {
            "allowed_origins": agency_doc.get("allowed_widget_origins") or [],
            "brand_color": agency_doc.get("widget_brand_color") or "#047857",
            "agency_id": agency_doc["id"],
            "token": _marketplace_widget_token(agency_doc),
        },
        "users": users,
        "api_keys": keys,
    }


@router.patch("/extranet/settings")
async def update_marketplace_extranet_settings(
    data: MarketplacePortalSettingsUpdate,
    agency: dict = Depends(get_marketplace_agency),
):
    """Update only the signed-in agency's editable portal settings."""
    sysdb = get_system_db()
    updates = {
        "name": data.name.strip(),
        "contact_email": str(data.contact_email).strip().lower(),
        "contact_phone": data.contact_phone.strip(),
        "address": data.address.strip(),
        "website": data.website.strip(),
        "notification_preferences": data.notification_preferences.model_dump(),
        "allowed_widget_origins": data.allowed_widget_origins,
        "widget_brand_color": data.widget_brand_color.lower(),
        "updated_at": _now_iso(),
        "updated_by": (agency.get("user") or {}).get("id"),
    }
    result = await sysdb.marketplace_agencies.update_one(
        {"id": agency["agency_id"], "status": "active"}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Acente hesabı bulunamadı")
    await sysdb.marketplace_audit_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "agency_id": agency["agency_id"],
            "actor_user_id": (agency.get("user") or {}).get("id"),
            "action": "portal_settings_updated",
            "changed_fields": sorted(updates.keys()),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return {"ok": True, "message": "Acente ayarları güncellendi"}


# ─── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def _record_marketplace_audit(
    sysdb,
    *,
    agency_id: str,
    action: str,
    details: dict | None = None,
) -> None:
    """Persist an admin-visible marketplace audit record without secrets.

    Raw API keys and hashes must never enter a business/audit collection.  The
    public prefix and generated key id are enough to trace a credential
    lifecycle event without turning the audit trail into a credential store.
    """
    await sysdb.marketplace_audit_logs.insert_one(
        {
            "id": _uuid(),
            "agency_id": agency_id,
            "actor_type": "system_admin",
            "action": action,
            "details": details or {},
            "created_at": _now_iso(),
        }
    )


def _last_occupied_date(check_in: str, check_out: str) -> str:
    """Convert the exclusive checkout boundary to the final sold room-night."""
    from datetime import timedelta

    ci = datetime.fromisoformat(check_in).date()
    co = datetime.fromisoformat(check_out).date()
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")
    return (co - timedelta(days=1)).isoformat()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def _create_marketplace_api_key(sysdb, agency_id: str, *, label: str) -> tuple[str, dict]:
    """Create one recoverable-once credential while persisting only its hash."""
    raw_key = f"syroce_mkt_{secrets.token_urlsafe(32)}"
    key_doc = {
        "id": _uuid(),
        "agency_id": agency_id,
        "label": label.strip(),
        "key_hash": _hash_key(raw_key),
        "key_prefix": raw_key[:18] + "...",
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "last_used_at": None,
        "last_used_ip": None,
    }
    await sysdb.marketplace_api_keys.insert_one(key_doc)
    return raw_key, key_doc


def _require_hotel_admin(user: User) -> str:
    """Otel admin/sahibi rollerini doğrular ve tenant_id döner. Super_admin always allowed."""
    if _is_super_admin(user):
        if not user.tenant_id:
            raise HTTPException(403, "Geçerli bir otel kiracısı yok")
        return user.tenant_id
    role = getattr(user.role, "value", user.role)
    if role not in ("admin", "super_admin", "supervisor"):
        raise HTTPException(403, "Marketplace otel ayarlarını yalnız yönetici roller yönetebilir")
    if not user.tenant_id:
        raise HTTPException(403, "Geçerli bir otel kiracısı yok")
    return user.tenant_id


async def _try_get_super_admin(authorization: str | None = Header(None)) -> bool:
    """Authorization header'dan opsiyonel super_admin tespiti (401 atmaz)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization.split(" ", 1)[1])
        user = await get_current_user(creds)
        return _is_super_admin(user)
    except Exception:
        return False


def _require_system_admin(
    token: str | None = Header(None, alias="X-Marketplace-Admin-Token"),
    is_sa: bool = Depends(_try_get_super_admin),
) -> bool:
    """Sistem yöneticisi yetkisi: env var token VEYA super_admin JWT ile koruma.

    Super_admin (role veya roles[]) her zaman geçerli sayılır.
    """
    if is_sa:
        return True
    expected = os.getenv("MARKETPLACE_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Marketplace admin yapılandırılmamış")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Geçersiz marketplace admin token")
    return True


# ─── Cross-tenant Agency Auth ─────────────────────────────────────────────





async def _get_listing_or_404(tenant_id: str) -> dict:
    """Bir otelin marketplace listing'ini döner. Liste edilmemişse 404."""
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id, "is_listed": True}, {"_id": 0})
    if not listing:
        raise HTTPException(404, "Bu otel marketplace'te listelenmemiş")
    tenant = await sysdb.tenants.find_one({"id": tenant_id}, {"_id": 0, "subscription_status": 1, "is_active": 1})
    if not tenant or tenant.get("is_active") is False or tenant.get("subscription_status", "active") != "active":
        raise HTTPException(404, "Bu otel şu anda rezervasyon kabul etmiyor")
    return listing


async def _departure_restriction_row(
    *, tenant_id: str, agency_id: str, room_type: str, check_out: str, rate_plan_code: str,
    allow_base_rate_fallback: bool,
) -> dict:
    """Return the calendar row of the departure date; it only carries the CTD restriction."""
    plan_filter = (
        {"rate_plan_code": {"$exists": False}} if rate_plan_code == "LEGACY" else {"rate_plan_code": rate_plan_code}
    )
    query = {"tenant_id": tenant_id, "room_type_code": room_type, "date": check_out, **plan_filter}
    projection = {"_id": 0, "date": 1, "ctd": 1}

    async def _first(collection, extra: dict) -> dict | None:
        rows = await collection.find({**query, **extra}, projection).to_list(1)
        return next((row for row in rows if row.get("date") == check_out), None)

    row = await _first(db.agency_rate_calendar, {"agency_id": agency_id})
    if row is None and allow_base_rate_fallback:
        row = await _first(db.hr_rate_calendar, {}) or await _first(db.rate_calendar, {})
    return row or {}


async def _marketplace_stay_price(
    *, tenant_id: str, agency_id: str, room_type: str, check_in: str, check_out: str, fallback_rate: float,
    rate_plan_code: str | None = None,
    exclude_booking_id: str | None = None,
    allow_base_rate_fallback: bool = False,
) -> dict:
    """Return the exact sellable nightly rates shared with this agency.

    By default an agency can sell only products explicitly distributed through
    its calendar. A contract may opt in to the legacy hotel/base-rate fallback.
    A stop-sell or zero agency allotment closes the whole stay.
    """
    dates = _date_range(check_in, check_out)
    query = {"tenant_id": tenant_id, "room_type_code": room_type, "date": {"$in": dates}}
    agency_rows = await db.agency_rate_calendar.find(
        {**query, "agency_id": agency_id}, {"_id": 0}
    ).to_list(max(len(dates) * 8, 32))
    base_rows = []
    if allow_base_rate_fallback:
        base_rows = await db.hr_rate_calendar.find(query, {"_id": 0}).to_list(max(len(dates) * 8, 32))
        if not base_rows:
            base_rows = await db.rate_calendar.find(query, {"_id": 0}).to_list(max(len(dates) * 8, 32))

    plans = {str(row.get("rate_plan_code") or "LEGACY") for row in agency_rows + base_rows}
    if not plans and allow_base_rate_fallback:
        plans = {"BASE"}
    if not plans:
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "agency_rate_not_shared"}
    if rate_plan_code is None:
        if len(plans) > 1:
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "rate_plan_required"}
        rate_plan_code = next(iter(plans), "BASE")
    if plans and rate_plan_code not in plans or not plans and rate_plan_code != "BASE":
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "unknown_rate_plan"}
    agency_rows = [row for row in agency_rows if str(row.get("rate_plan_code") or "LEGACY") == rate_plan_code]
    base_rows = [row for row in base_rows if str(row.get("rate_plan_code") or "LEGACY") == rate_plan_code]
    agency_by_date = {row.get("date"): row for row in agency_rows}
    base_by_date = {row.get("date"): row for row in base_rows}
    if len(agency_by_date) != len(agency_rows) or len(base_by_date) != len(base_rows):
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "duplicate_rate_plan_night"}
    effective_rows = [agency_by_date.get(day) or base_by_date.get(day) or {} for day in dates]
    arrival_row = effective_rows[0] if effective_rows else {}
    if arrival_row.get("cta") is True:
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "closed_to_arrival"}
    if len(dates) < int(arrival_row.get("min_los_arrival") or 1):
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "min_stay_arrival"}
    departure_row = await _departure_restriction_row(
        tenant_id=tenant_id, agency_id=agency_id, room_type=room_type, check_out=check_out,
        rate_plan_code=rate_plan_code, allow_base_rate_fallback=allow_base_rate_fallback,
    )
    if departure_row.get("ctd") is True:
        return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "closed_to_departure"}
    for field in ("meal_plan", "cancellation_policy"):
        if len({json.dumps(row.get(field), sort_keys=True) for row in effective_rows if row.get(field) is not None}) > 1:
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "inconsistent_product_terms"}
    nightly_rates: list[dict] = []
    shared_availability: list[int] = []
    for date in dates:
        row = agency_by_date.get(date) or base_by_date.get(date) or {}
        if not row or row.get("rate") is None:
            if not (allow_base_rate_fallback and rate_plan_code == "BASE"):
                return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "missing_shared_rate_night"}
        # Stay-through minimum: every occupied night must permit this stay.
        # Checkout is exclusive and must not impose a minimum on the stay.
        if len(dates) < int(row.get("min_stay") or 1):
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "min_stay"}
        if row.get("max_stay") and len(dates) > int(row["max_stay"]):
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "max_stay"}
        if row.get("stop_sell") is True or (
            date in agency_by_date
            and row.get("availability") is not None
            and int(row["availability"]) <= 0
        ):
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0}
        rate = row.get("rate")
        if rate is None:
            rate = fallback_rate
        if date in agency_by_date and row.get("availability") is not None:
            tomorrow = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
            used = await db.bookings.count_documents({
                **({"id": {"$ne": exclude_booking_id}} if exclude_booking_id else {}),
                "tenant_id": tenant_id, "agency_id": agency_id, "room_type": room_type,
                "$or": [{"rate_plan_code": rate_plan_code}, {"rate_plan_code": {"$exists": False}}],
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                # Checkout day is not an occupied night, regardless of the
                # stored check-out hour (typically 11:00).
                **stay_overlap_filter(date, tomorrow),
            })
            remaining = max(0, int(row["availability"]) - used)
            if remaining == 0:
                return {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "agency_allotment_exhausted"}
            shared_availability.append(remaining)
        nightly_rates.append({"date": date, "rate": round(float(rate or 0), 2)})
    result = {
        "rate_plan_code": rate_plan_code,
        "meal_plan": next((row["meal_plan"] for row in effective_rows if row.get("meal_plan")), None),
        "cancellation_policy": next((row["cancellation_policy"] for row in effective_rows if row.get("cancellation_policy")), None),
        "sellable": True,
        "nightly_rates": nightly_rates,
        "total_price": round(sum(item["rate"] for item in nightly_rates), 2),
    }
    if shared_availability:
        # A stay can only sell the lowest allotment available on any occupied
        # night. Physical PMS inventory remains the upper safety bound.
        result["shared_availability"] = min(shared_availability)
    return result


async def _agency_rate_plans(tenant_id, agency_id, room_type, check_in, check_out, *, allow_base_rate_fallback=False):
    query = {"tenant_id": tenant_id, "room_type_code": room_type, "date": {"$in": _date_range(check_in, check_out)}}
    agency_rows = await db.agency_rate_calendar.find({**query, "agency_id": agency_id}, {"_id": 0}).to_list(5000)
    base_rows = []
    if allow_base_rate_fallback:
        base_rows = await db.hr_rate_calendar.find(query, {"_id": 0}).to_list(5000)
        if not base_rows:
            base_rows = await db.rate_calendar.find(query, {"_id": 0}).to_list(5000)
    plans = {str(row.get("rate_plan_code") or "LEGACY") for row in agency_rows + base_rows}
    return sorted(plans or ({"BASE"} if allow_base_rate_fallback else set()))


def _rate_product_snapshot(plan_code, room, contract, pricing=None):
    """Immutable sale terms, sourced from the selected plan and approved contract."""
    pricing = pricing or {}
    meal = pricing.get("meal_plan") or (plan_code.upper() if plan_code.upper() in {"RO", "BB", "HB", "FB", "AI"} else (room.get("meal_plan") or room.get("board_type") or "unspecified"))
    return {"rate_plan_code": plan_code, "meal_plan": meal,
            "cancellation_policy": pricing.get("cancellation_policy") or contract.get("cancellation_policy") or {}}


async def _marketplace_occupancy_price(
    *, tenant_id: str, room: dict, pricing: dict, adults: int, child_ages: list[int]
) -> dict:
    """Apply the hotel's saved occupancy policy to each shared nightly rate."""
    rule = await find_occupancy_rule(db, tenant_id, room)
    if not rule:
        return {**pricing, "occupancy_pricing": None}

    quoted_nights = []
    total = 0.0
    try:
        for item in pricing.get("nightly_rates", []):
            quote = calculate_occupancy_quote(
                base_nightly_rate=item["rate"],
                nights=1,
                adults=adults,
                children_ages=child_ages,
                rule=rule,
            )
            quoted_nights.append({**item, "base_rate": item["rate"], "rate": quote["nightly_total"]})
            total += quote["nightly_total"]
    except OccupancyPricingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = calculate_occupancy_quote(
        base_nightly_rate=pricing["nightly_rates"][0]["rate"] if pricing.get("nightly_rates") else 0,
        nights=max(len(quoted_nights), 1),
        adults=adults,
        children_ages=child_ages,
        rule=rule,
    )
    return {
        **pricing,
        "nightly_rates": quoted_nights,
        "total_price": round(total, 2),
        "occupancy_pricing": {
            "pricing_version": summary["pricing_version"],
            "pricing_type": summary["pricing_type"],
            "children_ages": summary["children_ages"],
            "child_breakdown": summary["child_breakdown"],
            "adult_supplement_nightly": summary["adult_supplement_nightly"],
            "child_supplement_nightly": summary["child_supplement_nightly"],
        },
    }


async def _validated_agency_quote(*, tenant_id, agency_id, room, check_in, check_out,
                                  rate_plan_code, adults, children, child_ages, exclude_booking_id=None,
                                  allow_base_rate_fallback=False):
    if not rate_plan_code or len(child_ages) != children or any(age < 0 or age > 17 for age in child_ages):
        raise HTTPException(422, "Fiyat planı ve her çocuk için geçerli yaş bilgisi gerekli")
    if adults < 1 or children < 0 or int(room.get("capacity") or 2) < adults + children:
        raise HTTPException(409, "Oda kapasitesi misafir sayısı için yetersiz")
    pricing = await _marketplace_stay_price(
        tenant_id=tenant_id, agency_id=agency_id, room_type=room["room_type"],
        check_in=check_in, check_out=check_out, rate_plan_code=rate_plan_code,
        fallback_rate=float(room.get("base_price") or 0), exclude_booking_id=exclude_booking_id,
        allow_base_rate_fallback=allow_base_rate_fallback,
    )
    if not pricing["sellable"]:
        raise HTTPException(409, "Seçilen fiyat planı veya kontenjan bu tarihlerde satışa kapalı")
    pricing = await _marketplace_occupancy_price(
        tenant_id=tenant_id, room=room, pricing=pricing, adults=adults, child_ages=child_ages,
    )
    if pricing["total_price"] <= 0:
        raise HTTPException(409, "Geçerli satış fiyatı tanımlı değil")
    return pricing


async def _check_agency_credit(*, tenant_id, agency_id, contract, net_to_hotel,
                               booking_currency, exclude_booking_id=None):
    await assert_credit_capacity(
        db, tenant_id=tenant_id, agency_id=agency_id, contract=contract,
        booking_currency=booking_currency, new_net_exposure=net_to_hotel,
        exclude_booking_id=exclude_booking_id,
    )


def _contract_commission(contract: dict) -> float:
    """Return the hotel-approved commission; never silently fall back."""
    if contract.get("status") != "approved" or contract.get("commission_pct") is None:
        raise HTTPException(403, "Onaylı otel–acente sözleşmesi ve komisyon oranı gerekli")
    return float(contract["commission_pct"])


def _syroce_b2b_fee(total: float, source: str, agency_fee_pct: float | None = None) -> tuple[float, float]:
    """Return the marketplace service fee used in the hotel net calculation.

    Direct API integrations are billed at 1%; reservations created in the
    hosted extranet include the additional UI/operations service and are
    billed at 2%.  Keeping this calculation next to commission setup ensures
    the values exist before the PMS booking becomes durable.
    """
    fee_pct = float(agency_fee_pct) if agency_fee_pct is not None else (2.0 if source == "extranet_ui" else 1.0)
    if fee_pct < 0 or fee_pct > 100:
        raise ValueError("Platform hizmet bedeli 0 ile 100 arasında olmalıdır")
    return fee_pct, round(float(total) * fee_pct / 100, 2)


def _marketplace_financials(total: float, commission_pct: float, fee_pct: float) -> dict[str, float]:
    commission_amount = round(float(total) * float(commission_pct) / 100, 2)
    fee_amount = round(float(total) * float(fee_pct) / 100, 2)
    return {
        "commission_amount": commission_amount,
        "syroce_b2b_fee_amount": fee_amount,
        "net_to_hotel": round(float(total) - commission_amount, 2),
    }


def _reservation_room_snapshot(room: dict) -> dict:
    """Canonical room fields shared by PMS, ledger and API responses."""
    return {
        "room_type": room.get("room_type", ""),
        "room_number": room.get("room_number", ""),
    }


def _reservation_agency_snapshot(agency: dict) -> dict:
    """Canonical marketplace source fields shared by PMS and ledger records."""
    return {
        "marketplace_agency_id": agency["agency_id"],
        "marketplace_agency_name": agency["agency_name"],
        "agency_id": agency["agency_id"],
        "agency_name": agency["agency_name"],
        "channel": "marketplace",
        "source_channel": "marketplace",
        "origin": "syroce_marketplace",
    }


# ─── Pydantic Modelleri ───────────────────────────────────────────────────


class MarketplaceAgencyCreate(BaseModel):
    name: str
    contact_email: str = ""
    contact_phone: str = ""
    country: str = "TR"
    default_commission_pct: float = Field(default=12.0, ge=0, le=100)
    platform_fee_pct: float | None = Field(default=None, ge=0, le=100)
    # Keep direct API clients backward compatible; the admin UI always sends
    # an explicit choice and defaults to the safer portal-only mode.
    issue_api_key: bool = True
    api_key_label: str = Field(default="Ana entegrasyon", min_length=2, max_length=80)


class MarketplaceAgencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    default_commission_pct: float | None = Field(default=None, ge=0, le=100)
    platform_fee_pct: float | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class MarketplaceApiKeyRotate(BaseModel):
    label: str = Field(default="Ana entegrasyon", min_length=2, max_length=80)


class AgencySalesLockReconcile(BaseModel):
    owner: str = Field(..., min_length=8, max_length=100)
    resolution: str = Field(..., pattern="^(booking_committed|no_booking_committed)$")
    reason: str = Field(..., min_length=10, max_length=1000)
    writer_stopped_confirmed: bool = False


class MarketplaceListingCreate(BaseModel):
    hotel_name: str
    city: str
    country: str = "TR"
    address: str = ""
    description: str = ""
    photos: list[str] = []
    amenities: list[str] = []
    meal_plans: list[str] = []
    star_rating: int | None = Field(default=None, ge=1, le=5)
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    allowed_room_types: list[str] = []
    blocked_dates: list[str] = []  # YYYY-MM-DD


class MarketplaceListingUpdate(BaseModel):
    hotel_name: str | None = None
    city: str | None = None
    country: str | None = None
    address: str | None = None
    description: str | None = None
    photos: list[str] | None = None
    amenities: list[str] | None = None
    meal_plans: list[str] | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    allowed_room_types: list[str] | None = None
    blocked_dates: list[str] | None = None
    is_listed: bool | None = None


class MarketplaceSearchRequest(BaseModel):
    rate_plan_code: str | None = Field(default=None, min_length=1, max_length=160)
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    adults: int = Field(default=2, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    city: str | None = None
    country: str | None = None
    q: str | None = None
    amenities: list[str] = Field(default_factory=list, max_length=30)
    meal_plans: list[str] = Field(default_factory=list, max_length=10)
    min_star_rating: int | None = Field(default=None, ge=1, le=5)
    max_price: float | None = None
    limit: int = Field(default=50, le=200)

    @model_validator(mode="after")
    def validate_child_ages(self):
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("Çocuk yaşları 0-17 arasında olmalıdır")
        if len(self.child_ages) != self.children:
            raise ValueError("Her çocuk için yaş bilgisi girilmelidir")
        return self


def _filter_token(value: object) -> str:
    """Normalize marketplace facets without relying on display language/casing."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    token = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "havuz": "pool", "jakuzi": "jacuzzi", "plaj": "beach",
        "deniz_manzarasi": "sea_view", "deniz_manzaras": "sea_view",
        "oda_kahvalti": "bb", "bed_breakfast": "bb", "breakfast_included": "bb",
        "sadece_oda": "ro", "room_only": "ro",
        "yarim_pansiyon": "hb", "half_board": "hb",
        "tam_pansiyon": "fb", "full_board": "fb",
        "her_sey_dahil": "ai", "all_inclusive": "ai",
    }
    return aliases.get(token, token)


def _normalized_tokens(values: list[object] | None) -> set[str]:
    return {token for value in (values or []) if (token := _filter_token(value))}


class MarketplaceReservationCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    room_type: str = Field(..., min_length=1, max_length=160)
    rate_plan_code: str | None = Field(default=None, min_length=1, max_length=160)
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_name: str = Field(..., min_length=2, max_length=160)
    guest_email: EmailStr | None = None
    guest_phone: str = Field(default="", max_length=40)
    adults: int = Field(default=2, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    special_requests: str = Field(default="", max_length=1000)
    total_amount: float = Field(default=0, ge=0)
    external_reference: str = Field(default="", max_length=160)  # Acentenin kendi PNR/voucher kodu
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_child_ages(self):
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("Çocuk yaşları 0-17 arasında olmalıdır")
        if len(self.child_ages) != self.children:
            raise ValueError("Her çocuk için yaş bilgisi girilmelidir")
        return self


class CancellationProposalCreate(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)


class CancellationProposalDecision(BaseModel):
    accept: bool
    response_note: str = Field(default="", max_length=1000)


class VoucherEmailRequest(BaseModel):
    email: EmailStr


class ModificationProposalCreate(BaseModel):
    check_in: str
    check_out: str
    room_type: str = Field(..., min_length=1, max_length=160)
    rate_plan_code: str = Field(..., min_length=1, max_length=160)
    reason: str = Field(..., min_length=5, max_length=1000)

    @model_validator(mode="after")
    def validate_stay(self):
        ci, co = date.fromisoformat(self.check_in), date.fromisoformat(self.check_out)
        if ci.isoformat() != self.check_in or co.isoformat() != self.check_out or co <= ci:
            raise ValueError("Geçerli giriş ve çıkış tarihleri gerekli")
        return self


# ═══════════════════════════════════════════════════════════════════════
# SYSTEM ADMIN — Marketplace Agency Yönetimi
# ═══════════════════════════════════════════════════════════════════════


async def _sales_lock_evidence(sysdb, lock: dict) -> dict:
    """Return operator-safe evidence; never infer an abandoned writer by age."""
    key = lock.get("idempotency_key")
    proposal = None
    booking_query = {"tenant_id": lock["tenant_id"], "agency_id": lock["agency_id"]}
    if key:
        booking_query["agency_idempotency_key"] = key
    elif lock.get("reference_id"):
        # Modification locks keep the proposal id, not the reservation id.
        # Resolve it before looking for durable booking evidence.
        if lock.get("operation") == "marketplace_modification":
            proposal = await sysdb.marketplace_negotiations.find_one(
                {"id": lock["reference_id"], "tenant_id": lock["tenant_id"], "agency_id": lock["agency_id"]},
                {"_id": 0, "id": 1, "reservation_id": 1, "status": 1, "applied_snapshot": 1},
            )
            if not proposal:
                return {"booking": None, "idempotency": None, "proposal": None}
            booking_query["id"] = proposal.get("reservation_id")
        else:
            proposal = None
            booking_query["id"] = lock["reference_id"]
    else:
        return {"booking": None, "idempotency": None, "proposal": None}
    snapshot = (proposal or {}).get("applied_snapshot") or {}
    booking = await sysdb.bookings.find_one(
        booking_query,
        {"_id": 0, "id": 1, "confirmation_code": 1, "status": 1, "agency_completion.status": 1,
         **dict.fromkeys(snapshot, 1)},
    )
    modification_verified = False
    if proposal and proposal.get("status") == "accepted" and snapshot and booking:
        ledger = await sysdb.marketplace_bookings.find_one(
            {"id": booking["id"], "tenant_id": lock["tenant_id"], "agency_id": lock["agency_id"]},
            {"_id": 0, **dict.fromkeys(snapshot, 1)},
        )
        modification_verified = bool(ledger) and all(
            booking.get(field) == value and ledger.get(field) == value for field, value in snapshot.items()
        )
    if proposal and proposal.get("status") == "declined":
        modification_verified = True  # Rejection performs no reservation writes.
    idempotency = None
    if key:
        idempotency = await sysdb.idempotency_keys.find_one(
            {"idempotency_key": key}, {"_id": 0, "scope": 1, "status": 1, "created_at": 1, "expires_at": 1},
        )
    return {"booking": booking, "idempotency": idempotency, "proposal": proposal,
            "modification_verified": modification_verified}


@router.get("/admin/sales-locks")
async def admin_list_agency_sales_locks(_: bool = Depends(_require_system_admin)):
    """List manual-recovery-only admission fences with durable-write evidence."""
    sysdb = get_system_db()
    locks = await sysdb.agency_sale_mutexes.find({}, {"_id": 1, "owner": 1, "tenant_id": 1, "agency_id": 1,
                                                       "operation": 1, "idempotency_key": 1, "reference_id": 1,
                                                       "recovery_state": 1, "created_at": 1}).sort("created_at", 1).to_list(500)
    items = []
    for lock in locks:
        evidence = await _sales_lock_evidence(sysdb, lock)
        items.append({
            "lock_id": lock["_id"], "owner": lock.get("owner"), "tenant_id": lock.get("tenant_id"),
            "agency_id": lock.get("agency_id"), "operation": lock.get("operation", "unknown"),
            "reference_id": lock.get("reference_id"), "recovery_state": lock.get("recovery_state", "active"),
            "created_at": lock.get("created_at"), **evidence,
        })
    pending = await sysdb.agency_sales_lock_recoveries.find(
        {"status": "pending_release"}, {"_id": 0},
    ).to_list(500)
    # A completed deletion may have lost its response or final audit update.
    # Expose that receipt even when the original lock is already gone.
    for record in pending:
        if any(item["lock_id"] == record["lock_id"] and item["owner"] == record["lock_owner"] for item in items):
            continue
        items.append({"lock_id": record["lock_id"], "owner": record["lock_owner"],
                      "tenant_id": record["tenant_id"], "agency_id": record["agency_id"],
                      "operation": record.get("operation"), "recovery_state": "pending_release",
                      "booking": record.get("booking"), "proposal": record.get("proposal"),
                      "modification_verified": True, "receipt_only": True})
    return {"items": items, "total": len(items)}


@router.post("/admin/sales-locks/{lock_id}/reconcile")
async def admin_reconcile_agency_sales_lock(
    lock_id: str,
    data: AgencySalesLockReconcile,
    _: bool = Depends(_require_system_admin),
):
    """Release one lock only after evidence review and explicit writer-stop attestation."""
    if not data.writer_stopped_confirmed:
        raise HTTPException(422, "Kilidi açmadan önce özgün yazıcının durduğunu doğrulamalısınız")
    sysdb = get_system_db()
    lock = await sysdb.agency_sale_mutexes.find_one({"_id": lock_id, "owner": data.owner})
    if not lock:
        receipt = await sysdb.agency_sales_lock_recoveries.find_one(
            {"lock_id": lock_id, "lock_owner": data.owner, "status": {"$in": ["pending_release", "released"]}},
        )
        if receipt:
            # Never touch a replacement lock: only finish the original receipt.
            await sysdb.agency_sales_lock_recoveries.update_one(
                {"id": receipt["id"]}, {"$set": {"status": "released", "released_at": _now_iso()}},
            )
            return {"ok": True, "recovery_id": receipt["id"], "idempotent_replay": True}
        raise HTTPException(409, "Satış kilidi değişmiş veya zaten uzlaştırılmış; listeyi yenileyin")
    evidence = await _sales_lock_evidence(sysdb, lock)
    if lock.get("operation") == "marketplace_modification" and not evidence.get("modification_verified"):
        raise HTTPException(409, "Değişiklik tamamlandığı doğrulanamadı: teklif, PMS ve marketplace kaydı uzlaştırılmadan kilit kaldırılamaz.")
    has_booking = bool(evidence.get("booking"))
    processing = (evidence.get("idempotency") or {}).get("status") == "processing"
    if data.resolution == "booking_committed" and not has_booking:
        raise HTTPException(409, "Rezervasyon kaydı doğrulanamadı; 'rezervasyon oluşmadı' uzlaştırmasını kullanın")
    if data.resolution == "no_booking_committed" and has_booking:
        raise HTTPException(409, "Rezervasyon bulundu; 'rezervasyon oluştu' uzlaştırmasını kullanın")
    if processing:
        raise HTTPException(409, "İdempotency işlemi hâlâ işleniyor; önce özgün işlemi tamamlayın veya inceleyin")
    # Persist the operator's attestation before releasing the fence. This
    # preserves evidence even if a later storage operation fails.
    record = {
        "id": _uuid(), "lock_id": lock_id, "lock_owner": data.owner,
        "tenant_id": lock["tenant_id"], "agency_id": lock["agency_id"],
        "operation": lock.get("operation"), "resolution": data.resolution,
        "reason": data.reason.strip(), "writer_stopped_confirmed": True,
        "booking": evidence.get("booking"), "idempotency": evidence.get("idempotency"),
        "proposal": evidence.get("proposal"), "status": "pending_release",
        "reconciled_at": _now_iso(), "actor_type": "system_admin",
    }
    previous = await sysdb.agency_sales_lock_recoveries.find_one(
        {"lock_id": lock_id, "lock_owner": data.owner, "status": "pending_release"},
    )
    if previous:
        record = previous
    else:
        await sysdb.agency_sales_lock_recoveries.insert_one(record)
    deleted = await sysdb.agency_sale_mutexes.delete_one({"_id": lock_id, "owner": data.owner})
    if not deleted.deleted_count:
        if await sysdb.agency_sale_mutexes.find_one({"_id": lock_id, "owner": data.owner}):
            raise HTTPException(409, "Satış kilidi kaldırılamadı; denetim kaydı korundu, yeniden deneyin")
    await sysdb.agency_sales_lock_recoveries.update_one(
        {"id": record["id"]}, {"$set": {"status": "released", "released_at": _now_iso()}},
    )
    await _record_marketplace_audit(sysdb, agency_id=lock["agency_id"], action="agency_sales_lock_released", details={
        "lock_id": lock_id, "tenant_id": lock["tenant_id"], "operation": lock.get("operation"),
        "resolution": data.resolution, "recovery_id": record["id"],
    })
    return {"ok": True, "recovery_id": record["id"], "booking": evidence.get("booking")}


@router.post("/admin/agencies")
async def admin_create_agency(
    data: MarketplaceAgencyCreate,
    _: bool = Depends(_require_system_admin),
):
    """Yeni marketplace acentesi oluştur.

    API erişimi açıkça istenirse ilk anahtar yalnızca bu yanıtta gösterilir.
    Portal kullanan acenteler için gereksiz bir teknik sır üretilmez.
    """
    sysdb = get_system_db()

    agency_id = _uuid()
    agency_doc = {
        "id": agency_id,
        "name": data.name.strip(),
        "contact_email": data.contact_email.strip(),
        "contact_phone": data.contact_phone.strip(),
        "country": data.country,
        "default_commission_pct": data.default_commission_pct,
        "status": "active",
        "created_at": _now_iso(),
    }
    if data.platform_fee_pct is not None:
        agency_doc["platform_fee_pct"] = data.platform_fee_pct
    await sysdb.marketplace_agencies.insert_one(agency_doc)
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="agency_created",
        details={"api_access_requested": bool(data.issue_api_key)},
    )

    response = {
        "agency": {k: v for k, v in agency_doc.items() if k != "_id"},
        "api_key": None,
        "key_prefix": None,
        "warning": None,
    }
    if data.issue_api_key:
        raw_key, key_doc = await _create_marketplace_api_key(
            sysdb,
            agency_id,
            label=data.api_key_label,
        )
        response.update(
            {
                "api_key": raw_key,
                "key_prefix": key_doc["key_prefix"],
                "warning": "Bu API anahtarı yalnızca bir kez gösterilir. Güvenli bir parola kasasına kaydedin.",
            }
        )
        await _record_marketplace_audit(
            sysdb,
            agency_id=agency_id,
            action="api_key_created",
            details={"key_id": key_doc["id"], "key_prefix": key_doc["key_prefix"], "label": key_doc.get("label")},
        )
    return response


@router.get("/admin/integrations")
async def admin_incomplete_integrations(
    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
    _: bool = Depends(_require_system_admin),
):
    system = get_system_db()
    query = {"agency_completion.status": {"$in": ["pending", "processing", "retry", "waiting", "failed"]}}
    rows = await system.bookings.find(query, {
        "_id": 0, "id": 1, "tenant_id": 1, "agency_id": 1, "confirmation_code": 1,
        "agency_completion": 1,
    }).sort("agency_completion.available_at", 1).skip(offset).limit(limit).to_list(limit)
    for row in rows:
        state = row.pop("agency_completion")
        row["integration"] = {key: state.get(key) for key in
                              ("status", "done", "attempts", "last_error", "updated_at", "available_at")}
    return {"items": rows, "total": await system.bookings.count_documents(query)}


@router.post("/admin/integrations/{booking_id}/retry")
async def admin_retry_integration(booking_id: str, _: bool = Depends(_require_system_admin)):
    from core.agency_completion import stable_id
    system = get_system_db()
    row = await system.bookings.find_one({"id": booking_id, "agency_completion.status": {
        "$in": ["failed", "retry", "waiting"]}}, {"_id": 0, "id": 1, "tenant_id": 1})
    if not row:
        raise HTTPException(409, "İşlem çalışıyor, tamamlanmış veya yeniden denemeye uygun değil")
    # Only failed delivery is requeued; never steal an active outbox lease.
    await system.outbox_events.update_one({"tenant_id": row["tenant_id"],
        "idempotency_key": stable_id(booking_id, "inventory"), "status": "failed"}, {"$set": {
            "status": "pending", "attempt_count": 0, "available_at": _now_iso(), "last_error": None}})
    result = await system.bookings.update_one({"id": booking_id, "tenant_id": row["tenant_id"],
        "agency_completion.status": {"$in": ["failed", "retry", "waiting"]}}, {"$set": {
            "agency_completion.status": "pending", "agency_completion.attempts": 0,
            "agency_completion.available_at": datetime.now(UTC), "agency_completion.last_error": None}})
    if not result.matched_count:
        raise HTTPException(409, "İşlem başka bir çalışan tarafından alındı; yenileyin")
    return {"ok": True, "booking_id": booking_id, "integration_status": "pending"}


@router.get("/admin/agencies")
async def admin_list_agencies(_: bool = Depends(_require_system_admin)):
    sysdb = get_system_db()
    # These snapshots are independent. Awaiting them one by one multiplied
    # database latency and made every Hotels <-> Agencies switch feel blocked.
    docs, contract_rows, booking_rows, key_rows, portal_user_rows = await asyncio.gather(
        sysdb.marketplace_agencies.find({}, {"_id": 0}).sort("created_at", -1).to_list(500),
        sysdb.agency_contracts.aggregate([
            {"$match": {"status": "approved"}},
            {"$group": {"_id": "$agency_id", "connected_hotels": {"$addToSet": "$tenant_id"}}},
        ]).to_list(500),
        sysdb.marketplace_bookings.aggregate([
            {"$match": {"status": {"$ne": "cancelled"}}},
            {"$group": {"_id": {"agency_id": "$agency_id", "currency": {"$toUpper": {"$ifNull": ["$currency", "UNKNOWN"]}}}, "booking_count": {"$sum": 1}, "gross_volume": {"$sum": "$total_amount"}, "platform_revenue": {"$sum": "$syroce_b2b_fee_amount"}}},
        ]).to_list(None),
        sysdb.marketplace_api_keys.find(
            {"is_active": True},
            {
                "_id": 0,
                "agency_id": 1,
                "id": 1,
                "label": 1,
                "key_prefix": 1,
                "created_at": 1,
                "last_used_at": 1,
                "last_used_ip": 1,
                "usage_count": 1,
            },
        ).to_list(1000),
        sysdb.users.find(
            {"agency_id": {"$exists": True}, "is_active": {"$ne": False}},
            {"_id": 0, "agency_id": 1, "last_login": 1},
        ).to_list(5000),
    )
    contract_stats = {row["_id"]: len(row.get("connected_hotels") or []) for row in contract_rows}
    from core.agency_reporting import currency_code
    booking_stats = {}
    for row in booking_rows:
        booking_stats.setdefault(row['_id']['agency_id'], []).append({
            'currency': currency_code(row['_id'].get('currency')), 'booking_count': row['booking_count'],
            'gross_volume': round(float(row.get('gross_volume') or 0), 2),
            'platform_revenue': round(float(row.get('platform_revenue') or 0), 2),
        })
    active_keys: dict[str, dict] = {}
    for key in sorted(key_rows, key=lambda item: item.get("created_at") or "", reverse=True):
        active_keys.setdefault(key.get("agency_id"), key)
    portal_users: dict[str, dict] = {}
    for user in portal_user_rows:
        agency_users = portal_users.setdefault(user.get("agency_id"), {"count": 0, "last_login": None})
        agency_users["count"] += 1
        if user.get("last_login") and (not agency_users["last_login"] or user["last_login"] > agency_users["last_login"]):
            agency_users["last_login"] = user["last_login"]
    for agency in docs:
        agency_id = agency.get("id")
        stats = booking_stats.get(agency_id, [])
        agency["connected_hotels"] = contract_stats.get(agency_id, 0)
        agency["booking_count"] = sum(row['booking_count'] for row in stats)
        agency["totals_by_currency"] = stats
        agency["gross_volume"] = stats[0]['gross_volume'] if len(stats) == 1 else None
        agency["platform_revenue"] = stats[0]['platform_revenue'] if len(stats) == 1 else None
        agency["currency"] = stats[0]['currency'] if len(stats) == 1 else None
        key = active_keys.get(agency_id)
        agency["api_access"] = {
            "active": bool(key),
            "key_id": key.get("id") if key else None,
            "label": key.get("label") if key else None,
            "key_prefix": key.get("key_prefix") if key else None,
            "created_at": key.get("created_at") if key else None,
            "last_used_at": key.get("last_used_at") if key else None,
            "last_used_ip": key.get("last_used_ip") if key else None,
            "usage_count": int(key.get("usage_count", 0) or 0) if key else 0,
        }
        agency["portal_access"] = portal_users.get(agency_id, {"count": 0, "last_login": None})
    return {"agencies": docs, "total": len(docs)}


@router.patch("/admin/agencies/{agency_id}")
async def admin_update_agency(
    agency_id: str,
    data: MarketplaceAgencyUpdate,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    updates = data.model_dump(exclude_none=True)
    if "name" in updates:
        updates["name"] = updates["name"].strip()
    if "contact_email" in updates:
        updates["contact_email"] = updates["contact_email"].strip().lower()
    if "contact_phone" in updates:
        updates["contact_phone"] = updates["contact_phone"].strip()
    if "country" in updates:
        updates["country"] = updates["country"].upper()
    if not updates:
        raise HTTPException(400, "Güncellenecek alan bulunamadı")
    updates["updated_at"] = _now_iso()
    result = await sysdb.marketplace_agencies.update_one({"id": agency_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Acente bulunamadı")
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="agency_updated",
        details={"changed_fields": sorted(key for key in updates if key not in {"updated_at"})},
    )
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id}, {"_id": 0})
    return {"ok": True, "agency": agency}


@router.post("/admin/agencies/{agency_id}/portal-context")
async def admin_enter_agency_portal(
    agency_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Open an audited, short-lived agency portal session as superadmin.

    No agency password is read, returned or replaced. The session is a scoped
    superadmin preview identity and expires after 15 minutes.
    """
    if not _is_super_admin(current_user) or getattr(current_user, "is_impersonating", False):
        raise HTTPException(403, "Acente hesabını yalnızca ana süperadmin oturumu görüntüleyebilir")

    sysdb = get_system_db()
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id, "status": "active"}, {"_id": 0})
    if not agency:
        raise HTTPException(404, "Aktif acente bulunamadı")

    actor_user_id = current_user.id
    token, expires_at = _create_admin_agency_context_token(
        actor_user_id=actor_user_id,
        agency_id=agency_id,
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="admin_agency_context_enter",
        details={
            "actor_user_id": actor_user_id,
            "context_identity": "scoped_superadmin_preview",
            "expires_at": expires_at,
            "source_ip": request.client.host if request.client else None,
        },
    )
    return {
        "token": token,
        "expires_at": expires_at,
        "portal_path": "/agency-portal",
        "agency": {"id": agency_id, "name": agency.get("name", "")},
    }


@router.delete("/admin/agencies/{agency_id}")
async def admin_disable_agency(
    agency_id: str,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    res = await sysdb.marketplace_agencies.update_one({"id": agency_id}, {"$set": {"status": "disabled", "disabled_at": _now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Acente bulunamadı")
    await sysdb.marketplace_api_keys.update_many(
        {"agency_id": agency_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso()}},
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="agency_disabled",
        details={"reason": "system_admin"},
    )
    return {"ok": True, "message": "Acente devre dışı bırakıldı, tüm API key'ler iptal edildi"}


@router.post("/admin/agencies/{agency_id}/api-keys/regenerate")
async def admin_regenerate_key(
    agency_id: str,
    data: MarketplaceApiKeyRotate | None = None,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id, "status": "active"}, {"_id": 0})
    if not agency:
        raise HTTPException(409, "Yalnızca aktif bir acente için API anahtarı oluşturulabilir")

    # Availability-safe rotation: persist the new credential first. If that
    # write fails the currently active integration remains usable. Only after
    # success are the older credentials revoked.
    raw_key, key_doc = await _create_marketplace_api_key(
        sysdb,
        agency_id,
        label=(data.label if data else "Ana entegrasyon"),
    )
    revoked = await sysdb.marketplace_api_keys.update_many(
        {"agency_id": agency_id, "id": {"$ne": key_doc["id"]}, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso()}},
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="api_key_rotated",
        details={
            "key_id": key_doc["id"],
            "key_prefix": key_doc["key_prefix"],
            "label": key_doc.get("label"),
            "revoked_count": int(revoked.modified_count or 0),
        },
    )
    return {
        "api_key": raw_key,
        "key_prefix": key_doc["key_prefix"],
        "warning": "Bu API anahtarı yalnızca bir kez gösterilir. Eski anahtar artık geçersizdir.",
    }


@router.delete("/admin/agencies/{agency_id}/api-keys")
async def admin_revoke_api_keys(
    agency_id: str,
    _: bool = Depends(_require_system_admin),
):
    """Acentenin teknik API erişimini portal erişimini etkilemeden kapat."""
    sysdb = get_system_db()
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id}, {"_id": 0, "id": 1})
    if not agency:
        raise HTTPException(404, "Acente bulunamadı")
    result = await sysdb.marketplace_api_keys.update_many(
        {"agency_id": agency_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso()}},
    )
    await _record_marketplace_audit(
        sysdb,
        agency_id=agency_id,
        action="api_key_revoked",
        details={"revoked_count": int(result.modified_count or 0)},
    )
    return {
        "ok": True,
        "revoked_count": int(result.modified_count or 0),
        "message": "API erişimi kapatıldı. Acente portalı kullanıcıları etkilenmedi.",
    }


# ═══════════════════════════════════════════════════════════════════════
# HOTEL ADMIN — Marketplace Listing (Opt-in)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/listings/me")
async def listing_opt_in(
    data: MarketplaceListingCreate,
    current_user: User = Depends(get_current_user),
):
    """Bu oteli marketplace'e listele (opt-in)."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()

    existing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if existing and existing.get("is_listed"):
        raise HTTPException(409, "Otel zaten marketplace'te listelenmiş, güncellemek için PUT kullanın")

    doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "hotel_name": data.hotel_name.strip(),
        "city": data.city.strip().title(),
        "country": data.country,
        "address": data.address.strip(),
        "description": data.description.strip(),
        "photos": data.photos or [],
        "amenities": data.amenities or [],
        "meal_plans": data.meal_plans or [],
        "star_rating": data.star_rating,
        "commission_pct": data.commission_pct,
        "allowed_room_types": data.allowed_room_types or [],
        "blocked_dates": data.blocked_dates or [],
        "is_listed": True,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "created_by": current_user.id,
    }
    if existing:
        await sysdb.marketplace_listings.update_one({"tenant_id": tenant_id}, {"$set": {**{k: v for k, v in doc.items() if k != "id"}, "id": existing["id"]}})
        doc["id"] = existing["id"]
    else:
        await sysdb.marketplace_listings.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "listing": doc}


@router.get("/listings/me")
async def listing_get_mine(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not listing:
        return {"is_listed": False, "listing": None}
    return {"is_listed": listing.get("is_listed", False), "listing": listing}


@router.put("/listings/me")
async def listing_update_mine(
    data: MarketplaceListingUpdate,
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(400, "Güncellenecek alan yok")
    update["updated_at"] = _now_iso()
    res = await sysdb.marketplace_listings.update_one({"tenant_id": tenant_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Listing bulunamadı, önce opt-in yapın")
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {"ok": True, "listing": listing}


@router.delete("/listings/me")
async def listing_opt_out(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    res = await sysdb.marketplace_listings.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"is_listed": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Listing yok")
    return {"ok": True, "message": "Otel marketplace'ten çıkarıldı"}


# ═══════════════════════════════════════════════════════════════════════
# AGENCY (X-API-Key) — Hotel Discovery & Search
# ═══════════════════════════════════════════════════════════════════════


@router.get("/hotels")
async def agency_list_hotels(
    city: str | None = Query(None),
    country: str | None = Query(None),
    q: str | None = Query(None, description="Ad veya açıklamada ara"),
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_marketplace_agency),
):
    """Marketplace'te listelenen ve aktif sözleşmesi bulunan otelleri keşfet."""
    from routers.agency_contracts import list_partner_tenant_ids

    partner_tenant_ids = await list_partner_tenant_ids(agency["agency_id"])
    if not partner_tenant_ids:
        return {"hotels": [], "total": 0, "message": "Henüz onaylı sözleşmeniz olan otel yok. Önce otele teklif gönderin."}

    sysdb = get_system_db()
    query: dict = {"is_listed": True, "tenant_id": {"$in": partner_tenant_ids}}
    from security.query_safety import safe_search_term

    if city and (_c := safe_search_term(city)):
        query["city"] = {"$regex": f"^{_c}$", "$options": "i"}
    if country:
        query["country"] = country.upper()
    if q and (_s := safe_search_term(q)):
        query["$or"] = [
            {"hotel_name": {"$regex": _s, "$options": "i"}},
            {"description": {"$regex": _s, "$options": "i"}},
        ]

    docs = (
        await sysdb.marketplace_listings.find(
            query,
            {"_id": 0, "blocked_dates": 0, "created_by": 0},
        )
        .limit(limit)
        .to_list(limit)
    )
    return {"hotels": docs, "total": len(docs)}


@router.get("/hotels/{tenant_id}")
async def agency_get_hotel(
    tenant_id: str,
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract

    if not await has_active_contract(agency["agency_id"], tenant_id):
        raise HTTPException(403, "Bu otelle aktif sözleşmeniz yok")
    listing = await _get_listing_or_404(tenant_id)

    with tenant_context(tenant_id):
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)
        content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if content:
        listing = {
            **listing,
            "hotel_name": content.get("hotel_name") or listing.get("hotel_name"),
            "description": content.get("description") or listing.get("description", ""),
            "address": content.get("address") or listing.get("address", ""),
            "phone": content.get("phone") or listing.get("phone", ""),
            "email": content.get("email") or listing.get("email", ""),
            "photos": content.get("images") or listing.get("photos", []),
            "amenities": content.get("amenities") or listing.get("amenities", []),
            "services": content.get("services") or listing.get("services", []),
            "content_version": content.get("content_version", listing.get("content_version")),
        }
    editorial_room_types = {
        item.get("room_type"): item for item in (content or {}).get("room_types", [])
        if item.get("room_type")
    }
    room_types = {}
    for r in rooms:
        if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
            continue
        rt = r.get("room_type", "Standard")
        if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
            continue
        if rt not in room_types:
            editorial = editorial_room_types.get(rt, {})
            room_types[rt] = {
                "room_type": rt,
                "name": editorial.get("name") or rt,
                "description": editorial.get("description", ""),
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "images": editorial.get("images", []),
                "amenities": editorial.get("amenities") or r.get("amenities", []),
                "bed_type": r.get("bed_type", ""),
                "total_rooms": 0,
            }
        room_types[rt]["total_rooms"] += 1

    return {"listing": listing, "room_types": list(room_types.values())}


@router.post("/search")
async def agency_search(
    req: MarketplaceSearchRequest,
    agency: dict = Depends(get_marketplace_agency),
):
    """Çoklu otel müsaitlik araması.

    Şehir/ülke/sorgu filtreleriyle eşleşen tüm listed otellerde tarih aralığı
    için müsait oda tiplerini döndürür. Engelli tarih kuralları uygulanır.
    """
    try:
        ci = datetime.fromisoformat(req.check_in + "T00:00:00+00:00")
        co = datetime.fromisoformat(req.check_out + "T00:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih (YYYY-MM-DD)")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    from routers.agency_contracts import list_active_contracts

    last_night = _last_occupied_date(req.check_in, req.check_out)
    active_contracts = await list_active_contracts(
        agency["agency_id"], on_date=req.check_in, through_date=last_night
    )
    partner_tenant_ids = list(active_contracts)
    if not partner_tenant_ids:
        return {"check_in": req.check_in, "check_out": req.check_out, "results": [], "total_hotels": 0, "message": "Henüz onaylı sözleşmeniz olan otel yok."}

    sysdb = get_system_db()
    list_query: dict = {"is_listed": True, "tenant_id": {"$in": partner_tenant_ids}}
    from security.query_safety import safe_search_term

    if req.city and (_c := safe_search_term(req.city)):
        list_query["city"] = {"$regex": f"^{_c}$", "$options": "i"}
    if req.country:
        list_query["country"] = req.country.upper()
    if req.q and (_s := safe_search_term(req.q)):
        list_query["$or"] = [
            {"hotel_name": {"$regex": _s, "$options": "i"}},
            {"description": {"$regex": _s, "$options": "i"}},
        ]
    if req.min_star_rating:
        list_query["star_rating"] = {"$gte": req.min_star_rating}

    listings = await sysdb.marketplace_listings.find(list_query, {"_id": 0}).limit(req.limit).to_list(req.limit)
    tenant_ids = [item["tenant_id"] for item in listings]
    content_docs = await sysdb.hotel_content.find(
        {"tenant_id": {"$in": tenant_ids}}, {"_id": 0}
    ).to_list(len(tenant_ids) or 1)
    content_by_tenant = {item["tenant_id"]: item for item in content_docs}

    capacity_needed = max(1, req.adults + req.children)
    results: list[dict] = []

    for listing in listings:
        tenant_id = listing["tenant_id"]
        content = content_by_tenant.get(tenant_id) or {}
        listing = {
            **listing,
            "hotel_name": content.get("hotel_name") or listing.get("hotel_name"),
            "description": content.get("description") or listing.get("description", ""),
            "photos": content.get("images") or listing.get("photos", []),
            "amenities": content.get("amenities") or listing.get("amenities", []),
            "meal_plans": content.get("meal_plans") or listing.get("meal_plans", []),
            "star_rating": content.get("star_rating") or listing.get("star_rating"),
            "content_version": content.get("content_version", listing.get("content_version")),
        }
        editorial_room_types = {
            item.get("room_type"): item for item in content.get("room_types", [])
            if item.get("room_type")
        }
        # Tarih engeli kontrolü
        if any(d in listing.get("blocked_dates", []) for d in _date_range(req.check_in, req.check_out)):
            continue

        with tenant_context(tenant_id):
            rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)

            requested_amenities = _normalized_tokens(req.amenities)
            listing_amenities = _normalized_tokens(listing.get("amenities"))
            requested_meals = _normalized_tokens(req.meal_plans)
            known_meals = {"ro", "bb", "hb", "fb", "ai"}
            room_amenities = set().union(*(
                _normalized_tokens(room.get("amenities")) for room in rooms
            )) if rooms else set()
            room_meals = set()
            for room in rooms:
                room_meals |= _normalized_tokens([room.get("meal_plan"), room.get("board_type")])
                room_meals |= _normalized_tokens(room.get("amenities")) & known_meals
            if not requested_amenities.issubset(listing_amenities | room_amenities):
                continue
            # Board filtering is applied to the selected rate product below,
            # not to hotel-level amenities (a hotel may sell both RO and BB).

            room_types: dict[str, dict] = {}
            for r in rooms:
                if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
                    continue
                rt = r.get("room_type", "Standard")
                if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                    continue
                if r.get("capacity", 2) < capacity_needed:
                    continue
                # Hotel-level features (pool, beach, etc.) apply to every room;
                # room-level features (jacuzzi, sea view, etc.) must be present on
                # the selected room type when not declared by the hotel listing.
                required_room_amenities = requested_amenities - listing_amenities
                if not required_room_amenities.issubset(_normalized_tokens(r.get("amenities"))):
                    continue
                current_room_meals = _normalized_tokens([r.get("meal_plan"), r.get("board_type")])
                current_room_meals |= _normalized_tokens(r.get("amenities")) & known_meals
                rt_data = room_types.setdefault(
                    rt,
                    {
                        "room_type": rt,
                        "name": editorial_room_types.get(rt, {}).get("name") or rt,
                        "description": editorial_room_types.get(rt, {}).get("description", ""),
                        "images": editorial_room_types.get(rt, {}).get("images", []),
                        "capacity": r.get("capacity", 2),
                        "base_price": r.get("base_price", 0),
                        "total_rooms": 0,
                        "available_rooms": 0,
                        "amenities": r.get("amenities", []),
                        "meal_plan": r.get("meal_plan") or r.get("board_type") or "",
                        "_room_ids": [],
                    },
                )
                rt_data["total_rooms"] += 1
                rt_data["_room_ids"].append(r.get("id"))

            # One offer per room type AND rate plan. Never overwrite by date alone.
            products = {}
            for rt_data in room_types.values():
                for plan in await _agency_rate_plans(
                    tenant_id, agency["agency_id"], rt_data["room_type"], req.check_in, req.check_out,
                    allow_base_rate_fallback=bool(active_contracts[tenant_id].get("allow_base_rate_fallback")),
                ):
                    if req.rate_plan_code and plan != req.rate_plan_code:
                        continue
                    products[(rt_data["room_type"], plan)] = {**rt_data, "rate_plan_code": plan}
            room_types = products
            for rt_data in room_types.values():
                booked = await db.bookings.count_documents(
                    {
                        "tenant_id": tenant_id,
                        "room_id": {"$in": rt_data["_room_ids"]},
                        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                        # Half-open hotel-night overlap. A same-day departure
                        # must not consume the arriving guest's room-night.
                        **stay_overlap_filter(req.check_in, req.check_out),
                    }
                )
                rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
                pricing = await _marketplace_stay_price(
                    tenant_id=tenant_id,
                    agency_id=agency["agency_id"],
                    room_type=rt_data["room_type"],
                    check_in=req.check_in,
                    check_out=req.check_out,
                    fallback_rate=float(rt_data["base_price"] or 0),
                    rate_plan_code=rt_data["rate_plan_code"],
                    allow_base_rate_fallback=bool(active_contracts[tenant_id].get("allow_base_rate_fallback")),
                )
                pricing = await _marketplace_occupancy_price(
                    tenant_id=tenant_id,
                    room=rt_data,
                    pricing=pricing,
                    adults=req.adults,
                    child_ages=req.child_ages,
                )
                if pricing.get("shared_availability") is not None:
                    rt_data["available_rooms"] = min(
                        rt_data["available_rooms"], pricing["shared_availability"]
                    )
                rt_data["pricing"] = pricing
                del rt_data["_room_ids"]

        # Sadece müsait oda tipleri olan otelleri ekle
        nights = (co - ci).days
        commission_pct = _contract_commission(active_contracts[tenant_id])
        available = []
        for rt_data in room_types.values():
            pricing = rt_data.pop("pricing")
            if rt_data["available_rooms"] <= 0 or not pricing["sellable"]:
                continue
            product = _rate_product_snapshot(rt_data["rate_plan_code"], rt_data, active_contracts[tenant_id], pricing)
            if requested_meals and _filter_token(product["meal_plan"]) not in requested_meals:
                continue
            total_price = pricing["total_price"]
            if req.max_price and total_price > req.max_price:
                continue
            available.append(
                {
                    **rt_data,
                    **product,
                    "nights": nights,
                    "total_price": total_price,
                    "nightly_rates": pricing["nightly_rates"],
                    "currency": listing.get("currency", "TRY"),
                    "commission_pct": commission_pct,
                    "agency_payable": round(total_price * (1 - commission_pct / 100), 2),
                }
            )

        if available:
            results.append(
                {
                    "tenant_id": tenant_id,
                    "hotel_name": listing.get("hotel_name"),
                    "city": listing.get("city"),
                    "country": listing.get("country"),
                    "star_rating": listing.get("star_rating"),
                    "photos": listing.get("photos", [])[:3],
                    "description": listing.get("description", ""),
                    "amenities": listing.get("amenities", []),
                    "meal_plans": listing.get("meal_plans", []),
                    "currency": listing.get("currency", "TRY"),
                    "available_room_types": available,
                }
            )

    return {
        "check_in": req.check_in,
        "check_out": req.check_out,
        "results": results,
        "total_hotels": len(results),
    }


@router.get("/hotels/{tenant_id}/availability")
async def agency_hotel_availability(
    tenant_id: str,
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    adults: int = Query(2, ge=1, le=20),
    child_ages: list[int] = Query(default_factory=list, description="Her çocuk için yaş (0-17)"),
    rate_plan_code: str | None = Query(None, min_length=1, max_length=160),
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract

    if any(age < 0 or age > 17 for age in child_ages):
        raise HTTPException(422, "Çocuk yaşları 0-17 arasında olmalıdır")
    last_night = _last_occupied_date(check_in, check_out)
    contract = await has_active_contract(
        agency["agency_id"], tenant_id, on_date=check_in, through_date=last_night
    )
    if not contract:
        raise HTTPException(403, "Bu otelle bu tarih için aktif sözleşmeniz yok")
    listing = await _get_listing_or_404(tenant_id)
    if any(d in listing.get("blocked_dates", []) for d in _date_range(check_in, check_out)):
        return {"check_in": check_in, "check_out": check_out, "room_types": [], "blocked": True}

    try:
        ci = datetime.fromisoformat(check_in + "T00:00:00+00:00")
        co = datetime.fromisoformat(check_out + "T00:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    with tenant_context(tenant_id):
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(1000)
        room_types: dict[str, dict] = {}
        for r in rooms:
            if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
                continue
            rt = r.get("room_type", "Standard")
            if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                continue
            rt_data = room_types.setdefault(
                rt,
                {
                    "room_type": rt,
                    "capacity": r.get("capacity", 2),
                    "base_price": r.get("base_price", 0),
                    "amenities": r.get("amenities", []),
                    "total_rooms": 0,
                    "available_rooms": 0,
                    "_room_ids": [],
                },
            )
            rt_data["total_rooms"] += 1
            rt_data["_room_ids"].append(r.get("id"))

        nights = (co - ci).days
        commission_pct = _contract_commission(contract)
        for rt_data in room_types.values():
            booked = await db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "room_id": {"$in": rt_data["_room_ids"]},
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    **stay_overlap_filter(check_in, check_out),
                }
            )
            rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
            pricing = await _marketplace_stay_price(
                tenant_id=tenant_id,
                agency_id=agency["agency_id"],
                room_type=rt_data["room_type"],
                check_in=check_in,
                check_out=check_out,
                fallback_rate=float(rt_data["base_price"] or 0),
                rate_plan_code=rate_plan_code,
                allow_base_rate_fallback=bool(contract.get("allow_base_rate_fallback")),
            )
            if pricing["sellable"]:
                pricing = await _marketplace_occupancy_price(
                    tenant_id=tenant_id,
                    room=rt_data,
                    pricing=pricing,
                    adults=adults,
                    child_ages=child_ages,
                )
            if pricing.get("shared_availability") is not None:
                rt_data["available_rooms"] = min(
                    rt_data["available_rooms"], pricing["shared_availability"]
                )
            rt_data["nights"] = nights
            rt_data["total_price"] = pricing["total_price"]
            rt_data["nightly_rates"] = pricing["nightly_rates"]
            rt_data["occupancy_pricing"] = pricing.get("occupancy_pricing")
            rt_data["rate_plan_code"] = pricing.get("rate_plan_code")
            if not pricing["sellable"]:
                rt_data["available_rooms"] = 0
                rt_data["unavailable_reason"] = pricing.get("reason")
            rt_data["commission_pct"] = commission_pct
            rt_data["agency_payable"] = round(rt_data["total_price"] * (1 - commission_pct / 100), 2)
            del rt_data["_room_ids"]

    return {
        "check_in": check_in,
        "check_out": check_out,
        "hotel_name": listing.get("hotel_name"),
        "currency": listing.get("currency", "TRY"),
        "room_types": list(room_types.values()),
    }


@router.get("/hotels/{tenant_id}/rates")
async def agency_hotel_rates(
    tenant_id: str,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    room_type: str | None = Query(None),
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract

    if not await has_active_contract(
        agency["agency_id"], tenant_id, on_date=start_date, through_date=end_date
    ):
        raise HTTPException(403, "Bu otelle aktif sözleşmeniz yok")
    await _get_listing_or_404(tenant_id)
    base_query = {
        "tenant_id": tenant_id,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if room_type:
        base_query["room_type_code"] = room_type

    with tenant_context(tenant_id):
        rates = await db.agency_rate_calendar.find(
            {**base_query, "agency_id": agency["agency_id"]},
            {"_id": 0, "tenant_id": 0, "agency_id": 0},
        ).sort("date", 1).to_list(5000)
        source = "agency_rates"
        if not rates:
            source = "hotel_rates"
            rates = await db.hr_rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
        if not rates:
            rates = await db.rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
    return {"start_date": start_date, "end_date": end_date, "source": source, "rates": rates}


# ═══════════════════════════════════════════════════════════════════════
# AGENCY — Reservation Lifecycle (Cross-tenant)
# ═══════════════════════════════════════════════════════════════════════


async def agency_create_reservation(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_agency),
):
    """Listed otele cross-tenant rezervasyon oluştur. Mevcut bookings koleksiyonuna düşer."""
    from routers.agency_contracts import has_active_contract

    sysdb = get_system_db()
    if not data.rate_plan_code:
        raise HTTPException(422, "Arama sonucundaki rate_plan_code rezervasyonda zorunludur")
    if data.idempotency_key:
        existing = await sysdb.marketplace_bookings.find_one(
            {
                "agency_id": agency["agency_id"],
                "idempotency_key": data.idempotency_key,
            },
            {"_id": 0},
        )
        if existing:
            if existing.get("tenant_id") != data.tenant_id:
                raise HTTPException(409, "Bu işlem anahtarı farklı bir tesis rezervasyonunda kullanılmış")
            return {"ok": True, "reservation": existing, "idempotent_replay": True}

    last_night = _last_occupied_date(data.check_in, data.check_out)
    contract = await has_active_contract(
        agency["agency_id"],
        data.tenant_id,
        on_date=data.check_in,
        through_date=last_night,
    )
    if not contract:
        raise HTTPException(403, "Bu otelle bu tarih için aktif sözleşmeniz yok. Önce sözleşme teklifi gönderip otelin onayını bekleyin.")

    listing = await _get_listing_or_404(data.tenant_id)

    if any(d in listing.get("blocked_dates", []) for d in _date_range(data.check_in, data.check_out)):
        raise HTTPException(409, "Bu tarih aralığı otel tarafından kapatılmış")

    # Sözleşmedeki oda tipi kısıtı (varsa) listing kısıtının üzerine biner
    contract_room_types = contract.get("allowed_room_types") or []
    if contract_room_types and data.room_type not in contract_room_types:
        raise HTTPException(403, f"Bu oda tipi sözleşmenizde tanımlı değil: {contract_room_types}")
    if listing.get("allowed_room_types") and data.room_type not in listing["allowed_room_types"]:
        raise HTTPException(403, "Bu oda tipi marketplace satışına açık değil")

    try:
        ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
        co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    # Room selection is followed by create_booking_atomic below; its room-night
    # lock is the authoritative race-safety guard under concurrent requests.
    with tenant_context(data.tenant_id):
        rooms = await db.rooms.find(
            {
                "tenant_id": data.tenant_id,
                "room_type": data.room_type,
                "is_active": {"$ne": False},
                "status": {"$nin": ["maintenance", "out_of_order", "blocked"]},
            },
            {"_id": 0},
        ).to_list(500)
        rooms = [room for room in rooms if int(room.get("capacity") or 2) >= data.adults + data.children]
        if not rooms:
            raise HTTPException(404, "Uygun kapasitede, satışa açık oda tipi bulunamadı")

        available_room = None
        for room in rooms:
            conflict = await db.bookings.count_documents(
                {
                    "tenant_id": data.tenant_id,
                    "room_id": room["id"],
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    **stay_overlap_filter(data.check_in, data.check_out),
                }
            )
            if conflict == 0:
                available_room = room
                break

        if not available_room:
            raise HTTPException(409, "Seçilen tarihler için müsait oda yok")

        # Komisyon: sözleşmede otelin onayladığı oran (override edilmiş olabilir) kullanılır
        commission_pct = _contract_commission(contract)
        # Retain the explicit calendar-night/base calculation as a safe
        # fallback and as executable documentation of checkout exclusivity.
        nights = (co.date() - ci.date()).days
        server_total = float(available_room.get("base_price", 0)) * max(nights, 1)
        pricing = await _validated_agency_quote(
            tenant_id=data.tenant_id,
            agency_id=agency["agency_id"],
            room=available_room,
            check_in=data.check_in,
            check_out=data.check_out,
            rate_plan_code=data.rate_plan_code,
            adults=data.adults,
            children=data.children,
            child_ages=data.child_ages,
            allow_base_rate_fallback=bool(contract.get("allow_base_rate_fallback")),
        )
        # Server-side "ground truth" price. Search and booking use this exact helper.
        server_total: float = pricing["total_price"]
        if data.total_amount and data.total_amount > 0:
            if abs(data.total_amount - server_total) > PRICE_TOLERANCE:
                raise HTTPException(
                    422,
                    f"Fiyat uyuşmazlığı: gönderilen {data.total_amount}, beklenen {server_total} (tolerans ±{PRICE_TOLERANCE}). Lütfen güncel fiyat için /search çağrısını tekrarlayın.",
                )
        total = server_total
        commission_amount = round(total * commission_pct / 100, 2)
        syroce_b2b_fee_pct, syroce_b2b_fee_amount = _syroce_b2b_fee(
            total,
            agency.get("source", "syroce_agency_app"),
            agency.get("platform_fee_pct"),
        )
        # The platform fee is the agency's liability to Syroce; it must not
        # reduce the hotel's contracted payout a second time.
        net_to_hotel = round(total - commission_amount, 2)
        await _check_agency_credit(
            tenant_id=data.tenant_id, agency_id=agency["agency_id"], contract=contract,
            net_to_hotel=net_to_hotel, booking_currency=listing.get("currency", "TRY"),
        )

        guest_id = _uuid()
        from security.guest_write import encrypt_guest_insert

        await db.guests.insert_one(
            encrypt_guest_insert(
                {
                    "id": guest_id,
                    "tenant_id": data.tenant_id,
                    "name": data.guest_name.strip(),
                    "email": str(data.guest_email or "").strip().lower() or f"agency-{guest_id[:8]}@placeholder.local",
                    "phone": data.guest_phone.strip(),
                    "id_number": "",
                    "vip_status": False,
                    "loyalty_points": 0,
                    "total_stays": 0,
                    "total_spend": 0.0,
                    "created_at": _now_iso(),
                }
            )
        )

        booking_id = _uuid()
        confirmation_code = f"MKT-{booking_id[:8].upper()}"
        room_snapshot = _reservation_room_snapshot(available_room)
        agency_snapshot = _reservation_agency_snapshot(agency)
        product_snapshot = _rate_product_snapshot(data.rate_plan_code, available_room, contract, pricing)
        booking_doc = {
            "agency_completion": pending_completion('marketplace'),
            "hotel_name": listing.get("hotel_name"),
            "syroce_b2b_fee_pct": syroce_b2b_fee_pct,
            "syroce_b2b_fee_amount": syroce_b2b_fee_amount,
            "agency_idempotency_key": data.idempotency_key,
            "agency_request_hash": build_request_hash(data.model_dump()),
            "id": booking_id,
            "tenant_id": data.tenant_id,
            "guest_id": guest_id,
            "room_id": available_room["id"],
            **room_snapshot,
            "check_in": data.check_in + "T14:00:00",
            "check_out": data.check_out + "T11:00:00",
            "adults": data.adults,
            "children": data.children,
            "child_ages": data.child_ages,
            "guests_count": data.adults + data.children,
            "status": "confirmed",
            "payment_status": "pending",
            "payment_terms": contract.get("payment_terms", "on_arrival"),
            **product_snapshot,
            "total_amount": total,
            "currency": listing.get("currency", "TRY"),
            "nightly_rates": pricing["nightly_rates"],
            "balance": total,
            # Canonical fields are shared with hotel-created agency bookings so
            # every PMS surface can identify the exact seller consistently.
            **agency_snapshot,
            "agency_commission_rate": commission_pct,
            "agency_commission_amount": commission_amount,
            "net_to_hotel": net_to_hotel,
            "credit_exposure_amount": net_to_hotel,
            "credit_exposure_currency": listing.get("currency", "TRY"),
            "credit_exposure_basis": "net_to_hotel_after_agency_commission_v1",
            "confirmation_code": confirmation_code,
            "external_reference": data.external_reference,
            "special_requests": data.special_requests,
            "guest_name": data.guest_name.strip(),
            "guest_email": str(data.guest_email or "").strip().lower(),
            "guest_phone": data.guest_phone.strip(),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        # v106 architect follow-up (race-safety): direct insert_one bypassed
        # the room_night_locks atomic guard → marketplace agencies could
        # double-book the same room across concurrent requests. Now routed
        # through create_booking_atomic.
        try:
            booking_doc = await create_booking_atomic(tenant_id=data.tenant_id, booking_doc=booking_doc)
        except BookingConflictError as conflict_err:
            await db.guests.delete_one({"id": guest_id, "tenant_id": data.tenant_id})
            raise HTTPException(status_code=409, detail=str(conflict_err))
        except Exception:
            await db.guests.delete_one({"id": guest_id, "tenant_id": data.tenant_id})
            raise

    # Completion intent was stored atomically with the booking. The durable
    # worker repairs local projections and tracks downstream delivery.

    return {
        "ok": True,
        "reservation": {
            "integration_status": "pending",
            **product_snapshot,
            "id": booking_id,
            "confirmation_code": confirmation_code,
            "external_reference": data.external_reference,
            "tenant_id": data.tenant_id,
            "hotel_name": listing.get("hotel_name"),
            "status": "confirmed",
            **room_snapshot,
            "check_in": data.check_in,
            "check_out": data.check_out,
            "guest_name": data.guest_name,
            "total_amount": total,
            "currency": listing.get("currency", "TRY"),
            "nightly_rates": pricing["nightly_rates"],
            "commission_pct": commission_pct,
            "commission_amount": commission_amount,
            "syroce_b2b_fee_pct": syroce_b2b_fee_pct,
            "syroce_b2b_fee_amount": syroce_b2b_fee_amount,
            "net_to_hotel": net_to_hotel,
        },
    }


@router.post("/reservations")
async def agency_create_reservation_endpoint(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_agency),
):
    """Create once even when the agency retries concurrently after a timeout."""
    sysdb = get_system_db()
    if not data.idempotency_key:
        raise HTTPException(422, "Rezervasyonda idempotency_key zorunludur")
    guard = None
    if data.idempotency_key:
        claim = await claim_idempotency(
            sysdb,
            tenant_id=agency["agency_id"],
            scope="marketplace_reservation",
            idempotency_key=data.idempotency_key,
            request_hash=build_request_hash(data.model_dump()),
        )
        if claim["status"] == "replay":
            response = claim.get("response") or {}
            if response:
                return response
            existing = await sysdb.marketplace_bookings.find_one(
                {"agency_id": agency["agency_id"], "idempotency_key": data.idempotency_key}, {"_id": 0}
            )
            if existing:
                return {"ok": True, "reservation": existing, "idempotent_replay": True}
            raise HTTPException(409, "Önceki rezervasyon işlendi; sonucu rezervasyon listesinden kontrol edin")
        if claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı rezervasyon isteği halen işleniyor")
        if claim["status"] == "mismatch":
            raise HTTPException(409, "Bu işlem anahtarı farklı rezervasyon bilgileriyle kullanılmış")
        guard = claim["lock_id"]
    try:
        from core.agency_sales_guard import agency_sale_guard, durable_agency_replay

        async with agency_sale_guard(
            sysdb, data.tenant_id, agency["agency_id"],
            operation="marketplace_reservation", idempotency_key=data.idempotency_key,
        ):
            result = await durable_agency_replay(sysdb, data.tenant_id, agency["agency_id"], data.idempotency_key, build_request_hash(data.model_dump()))
            if result is None:
                result = await agency_create_reservation(data, background_tasks, agency)
        if guard:
            try:
                await complete_idempotency(sysdb, lock_id=guard, response_body=result)
            except Exception as exc:
                # Reservation and cross-tenant ledger are already durable.
                logger.error("Marketplace idempotency completion failed: %s", type(exc).__name__)
        return result
    except Exception as exc:
        if guard:
            await release_idempotency(sysdb, lock_id=guard, error=type(exc).__name__)
        raise


# ─── Public agency website widget (search + create only) ────────────────


@router.get("/widget/config")
async def marketplace_widget_config(
    agency: dict = Depends(get_marketplace_widget_agency),
):
    return {
        "agency": {"name": agency["agency_name"]},
        "brand_color": agency["widget_brand_color"],
        "capabilities": ["hotel_search", "live_availability", "live_pricing", "reservation_create"],
    }


@router.post("/widget/search")
async def marketplace_widget_search(
    data: MarketplaceSearchRequest,
    agency: dict = Depends(get_marketplace_widget_agency),
):
    """Public storefront search, scoped to the widget agency and its contracts."""
    return await agency_search(data, agency)


@router.post("/widget/reservations")
async def marketplace_widget_create_reservation(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_widget_agency),
):
    """Create a booking from an agency website with server-side revalidation."""
    if not data.idempotency_key:
        raise HTTPException(400, "Widget rezervasyonunda işlem anahtarı zorunludur")
    return await agency_create_reservation_endpoint(data, background_tasks, agency)


@router.get("/reservations")
async def agency_list_reservations(
    status: str | None = Query(None),
    tenant_id: str | None = Query(None, description="Belirli bir otele filtrele"),
    check_in_from: str | None = Query(None),
    check_in_to: str | None = Query(None),
    limit: int = Query(100, le=500),
    agency: dict = Depends(get_marketplace_agency),
):
    """Acentenin tüm marketplace rezervasyonları (cross-tenant)."""
    sysdb = get_system_db()
    query: dict = {"agency_id": agency["agency_id"]}
    if status:
        query["status"] = status
    if tenant_id:
        query["tenant_id"] = tenant_id
    if check_in_from:
        query.setdefault("check_in", {})["$gte"] = check_in_from
    if check_in_to:
        query.setdefault("check_in", {})["$lte"] = check_in_to

    docs = await sysdb.marketplace_bookings.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    docs = await refresh_ledger_from_pms(sysdb, docs)
    canonical_query = {**query, "agency_completion.kind": "marketplace"}
    if check_in_to:
        canonical_query["check_in"] = {**query["check_in"], "$lte": check_in_to + "T23:59:59.999999"}
    canonical = await sysdb.bookings.find(canonical_query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    merged = {row["id"]: row for row in docs}
    for row in canonical:
        merged[row["id"]] = {**merged.get(row["id"], {}), **public_booking(row)}
    docs = sorted(merged.values(), key=lambda row: str(row.get("created_at", "")), reverse=True)[:limit]
    return {"reservations": docs, "total": len(docs)}


@router.get("/reservations/{reservation_id}")
async def agency_get_reservation(
    reservation_id: str,
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    doc = await sysdb.marketplace_bookings.find_one({"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0})
    if not doc:
        pending = await sysdb.bookings.find_one({"id": reservation_id, "agency_id": agency["agency_id"],
                                               "agency_completion.kind": "marketplace"})
        if pending:
            return {"summary": public_booking(pending), "booking": public_booking(pending)}
        raise HTTPException(404, "Rezervasyon bulunamadı")

    with tenant_context(doc["tenant_id"]):
        booking = await db.bookings.find_one(
            {"id": reservation_id, "tenant_id": doc["tenant_id"]},
            {
                "_id": 0,
                "tenant_id": 0,
                "guest_id": 0,
                "room_id": 0,
                "guest_email": 0,
                "guest_phone": 0,
                "_hash_guest_email": 0,
                "_hash_guest_phone": 0,
                "_enc_version": 0,
                "_encrypted_at": 0,
                "guest_name_lower": 0,
            },
        )
    return {"summary": doc, "booking": public_booking(booking) if booking else None}


def _voucher_html(doc: dict) -> str:
    safe = lambda value: html.escape(str(value or "—"))
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Arial;color:#172033;padding:32px}}.sheet{{border:1px solid #ccd5e1;border-radius:12px;padding:24px}}table{{width:100%;border-collapse:collapse}}td{{padding:10px;border-bottom:1px solid #eee}}</style></head><body><div class='sheet'><h1>Rezervasyon Voucher</h1><table><tr><td>Onay kodu</td><td>{safe(doc.get('confirmation_code'))}</td></tr><tr><td>Otel</td><td>{safe(doc.get('hotel_name'))}</td></tr><tr><td>Misafir</td><td>{safe(doc.get('guest_name'))}</td></tr><tr><td>Giriş / Çıkış</td><td>{safe(doc.get('check_in'))} / {safe(doc.get('check_out'))}</td></tr><tr><td>Tutar</td><td>{safe(doc.get('total_amount'))} {safe(doc.get('currency', 'TRY'))}</td></tr></table><p>Syroce Acente Portalı tarafından oluşturulmuştur.</p></div></body></html>"""


async def _agency_voucher_booking(reservation_id: str, agency_id: str) -> dict:
    """Return the agency-authorized booking while its marketplace projection catches up.

    The canonical PMS booking is written atomically before the asynchronous
    marketplace ledger projection. Voucher availability must therefore follow
    the same fallback already used by the reservation list and detail views.
    """
    sysdb = get_system_db()
    doc = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency_id}, {"_id": 0}
    )
    if not doc:
        doc = await sysdb.bookings.find_one(
            {
                "id": reservation_id,
                "agency_id": agency_id,
                "agency_completion.kind": "marketplace",
            },
            {"_id": 0},
        )
    if not doc:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    return public_booking(doc)


@router.get("/reservations/{reservation_id}/voucher.pdf")
async def agency_reservation_voucher_pdf(reservation_id: str, agency: dict = Depends(get_marketplace_agency)):
    doc = await _agency_voucher_booking(reservation_id, agency["agency_id"])
    try:
        from weasyprint import HTML
        pdf = HTML(string=_voucher_html(doc)).write_pdf()
    except Exception as exc:
        raise HTTPException(503, "PDF oluşturucu şu anda kullanılamıyor") from exc
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={doc.get('confirmation_code', reservation_id)}.pdf"})


@router.post("/reservations/{reservation_id}/voucher-email")
async def agency_email_reservation_voucher(
    reservation_id: str, data: VoucherEmailRequest, agency: dict = Depends(get_marketplace_agency)
):
    doc = await _agency_voucher_booking(reservation_id, agency["agency_id"])
    from core.email import send_email
    result = await send_email(str(data.email), f"Rezervasyon Voucher · {doc.get('confirmation_code')}", _voucher_html(doc), sensitive=True)
    if not isinstance(result, dict) or not result.get("sent"):
        raise HTTPException(502, "Voucher e-postası gönderilemedi")
    return {"ok": True, "message": "Voucher e-postası gönderildi"}


@router.delete("/reservations/{reservation_id}")
async def agency_cancel_reservation(
    reservation_id: str,
    reason: str = Query("agency_request"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Open a cancellation negotiation; hotel approval is mandatory."""
    sysdb = get_system_db()
    summary = await sysdb.marketplace_bookings.find_one({"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0})
    if not summary:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if summary.get("status") == "cancelled":
        return {"ok": True, "message": "Rezervasyon zaten iptal edilmiş"}
    normalized_reason = reason.strip()
    if len(normalized_reason) < 5:
        raise HTTPException(400, "İptal gerekçesi en az 5 karakter olmalıdır")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "agency_cancellation", "status": "awaiting_hotel"},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için otel yanıtı bekleyen iptal talebi zaten var")
    proposal = {
        "id": _uuid(),
        "reservation_id": reservation_id,
        "tenant_id": summary["tenant_id"],
        "agency_id": agency["agency_id"],
        "hotel_name": summary.get("hotel_name"),
        "confirmation_code": summary.get("confirmation_code"),
        "guest_name": summary.get("guest_name"),
        "type": "agency_cancellation",
        "reason": normalized_reason,
        "status": "awaiting_hotel",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(summary["tenant_id"]):
        await db.notifications.insert_one(
            {
                "id": _uuid(),
                "tenant_id": summary["tenant_id"],
                "type": "agency_negotiation",
                "title": "Acente iptal onayı bekliyor",
                "message": f"{summary.get('confirmation_code')} için iptal talebi iletildi.",
                "read": False,
                "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id},
                "created_at": _now_iso(),
            }
        )
    return {"ok": True, "message": "İptal talebi otele iletildi", "proposal": {k: v for k, v in proposal.items() if k != "_id"}}


@router.post("/reservations/{reservation_id}/modification-proposals")
async def agency_propose_reservation_modification(
    reservation_id: str,
    data: ModificationProposalCreate,
    agency: dict = Depends(get_marketplace_agency),
):
    """Request a stay/room change; PMS approval is mandatory before mutation."""
    if data.check_out <= data.check_in:
        raise HTTPException(400, "Çıkış tarihi giriş tarihinden sonra olmalıdır")
    sysdb = get_system_db()
    booking = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"], "status": "confirmed"}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(404, "Değiştirilebilir aktif rezervasyon bulunamadı")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "agency_modification", "status": "awaiting_hotel"}
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için otel yanıtı bekleyen değişiklik zaten var")
    proposal = {
        "id": _uuid(),
        "reservation_id": reservation_id,
        "tenant_id": booking["tenant_id"],
        "agency_id": agency["agency_id"],
        "hotel_name": booking.get("hotel_name"),
        "confirmation_code": booking.get("confirmation_code"),
        "guest_name": booking.get("guest_name"),
        "type": "agency_modification",
        "reason": data.reason.strip(),
        "requested": data.model_dump(exclude={"reason"}),
        "current": {key: booking.get(key) for key in ("check_in", "check_out", "room_type", "total_amount")},
        "status": "awaiting_hotel",
        "expires_at": (datetime.now(UTC) + timedelta(hours=48)).isoformat(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(booking["tenant_id"]):
        await db.notifications.insert_one(
            {
                "id": _uuid(),
                "tenant_id": booking["tenant_id"],
                "type": "agency_negotiation",
                "title": "Acente değişiklik onayı bekliyor",
                "message": f"{booking.get('confirmation_code')} için tarih/oda tipi değişikliği talep edildi.",
                "read": False,
                "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id},
                "created_at": _now_iso(),
            }
        )
    proposal.pop("_id", None)
    return {"ok": True, "proposal": proposal}


@router.post("/hotel/negotiations/{proposal_id}/decision")
async def hotel_decide_marketplace_modification(
    proposal_id: str,
    data: CancellationProposalDecision,
    current_user: User = Depends(get_current_user),
):
    from core.agency_sales_guard import agency_sale_guard
    tenant_id = _require_hotel_admin(current_user)
    system = get_system_db()
    proposal = await system.marketplace_negotiations.find_one({"id": proposal_id, "tenant_id": tenant_id})
    if not proposal:
        raise HTTPException(404, "Değişiklik talebi bulunamadı")
    async with agency_sale_guard(
        system, tenant_id, proposal["agency_id"], operation="marketplace_modification",
        reference_id=proposal_id,
    ):
        with tenant_context(tenant_id):
            return await _decide_marketplace_modification_locked(proposal_id, data, current_user)


async def _decide_marketplace_modification_locked(proposal_id, data, current_user):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    proposal = await sysdb.marketplace_negotiations.find_one(
        {
            "id": proposal_id,
            "tenant_id": tenant_id,
            "type": {"$in": ["agency_modification", "agency_cancellation"]},
            "status": "awaiting_hotel",
        },
        {"_id": 0},
    )
    if not proposal:
        raise HTTPException(404, "Yanıt bekleyen değişiklik talebi bulunamadı")
    if proposal.get("expires_at") and datetime.fromisoformat(proposal["expires_at"]) < datetime.now(UTC):
        await sysdb.marketplace_negotiations.update_one({"id": proposal_id}, {"$set": {"status": "expired"}})
        raise HTTPException(409, "Değişiklik teklifinin 48 saatlik süresi dolmuş")

    if data.accept and proposal["type"] == "agency_modification":
        requested = proposal["requested"]
        from routers.agency_contracts import has_active_contract

        last_night = _last_occupied_date(requested["check_in"], requested["check_out"])
        contract = await has_active_contract(
            proposal["agency_id"], tenant_id, on_date=requested["check_in"], through_date=last_night
        )
        if not contract:
            raise HTTPException(409, "Yeni tarihler aktif acente sözleşmesi kapsamında değil")
        listing = await _get_listing_or_404(tenant_id)
        for policy in (contract, listing):
            if policy.get("allowed_room_types") and requested["room_type"] not in policy["allowed_room_types"]:
                raise HTTPException(409, "İstenen oda tipi acente satışına açık değil")
        if any(day in listing.get("blocked_dates", []) for day in _date_range(requested["check_in"], requested["check_out"])):
            raise HTTPException(409, "Bu tarihler otel tarafından kapatılmış")
        with tenant_context(tenant_id):
            rooms = await db.rooms.find(
                {"tenant_id": tenant_id, "room_type": requested["room_type"], "is_active": {"$ne": False},
                 "status": {"$nin": ["maintenance", "out_of_order", "blocked"]}}, {"_id": 0}
            ).to_list(500)
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": tenant_id}, {"_id": 0})
        if not booking or booking.get("status") != "confirmed" or booking.get("agency_id") != proposal["agency_id"]:
            raise HTTPException(409, "Rezervasyon artık değiştirilebilir durumda değil")
        adults, children = int(booking.get("adults", 2)), int(booking.get("children", 0))
        child_ages = booking.get("child_ages") or []
        rooms = [room for room in rooms if int(room.get("capacity") or 2) >= adults + children]
        if not rooms:
            raise HTTPException(409, "İstenen oda tipinde aktif oda bulunamadı")
        plan = requested.get("rate_plan_code")
        if not plan:
            raise HTTPException(409, "Eski teklif fiyat planı içermiyor; yeni teklif oluşturun")
        commission_pct = _contract_commission(contract)
        fee_pct = float(booking.get("syroce_b2b_fee_pct", 0) or 0)
        selected_room = None
        for room in rooms:
            pricing = await _validated_agency_quote(
                tenant_id=tenant_id, agency_id=proposal["agency_id"], room=room,
                check_in=requested["check_in"], check_out=requested["check_out"], rate_plan_code=plan,
                adults=adults, children=children, child_ages=child_ages, exclude_booking_id=booking["id"],
                allow_base_rate_fallback=bool(contract.get("allow_base_rate_fallback")),
            )
            financials = _marketplace_financials(pricing["total_price"], commission_pct, fee_pct)
            await _check_agency_credit(tenant_id=tenant_id, agency_id=proposal["agency_id"],
                contract=contract, net_to_hotel=financials["net_to_hotel"],
                booking_currency=booking.get("currency", "TRY"), exclude_booking_id=booking["id"])
            try:
                await assign_room_atomic(
                    tenant_id=tenant_id,
                    booking_id=proposal["reservation_id"],
                    room_id=room["id"],
                    check_in=requested["check_in"] + "T14:00:00",
                    check_out=requested["check_out"] + "T11:00:00",
                    release_obsolete=False,
                )
                selected_room = room
                break
            except BookingConflictError:
                continue
        if not selected_room:
            raise HTTPException(409, "İstenen tarihlerde uygun fiziksel oda bulunamadı")
        total = float(pricing["total_price"])
        paid = float(booking.get("total_paid", 0) or 0)
        financials = _marketplace_financials(total, commission_pct, fee_pct)
        changes = {
            **_rate_product_snapshot(plan, selected_room, contract, pricing),
            "occupancy_pricing": pricing.get("occupancy_pricing"),
            "agency_commission_rate": commission_pct,
            "check_in": requested["check_in"] + "T14:00:00",
            "check_out": requested["check_out"] + "T11:00:00",
            "room_id": selected_room["id"],
            "room_number": selected_room.get("room_number", ""),
            "room_type": requested["room_type"],
            "nightly_rates": pricing["nightly_rates"],
            "total_amount": total,
            "balance": max(0, round(total - paid, 2)),
            "agency_commission_amount": financials["commission_amount"],
            "syroce_b2b_fee_pct": fee_pct,
            **financials,
            "credit_exposure_amount": financials["net_to_hotel"],
            "credit_exposure_currency": booking.get("currency", "TRY"),
            "credit_exposure_basis": "net_to_hotel_after_agency_commission_v1",
            "updated_at": _now_iso(),
        }
        with tenant_context(tenant_id):
            updated = await db.bookings.update_one({"id": proposal["reservation_id"], "tenant_id": tenant_id,
                "agency_id": proposal["agency_id"], "status": "confirmed"}, {"$set": changes})
            if updated.matched_count == 0:
                # Locks already acquired: retain the fence for reconciliation.
                raise RuntimeError("Booking changed while applying agency modification")
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "tenant_id": tenant_id}, {"$set": changes}
        )
        # Re-enter idempotently only after persistence, then release the old
        # nights. An exception before here keeps the admission fence intact.
        await assign_room_atomic(tenant_id=tenant_id, booking_id=booking["id"],
            room_id=selected_room["id"], check_in=changes["check_in"], check_out=changes["check_out"])
    elif data.accept:
        with tenant_context(tenant_id):
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": tenant_id})
            if not booking or booking.get("status") in {"checked_in", "checked_out", "cancelled"}:
                raise HTTPException(409, "Rezervasyon artık iptal edilebilir durumda değil")
            await db.bookings.update_one(
                {"id": proposal["reservation_id"], "tenant_id": tenant_id},
                {"$set": {"status": "cancelled", "cancellation_reason": proposal["reason"], "cancelled_by": "mutual_agreement", "cancelled_at": _now_iso(), "updated_at": _now_iso()}},
            )
            from core.atomic_booking import release_booking_nights

            await release_booking_nights(tenant_id, proposal["reservation_id"], reason="mutual_agreement")
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "tenant_id": tenant_id},
            {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancellation_reason": proposal["reason"]}},
        )

    status_value = "accepted" if data.accept else "declined"
    await sysdb.marketplace_negotiations.update_one(
        {"id": proposal_id, "status": "awaiting_hotel"},
        {"$set": {"status": status_value, "response_note": data.response_note.strip(), "responded_at": _now_iso(), "updated_at": _now_iso(),
                  "applied_snapshot": ({key: changes[key] for key in (
                      "check_in", "check_out", "room_id", "room_type", "rate_plan_code", "total_amount",
                      "net_to_hotel", "credit_exposure_amount", "credit_exposure_currency",
                      "nightly_rates", "meal_plan", "cancellation_policy",
                  )} if data.accept and proposal["type"] == "agency_modification" else
                  {"status": "cancelled"} if data.accept else {})}},
    )
    return {
        "ok": True,
        "status": status_value,
        "reservation_modified": bool(data.accept and proposal["type"] == "agency_modification"),
        "reservation_cancelled": bool(data.accept and proposal["type"] == "agency_cancellation"),
    }


@router.post("/hotel/reservations/{reservation_id}/cancellation-proposals")
async def hotel_propose_marketplace_cancellation(
    reservation_id: str,
    data: CancellationProposalCreate,
    current_user: User = Depends(get_current_user),
):
    """Hotel may propose, but never unilaterally execute, an agency cancellation."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    booking = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "tenant_id": tenant_id, "status": {"$ne": "cancelled"}}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(404, "Aktif acente rezervasyonu bulunamadı")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "hotel_cancellation", "status": "awaiting_agency"}, {"_id": 0}
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için acente yanıtı bekleyen bir teklif zaten var")
    proposal = {
        "id": _uuid(), "reservation_id": reservation_id, "tenant_id": tenant_id,
        "agency_id": booking["agency_id"], "hotel_name": booking.get("hotel_name"),
        "confirmation_code": booking.get("confirmation_code"), "guest_name": booking.get("guest_name"),
        "type": "hotel_cancellation", "reason": data.reason.strip(), "status": "awaiting_agency",
        "created_by": current_user.id, "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(tenant_id):
        await db.notifications.insert_one({
            "id": _uuid(), "tenant_id": tenant_id, "type": "agency_negotiation", "title": "Acente yanıtı bekleniyor",
            "message": f"{booking.get('confirmation_code')} için iptal önerisi acenteye iletildi.", "read": False,
            "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id}, "created_at": _now_iso(),
        })
    return {"ok": True, "proposal": {k: v for k, v in proposal.items() if k != "_id"}}


@router.get("/hotel/negotiations")
async def hotel_list_marketplace_negotiations(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    docs = await get_system_db().marketplace_negotiations.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"items": docs}


@router.get("/notices")
async def agency_list_notices(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    agency: dict = Depends(get_marketplace_agency),
):
    """Hotel-originated notices for this agency (contract decisions, PMS cancellations)."""
    query: dict = {"agency_id": agency["agency_id"]}
    if unread_only:
        query["read"] = False
    sysdb = get_system_db()
    items = await sysdb.marketplace_agency_notices.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await sysdb.marketplace_agency_notices.count_documents({"agency_id": agency["agency_id"], "read": False})
    return {"items": items, "unread": unread}


@router.post("/notices/{notice_id}/read")
async def agency_mark_notice_read(notice_id: str, agency: dict = Depends(get_marketplace_agency)):
    result = await get_system_db().marketplace_agency_notices.update_one(
        {"id": notice_id, "agency_id": agency["agency_id"]}, {"$set": {"read": True, "read_at": _now_iso()}}
    )
    if not result.matched_count:
        raise HTTPException(404, "Bildirim bulunamadı")
    return {"ok": True}


@router.get("/negotiations")
async def agency_list_negotiations(agency: dict = Depends(get_marketplace_agency)):
    docs = await get_system_db().marketplace_negotiations.find(
        {"agency_id": agency["agency_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"items": docs}


@router.post("/negotiations/{proposal_id}/decision")
async def agency_decide_negotiation(
    proposal_id: str,
    data: CancellationProposalDecision,
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    proposal = await sysdb.marketplace_negotiations.find_one(
        {"id": proposal_id, "agency_id": agency["agency_id"], "status": "awaiting_agency"}, {"_id": 0}
    )
    if not proposal:
        raise HTTPException(404, "Yanıt bekleyen teklif bulunamadı")
    status_value = "accepted" if data.accept else "declined"
    if data.accept:
        with tenant_context(proposal["tenant_id"]):
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": proposal["tenant_id"]})
            if not booking or booking.get("status") in {"checked_in", "checked_out", "cancelled"}:
                raise HTTPException(409, "Rezervasyon artık iptal edilebilir durumda değil")
            await db.bookings.update_one(
                {"id": proposal["reservation_id"], "tenant_id": proposal["tenant_id"]},
                {"$set": {"status": "cancelled", "cancellation_reason": proposal["reason"], "cancelled_by": "mutual_agreement", "cancelled_at": _now_iso(), "updated_at": _now_iso()}},
            )
            from core.atomic_booking import release_booking_nights
            await release_booking_nights(proposal["tenant_id"], proposal["reservation_id"], reason="mutual_agreement")
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "agency_id": agency["agency_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancellation_reason": proposal["reason"]}},
        )
    await sysdb.marketplace_negotiations.update_one(
        {"id": proposal_id, "status": "awaiting_agency"},
        {"$set": {"status": status_value, "response_note": data.response_note.strip(), "responded_at": _now_iso(), "updated_at": _now_iso()}},
    )
    return {"ok": True, "status": status_value, "reservation_cancelled": bool(data.accept)}


# ═══════════════════════════════════════════════════════════════════════
# Reconciliation — Cross-tenant Komisyon Raporu
# ═══════════════════════════════════════════════════════════════════════


@router.get("/reconciliation/agency")
async def agency_reconciliation(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Acente için dönem bazlı komisyon ve ciro özeti."""
    sysdb = get_system_db()
    docs = await sysdb.marketplace_bookings.find(
        {
            "agency_id": agency["agency_id"],
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).to_list(None)
    docs = await refresh_ledger_from_pms(sysdb, docs)

    from core.agency_reporting import combined_summary, currency_code
    by_hotel: dict = {}
    totals_by_currency = {}
    for d in docs:
        currency = currency_code(d.get('currency'))
        totals = totals_by_currency.setdefault(currency, {"currency": currency, "gross_revenue": 0.0, "commission": 0.0, "platform_fee": 0.0, "net_to_hotels": 0.0, "bookings": 0, "cancelled": 0, "no_show": 0})
        if d.get("status") in NON_REVENUE_STATUSES:
            totals[d["status"]] += 1
            continue
        tid = d["tenant_id"]
        bucket = by_hotel.setdefault(
            (tid, currency),
            {
                "tenant_id": tid,
                "currency": currency,
                "hotel_name": d.get("hotel_name"),
                "bookings": 0,
                "gross_revenue": 0.0,
                "commission": 0.0,
                "platform_fee": 0.0,
                "net_to_hotel": 0.0,
            },
        )
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        platform_fee = float(d.get("syroce_b2b_fee_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission"] += comm
        bucket["platform_fee"] += platform_fee
        bucket["net_to_hotel"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["platform_fee"] += platform_fee
        totals["net_to_hotels"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "agency_id": agency["agency_id"],
        "totals": combined_summary(totals_by_currency),
        "totals_by_currency": [{k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()} for row in totals_by_currency.values()],
        "by_hotel": [{**v, "gross_revenue": round(v["gross_revenue"], 2), "commission": round(v["commission"], 2), "platform_fee": round(v["platform_fee"], 2), "net_to_hotel": round(v["net_to_hotel"], 2)} for v in by_hotel.values()],
    }


_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(value, *, force_text: bool = False) -> str:
    """Spreadsheet-safe text cell.

    Hotel and guest names are typed by other parties; a value starting with a
    formula character would run as a formula when the CSV is opened. A leading
    apostrophe keeps it visible text. ``force_text`` also protects references
    such as confirmation codes that spreadsheets would otherwise reformat.
    """
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    if force_text or text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


@router.get("/reconciliation/agency.csv")
async def agency_reconciliation_csv(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Download an agency-owned, spreadsheet-safe reconciliation detail."""
    sysdb = get_system_db()
    docs = await sysdb.marketplace_bookings.find(
        {
            "agency_id": agency["agency_id"],
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).sort("check_in", 1).to_list(None)
    docs = await refresh_ledger_from_pms(sysdb, docs)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Onay Kodu", "Otel", "Misafir", "Giriş", "Çıkış", "Durum", "Para Birimi", "Brüt", "Komisyon", "Platform Bedeli", "Otele Net"])
    for item in docs:
        writer.writerow(
            [
                _csv_text(item.get("confirmation_code") or item.get("id"), force_text=True),
                _csv_text(item.get("hotel_name")),
                _csv_text(item.get("guest_name")),
                str(item.get("check_in", ""))[:10],
                str(item.get("check_out", ""))[:10],
                _csv_text(item.get("status")),
                item.get("currency") or "UNKNOWN",
                round(float(item.get("total_amount", 0) or 0), 2),
                round(float(item.get("commission_amount", 0) or 0), 2),
                round(float(item.get("syroce_b2b_fee_amount", 0) or 0), 2),
                round(float(item.get("net_to_hotel", 0) or 0), 2),
            ]
        )
    filename = f"acente-mutabakat-{period_start}-{period_end}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reconciliation/hotel")
async def hotel_reconciliation(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
):
    """Otel için marketplace üzerinden gelen rezervasyonların komisyon raporu."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    docs = await sysdb.marketplace_bookings.find(
        {
            "tenant_id": tenant_id,
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).to_list(None)
    docs = await refresh_ledger_from_pms(sysdb, docs)

    from core.agency_reporting import combined_summary, currency_code
    by_agency: dict = {}
    totals_by_currency = {}
    for d in docs:
        currency = currency_code(d.get('currency'))
        totals = totals_by_currency.setdefault(currency, {"currency": currency, "gross_revenue": 0.0, "commission": 0.0, "platform_fee": 0.0, "net_to_hotel": 0.0, "bookings": 0, "cancelled": 0, "no_show": 0})
        if d.get("status") in NON_REVENUE_STATUSES:
            totals[d["status"]] += 1
            continue
        aid = d["agency_id"]
        bucket = by_agency.setdefault(
            (aid, currency),
            {
                "agency_id": aid,
                "currency": currency,
                "bookings": 0,
                "gross_revenue": 0.0,
                "commission_owed": 0.0,
                "platform_fee": 0.0,
                "net_received": 0.0,
            },
        )
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        platform_fee = float(d.get("syroce_b2b_fee_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission_owed"] += comm
        bucket["platform_fee"] += platform_fee
        bucket["net_received"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["platform_fee"] += platform_fee
        totals["net_to_hotel"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "tenant_id": tenant_id,
        "totals": combined_summary(totals_by_currency),
        "totals_by_currency": [{k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()} for row in totals_by_currency.values()],
        "by_agency": [{**v, "gross_revenue": round(v["gross_revenue"], 2), "commission_owed": round(v["commission_owed"], 2), "platform_fee": round(v["platform_fee"], 2), "net_received": round(v["net_received"], 2)} for v in by_agency.values()],
    }


# ─── Utility ──────────────────────────────────────────────────────────────


def _date_range(start: str, end: str) -> list[str]:
    """[start, end) aralığındaki YYYY-MM-DD listesi."""
    from datetime import date, timedelta

    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out = []
    while s < e:
        out.append(s.isoformat())
        s += timedelta(days=1)
    return out
