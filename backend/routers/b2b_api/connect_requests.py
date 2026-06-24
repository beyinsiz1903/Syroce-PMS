"""
B2B agency connect-request flow (Seçenek B / approval model).

Two distinct auth surfaces on the SAME `/api/b2b` prefix:

  Connect-code auth (header `X-Connect-Code`, NO JWT) — for the agency app:
    POST /api/b2b/connect-requests        intake a pending connection request
    GET  /api/b2b/connect-requests/{id}   poll status; deliver the key ONCE

  JWT hotel-staff auth (+ require_op) — for the PMS UI:
    GET  /api/b2b/connect-info                     connect-code status + ids
    POST /api/b2b/connect-codes/regenerate         create/rotate the code (raw 1x)
    GET  /api/b2b/connect-requests                  list this tenant's requests
    POST /api/b2b/connect-requests/{id}/approve     approve + mint + attach key
    POST /api/b2b/connect-requests/{id}/reject      reject

Doctrine: an API key can NEVER be minted without an explicit hotel approval.
Tenant identity is resolved server-side (code hash or JWT), never from the body.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

from ._provisioning import (
    DEFAULT_AUTO_SCOPES,
    KEY_DELIVERY_TTL_HOURS,
    REQUEST_TTL_DAYS,
    _now,
    _now_iso,
    _uuid,
    decrypt_delivery_key,
    encrypt_delivery_key,
    generate_connect_code,
    generate_delivery_token,
    get_connect_info,
    hash_delivery_token,
    mint_agency_api_key,
    normalize_agency_name,
    resolve_tenant_from_code,
)
from ._scope import normalize_scopes
from .api_keys import _require_hotel_staff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/b2b", tags=["B2B Connect - Syroce"])

# Same op gate as manual key issuance (api_keys.py create/regenerate/revoke):
# minting a key and managing connection requests are equally sensitive.
_OP = "view_system_diagnostics"

# Per-tenant intake DoS bound for NEW connection requests, layered on top of the
# global per-IP middleware limiter. A single hotel onboarding agencies never
# legitimately files this many distinct requests in an hour.
INTAKE_MAX_PER_HOUR = 30

# Returned on every idempotent intake retry. The per-request delivery token is
# hash-only and unrecoverable, so retries cannot re-issue it; the caller must
# persist request_id + request_token from the original 201 create response.
_IDEMPOTENT_MSG = (
    "Bu acente icin zaten bir baglanti istegi mevcut. Ilk olusturma yanitindaki "
    "request_id ve request_token degerleriyle durumu sorgulayin; bu degerler "
    "kaybedildiyse otelden istegi reddedip yeniden olusturmasini isteyin."
)


# ── Models (strict, bounded) ─────────────────────────────────────

class ConnectRequestIn(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    agency_name: str = Field(..., min_length=2, max_length=120)
    contact_name: str = Field("", max_length=120)
    contact_email: str = Field("", max_length=160)
    contact_phone: str = Field("", max_length=40)
    note: str = Field("", max_length=500)
    external_agency_id: str = Field("", max_length=120)
    agency_platform_request_id: str = Field("", max_length=120)
    requested_scopes: list[str] | None = Field(None, max_length=20)


class ApproveIn(BaseModel):
    model_config = {"extra": "forbid"}
    scopes: list[str] | None = Field(None, max_length=20)
    regenerate_if_exists: bool = False


class RejectIn(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    reason: str = Field("", max_length=300)


# ── Auth helpers ─────────────────────────────────────────────────

async def _require_connect_code(
    x_connect_code: str | None = Header(None, alias="X-Connect-Code"),
) -> str:
    """Resolve the owning tenant_id from the connect code. Generic 401 — never
    leaks whether a given tenant/code exists."""
    tenant_id = await resolve_tenant_from_code(get_system_db(), x_connect_code)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Gecersiz baglanti kodu")
    return tenant_id


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _resolve_scopes(*candidates) -> list[str]:
    """First non-empty validated scope list, else least-privilege default.
    Never returns None (unrestricted) for an auto-provisioned key."""
    for c in candidates:
        if c:
            norm = normalize_scopes(c)  # raises 400 on unknown scope
            if norm:
                return norm
    return list(DEFAULT_AUTO_SCOPES)


# ═══════════════════════════════════════════════════════════════════
# CONNECT-CODE AUTH (agency app) — no JWT
# ═══════════════════════════════════════════════════════════════════

@router.post("/connect-requests", status_code=201)
async def create_connect_request(
    payload: ConnectRequestIn,
    request: Request,
    tenant_id: str = Depends(_require_connect_code),
):
    """Agency app files a pending connection request. Idempotent on
    agency_platform_request_id and on an open pending row for the same agency."""
    sysdb = get_system_db()

    name_lower = normalize_agency_name(payload.agency_name)
    if len(name_lower) < 2:
        raise HTTPException(status_code=422, detail="Gecersiz acente adi")

    apr = payload.agency_platform_request_id.strip()
    if apr:
        prior = await sysdb.b2b_connection_requests.find_one(
            {"tenant_id": tenant_id, "agency_platform_request_id": apr},
            {"_id": 0, "id": 1, "status": 1},
        )
        if prior:
            # Idempotent retry: the per-request delivery token was returned only on
            # the FIRST create and is unrecoverable (hash-only). We therefore return
            # neither the request_id nor a token here — the caller MUST persist both
            # from the original 201. This keeps a connect-code holder from harvesting
            # an existing request's id by resubmitting a known agency name.
            return {"status": prior.get("status", "pending"), "idempotent": True,
                    "message": _IDEMPOTENT_MSG}

    open_pending = await sysdb.b2b_connection_requests.find_one(
        {"tenant_id": tenant_id, "agency_name_lower": name_lower, "status": "pending"},
        {"_id": 0, "id": 1},
    )
    if open_pending:
        return {"status": "pending", "idempotent": True, "message": _IDEMPOTENT_MSG}

    # DoS bound: only genuinely-new requests reach here (idempotent retries
    # returned above). created_at is an ISO-8601 UTC string, so a lexicographic
    # $gte against an ISO window-start is correct. Bounded count via `limit`.
    window_start = (_now() - timedelta(hours=1)).isoformat()
    recent = await sysdb.b2b_connection_requests.count_documents(
        {"tenant_id": tenant_id, "created_at": {"$gte": window_start}},
        limit=INTAKE_MAX_PER_HOUR + 1,
    )
    if recent >= INTAKE_MAX_PER_HOUR:
        logger.warning("B2B intake rate-limited tenant=%s", tenant_id)  # no PII
        raise HTTPException(
            status_code=429,
            detail="Cok fazla baglanti istegi; lutfen daha sonra tekrar deneyin",
        )

    # Per-request delivery token: raw value returned to THIS caller exactly once
    # below; only its HMAC is persisted. Required (with the connect code) to poll
    # for status / retrieve the key, so the shared hotel connect code alone can
    # never read another agency's key.
    raw_token = generate_delivery_token()

    now = _now()
    doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "status": "pending",
        "agency_name": payload.agency_name.strip(),
        "agency_name_lower": name_lower,
        "contact_name": payload.contact_name.strip(),
        "contact_email": payload.contact_email.strip(),
        "contact_phone": payload.contact_phone.strip(),
        "note": payload.note.strip(),
        "requested_scopes": payload.requested_scopes,
        "external_agency_id": (payload.external_agency_id.strip() or None),
        "delivery_token_hash": hash_delivery_token(raw_token),
        "source_ip": _client_ip(request),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        # BSON Date (NOT isoformat) so the TTL index + $gt comparisons work.
        "expires_at": now + timedelta(days=REQUEST_TTL_DAYS),
        "api_key_consumed_at": None,
    }
    if apr:
        doc["agency_platform_request_id"] = apr

    try:
        await sysdb.b2b_connection_requests.insert_one(doc)
    except DuplicateKeyError:
        # Lost the partial-unique pending race — the winning request belongs to an
        # earlier caller whose token we cannot reissue. Return idempotent without
        # id/token (caller must use the original 201's values).
        return {"status": "pending", "idempotent": True, "message": _IDEMPOTENT_MSG}

    logger.info("B2B connect request created tenant=%s", tenant_id)  # no PII
    return {"request_id": doc["id"], "request_token": raw_token, "status": "pending",
            "message": "request_token yalnizca burada bir kez doner. Guvenli saklayin."}


@router.get("/connect-requests/{request_id}")
async def poll_connect_request(
    request_id: str,
    tenant_id: str = Depends(_require_connect_code),
    x_request_token: str | None = Header(None, alias="X-Request-Token"),
):
    """Agency app polls status. Requires BOTH the hotel connect code (resolves the
    tenant) AND the per-request delivery token returned once at create time, so a
    party that only knows the shared hotel connect code can never read another
    agency's key or status. On the first authenticated poll after approval the raw
    key is returned exactly once (atomic read-once), then the ciphertext is unset.
    """
    sysdb = get_system_db()
    now = _now()

    if not x_request_token or not x_request_token.strip():
        raise HTTPException(status_code=401, detail="Istek dogrulama anahtari gerekli")
    token_hash = hash_delivery_token(x_request_token.strip())

    # Single uniform lookup BOUND to the per-request token hash. A wrong/absent
    # token AND a non-existent request_id both resolve to None -> the identical
    # 401 below, so a connect-code holder gets NO request-id existence oracle (no
    # 404-vs-401 distinction). The HMAC token is matched by its server-side hash,
    # exactly like a hashed session / API token lookup.
    current = await sysdb.b2b_connection_requests.find_one(
        {"id": request_id, "tenant_id": tenant_id, "delivery_token_hash": token_hash},
        {"_id": 0, "encrypted_api_key": 0, "source_ip": 0},
    )
    if not current:
        raise HTTPException(status_code=401, detail="Gecersiz istek dogrulamasi")

    # Atomic single-shot delivery, additionally bound to the token hash so two
    # concurrent authenticated polls still deliver the key at most once.
    claimed = await sysdb.b2b_connection_requests.find_one_and_update(
        {
            "id": request_id,
            "tenant_id": tenant_id,
            "status": "approved",
            "delivery_token_hash": token_hash,
            "api_key_consumed_at": None,
            "key_delivery_expires_at": {"$gt": now},
        },
        {"$set": {"api_key_consumed_at": now},
         "$unset": {"encrypted_api_key": ""}},
        return_document=ReturnDocument.BEFORE,
    )
    if claimed and claimed.get("encrypted_api_key"):
        try:
            raw_key = decrypt_delivery_key(claimed["encrypted_api_key"])
        except ValueError:
            logger.error("B2B key decrypt failed tenant=%s", tenant_id)
            raise HTTPException(status_code=500, detail="Key teslim hatasi")
        return {
            "status": "approved",
            "api_key": raw_key,
            "agency_id": claimed.get("agency_id"),
            "scopes": claimed.get("scopes"),
            "key_prefix": claimed.get("key_prefix"),
            "message": "API key tek seferlik teslim edildi. Guvenli saklayin.",
        }

    status = current.get("status")
    if status in ("pending", "approving"):
        return {"status": "pending", "message": "Onay bekleniyor."}
    if status == "rejected":
        return {"status": "rejected", "reason": current.get("reject_reason", ""),
                "message": "Baglanti istegi reddedildi."}

    # status == approved but no key was delivered now → explain why.
    if current.get("delivery_state") == "existing_key_not_retrievable":
        return {"status": "approved", "key_available": False,
                "reason": "connected_existing_key_not_retrievable",
                "message": "Bu acente icin zaten aktif key var; tekrar teslim edilemez. Oteldan yenileme isteyin."}
    if current.get("api_key_consumed_at"):
        return {"status": "approved", "key_available": False, "reason": "already_retrieved",
                "message": "API key zaten tek seferlik teslim edildi."}
    return {"status": "approved", "key_available": False, "reason": "delivery_expired",
            "message": "Key teslim suresi doldu. Oteldan yenileme isteyin."}


# ═══════════════════════════════════════════════════════════════════
# JWT HOTEL-STAFF AUTH (PMS UI)
# ═══════════════════════════════════════════════════════════════════

@router.get("/connect-info")
async def connect_info(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op(_OP)),
):
    """Connect-code status (read-only; never creates a code) + display ids."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    sysdb = get_system_db()
    info = await get_connect_info(sysdb, tenant_id)
    tdoc = await sysdb.tenants.find_one({"id": tenant_id}, {"_id": 0, "hotel_id": 1})
    info["tenant_id"] = tenant_id
    info["hotel_id"] = (tdoc or {}).get("hotel_id")
    return info


@router.post("/connect-codes/regenerate")
async def regenerate_connect_code(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op(_OP)),
):
    """Create (if none) or rotate the connect code. Raw value returned ONCE."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    res = await generate_connect_code(get_system_db(), tenant_id)
    logger.info("B2B connect code rotated tenant=%s", tenant_id)  # no raw value
    return {
        "connect_code": res["connect_code"],
        "code_prefix": res["code_prefix"],
        "created_at": res["created_at"],
        "message": "Bu kod yalnizca bir kez gosterilir. Guvenli saklayin.",
    }


@router.get("/connect-requests")
async def list_connect_requests(
    status: str | None = Query(None, description="pending|approved|rejected"),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op(_OP)),
):
    """List this tenant's connection requests (secrets/IP projected out)."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    sysdb = get_system_db()
    query: dict = {"tenant_id": tenant_id}
    if status in ("pending", "approved", "rejected"):
        query["status"] = status
    cursor = (
        sysdb.b2b_connection_requests.find(
            query, {"_id": 0, "encrypted_api_key": 0, "source_ip": 0}
        )
        .sort("created_at", -1)
        .limit(200)
    )
    items = await cursor.to_list(length=200)
    return {"items": items, "count": len(items)}


async def _release_approving_claim(sysdb, tenant_id: str, request_id: str) -> None:
    """Revert an in-flight 'approving' claim to 'pending' so a corrected retry can
    re-approve. No-op if the row already advanced (e.g. delivered)."""
    await sysdb.b2b_connection_requests.update_one(
        {"id": request_id, "tenant_id": tenant_id, "status": "approving"},
        {"$set": {"status": "pending", "updated_at": _now_iso()},
         "$unset": {"approving_by": "", "approving_at": ""}},
    )


async def _match_or_create_agency(sysdb, tenant_id: str, req: dict, created_by: str) -> dict:
    ext = req.get("external_agency_id")
    agency = None
    if ext:
        agency = await sysdb.agencies.find_one(
            {"tenant_id": tenant_id, "external_agency_id": ext}, {"_id": 0}
        )
    if not agency:
        import re as _re
        rx = {"$regex": f"^{_re.escape(req.get('agency_name', ''))}$", "$options": "i"}
        agency = await sysdb.agencies.find_one(
            {"tenant_id": tenant_id, "name": rx}, {"_id": 0}
        )
    if agency:
        return agency
    agency = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "name": req.get("agency_name", ""),
        "contact_name": req.get("contact_name", ""),
        "contact_email": req.get("contact_email", ""),
        "contact_phone": req.get("contact_phone", ""),
        "commission_rate": 0,
        "notes": "B2B connect (oto-saglama)",
        "status": "active",
        "published_content": False,
        "published_at": None,
        "external_agency_id": ext or None,
        "source": "b2b_connect",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await sysdb.agencies.insert_one(agency)
    agency.pop("_id", None)
    return agency


@router.post("/connect-requests/{request_id}/approve")
async def approve_connect_request(
    request_id: str,
    payload: ApproveIn | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op(_OP)),
):
    """Approve a pending request: match/create the agency, mint a least-privilege
    API key, and attach it for one-time delivery to the agency app."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    sysdb = get_system_db()
    body = payload or ApproveIn()

    # Atomic claim: flip pending→approving so two concurrent approvals can never
    # both mint a key for the SAME request. Only the claim winner proceeds; the
    # loser observes a non-pending status below.
    req = await sysdb.b2b_connection_requests.find_one_and_update(
        {"id": request_id, "tenant_id": tenant_id, "status": "pending"},
        {"$set": {"status": "approving", "approving_by": current_user.id,
                  "approving_at": _now_iso()}},
        return_document=ReturnDocument.AFTER,
    )
    if not req:
        existing = await sysdb.b2b_connection_requests.find_one(
            {"id": request_id, "tenant_id": tenant_id},
            {"_id": 0, "status": 1, "agency_id": 1, "key_prefix": 1},
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Istek bulunamadi")
        st = existing.get("status")
        if st == "approved":
            return {"ok": True, "status": "approved", "already": True,
                    "agency_id": existing.get("agency_id"),
                    "key_prefix": existing.get("key_prefix"),
                    "message": "Istek zaten onaylanmis."}
        if st == "rejected":
            raise HTTPException(status_code=409, detail="Reddedilmis istek onaylanamaz")
        if st == "approving":
            raise HTTPException(status_code=409, detail="Istek su anda isleniyor")
        raise HTTPException(status_code=409, detail="Istek onaylanamaz")

    # From here we hold the claim; any failure must release it back to pending so a
    # corrected retry can proceed.
    try:
        scopes = _resolve_scopes(body.scopes, req.get("requested_scopes"))
        agency = await _match_or_create_agency(sysdb, tenant_id, req, current_user.id)

        existing_key = await sysdb.agency_api_keys.find_one(
            {"tenant_id": tenant_id, "agency_id": agency["id"], "is_active": True},
            {"_id": 0, "key_prefix": 1},
        )

        now = _now()
        base_set = {
            "status": "approved",
            "approved_by": current_user.id,
            "approved_at": _now_iso(),
            "agency_id": agency["id"],
            "updated_at": _now_iso(),
        }

        if existing_key and not body.regenerate_if_exists:
            # Don't mint a second key; the existing one's raw value is unrecoverable.
            await sysdb.b2b_connection_requests.update_one(
                {"id": request_id, "tenant_id": tenant_id},
                {"$set": {**base_set, "delivery_state": "existing_key_not_retrievable",
                          "key_prefix": existing_key.get("key_prefix")}},
            )
            return {"ok": True, "status": "approved",
                    "agency_id": agency["id"], "key_minted": False,
                    "reason": "connected_existing_key_not_retrievable",
                    "message": "Onaylandi. Bu acentede zaten aktif key var; yeni key uretmek icin 'yenile' secenegini kullanin."}

        if existing_key and body.regenerate_if_exists:
            await sysdb.agency_api_keys.update_many(
                {"tenant_id": tenant_id, "agency_id": agency["id"], "is_active": True},
                {"$set": {"is_active": False, "revoked_at": _now_iso(),
                          "revoked_by": current_user.id}},
            )

        # NARROW DuplicateKeyError scope to the mint insert ONLY: the
        # (tenant_id, agency_id) is_active partial-unique index trips when a
        # concurrent approval already minted the active key for THIS agency.
        # Connect (no second key) instead of failing. base_set + agency are
        # guaranteed defined here, so this branch can never NameError. Any OTHER
        # DuplicateKeyError (e.g. a future agency unique index) propagates to the
        # outer `except Exception`, which deterministically releases the claim.
        try:
            raw_key, key_doc = await mint_agency_api_key(
                sysdb, tenant_id, agency, scopes, current_user.id
            )
        except DuplicateKeyError:
            ex = await sysdb.agency_api_keys.find_one(
                {"tenant_id": tenant_id, "agency_id": agency["id"], "is_active": True},
                {"_id": 0, "key_prefix": 1},
            )
            await sysdb.b2b_connection_requests.update_one(
                {"id": request_id, "tenant_id": tenant_id},
                {"$set": {**base_set, "delivery_state": "existing_key_not_retrievable",
                          "key_prefix": (ex or {}).get("key_prefix")}},
            )
            return {"ok": True, "status": "approved", "agency_id": agency["id"],
                    "key_minted": False, "reason": "connected_existing_key_not_retrievable",
                    "key_prefix": (ex or {}).get("key_prefix"),
                    "message": "Onaylandi. Bu acentede zaten aktif key var; yeni key uretmek icin 'yenile' secenegini kullanin."}

        await sysdb.b2b_connection_requests.update_one(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": {
                **base_set,
                "scopes": scopes,
                "encrypted_api_key": encrypt_delivery_key(raw_key),
                "key_prefix": key_doc["key_prefix"],
                "key_delivery_expires_at": now + timedelta(hours=KEY_DELIVERY_TTL_HOURS),
                "api_key_consumed_at": None,
                "delivery_state": "pending_retrieval",
            }},
        )
    except HTTPException:
        await _release_approving_claim(sysdb, tenant_id, request_id)
        raise
    except Exception:
        await _release_approving_claim(sysdb, tenant_id, request_id)
        logger.exception("B2B approve failed tenant=%s request=%s", tenant_id, request_id)
        raise HTTPException(status_code=500, detail="Onay islemi basarisiz")

    logger.info("B2B connect request approved tenant=%s agency=%s", tenant_id, agency["id"])
    return {"ok": True, "status": "approved", "agency_id": agency["id"],
            "key_minted": True, "key_prefix": key_doc["key_prefix"], "scopes": scopes,
            "message": "Onaylandi; API key acente uygulamasina poll ile teslim edilecek."}


@router.post("/connect-requests/{request_id}/reject")
async def reject_connect_request(
    request_id: str,
    payload: RejectIn | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op(_OP)),
):
    """Reject a pending request."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    sysdb = get_system_db()
    body = payload or RejectIn()

    result = await sysdb.b2b_connection_requests.update_one(
        {"id": request_id, "tenant_id": tenant_id, "status": "pending"},
        {"$set": {"status": "rejected", "rejected_by": current_user.id,
                  "rejected_at": _now_iso(), "reject_reason": body.reason.strip(),
                  "updated_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bekleyen istek bulunamadi")
    return {"ok": True, "status": "rejected"}
