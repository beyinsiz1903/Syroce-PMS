"""Hosted agency onboarding. Invitations never grant API or hotel permissions."""
import hashlib
import html
import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from core.security import get_current_user, hash_password
from core.tenant_db import get_system_db
from models.schemas import User
from security.encrypted_lookup import build_user_email_query, decrypt_user_doc, encrypt_user_doc

router = APIRouter(prefix="/api/marketplace/v1", tags=["Agency onboarding"])
logger = logging.getLogger(__name__)


class InviteRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr


class AcceptRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=72)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class RecoverRequest(BaseModel):
    email: EmailStr


def recovery_scope():
    return {"is_active": {"$ne": False}, "agency_id": {"$exists": True, "$nin": [None, ""]},
            "onboarding_status": {"$ne": "invited"},
            "$or": [{"role": {"$in": ["marketplace_agent", "agency_admin", "agency_agent"]}},
                    {"roles": {"$in": ["marketplace_agent", "agency_admin", "agency_agent"]}}]}


async def send_recovery(email):
    from core.email import _frontend_base_url, send_email

    try:
        database = get_system_db()
        user = await database.users.find_one({"$and": [build_user_email_query(email), recovery_scope()]})
        if not user:
            return
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        result = await database.users.update_one({"id": user["id"], **recovery_scope()}, {"$set": {
            "agency_reset_hash": digest(token), "agency_reset_expires": now + timedelta(minutes=30),
        }})
        if not result.modified_count:
            return
        link = f"{_frontend_base_url().rstrip('/')}/agency-recover#token={token}"
        delivery = await send_email(email, "Syroce — Acente şifrenizi yenileyin",
                                   f'<p><a href="{html.escape(link, quote=True)}">Yeni şifre belirle</a></p>'
                                   '<p>Bağlantı 30 dakika geçerlidir ve tek kullanımlıktır. Talep size ait değilse yok sayın.</p>',
                                   sensitive=True)
        await audit(database, user['agency_id'], 'portal_recovery_requested', user_id=user['id'],
                    email_sent=bool(delivery.get('sent')))
    except Exception:
        logger.error("Agency recovery delivery failed")


@router.post("/extranet/auth/recover")
async def recover(data: RecoverRequest, request: Request, background_tasks: BackgroundTasks):
    from security.auth_throttle import FORGOT_PW_EMAIL, FORGOT_PW_IP, client_ip, enforce, normalize_identity

    email = str(data.email).strip().lower()
    await enforce(FORGOT_PW_IP, f"ip:{client_ip(request)}", "sıfırlama isteği")
    await enforce(FORGOT_PW_EMAIL, f"em:{normalize_identity(email)}", "sıfırlama isteği")
    # Lookup and delivery both happen after the identical public response.
    background_tasks.add_task(send_recovery, email)
    return {"ok": True, "message": "Uygun bir acente hesabı varsa şifre yenileme bağlantısı gönderilecektir. Gelen kutunuzu ve spam klasörünü kontrol edin."}


@router.post("/extranet/auth/reset")
async def reset(data: AcceptRequest, request: Request):
    from core.security import invalidate_user_doc_cache
    from security.auth_throttle import RESET_TOKEN_IP, client_ip, enforce
    from security.credential_guard import CredentialGuard

    await enforce(RESET_TOKEN_IP, f"ip:{client_ip(request)}", "şifre yenileme")
    if len(data.password.encode()) > 72 or not CredentialGuard.validate_password_strength(data.password)["is_strong"]:
        raise HTTPException(422, "Şifre en az 12 karakter, büyük/küçük harf ve rakam içermeli; en fazla 72 bayt olmalıdır")
    database = get_system_db()
    now = datetime.now(UTC)
    query = {**recovery_scope(), "agency_reset_hash": digest(data.token), "agency_reset_expires": {"$gt": now}}
    user = await database.users.find_one(query)
    if not user:
        raise HTTPException(400, "Bağlantı geçersiz, kullanılmış veya süresi dolmuş. Yeni bağlantı isteyin.")
    result = await database.users.update_one({**query, "id": user['id']}, {
        "$set": {"hashed_password": hash_password(data.password), "password_reset_at": now.isoformat(),
                 "tokens_invalid_before": now.timestamp(), "requires_password_change": False},
        "$unset": {"agency_reset_hash": "", "agency_reset_expires": ""},
    })
    if not result.modified_count:
        raise HTTPException(400, "Bağlantı kullanılmış veya yenilenmiş. Yeni bağlantı isteyin.")
    invalidate_user_doc_cache(user['id'])
    await audit(database, user['agency_id'], 'portal_password_reset', user_id=user['id'])
    return {"ok": True, "login_path": "/acente-girisi"}


async def audit(database, agency_id, action, **details):
    # An audit outage must not turn successful activation into an apparent failure.
    try:
        await database.marketplace_audit_logs.insert_one({
            "id": str(uuid.uuid4()), "agency_id": agency_id, "action": action,
            "details": details, "created_at": datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.error("Agency onboarding audit write failed action=%s", action)


@router.post("/admin/agencies/{agency_id}/invitations")
async def invite(agency_id: str, data: InviteRequest, current_user: User = Depends(get_current_user)):
    from core.email import _frontend_base_url, send_email
    from core.security import _is_super_admin

    if not _is_super_admin(current_user) or getattr(current_user, "is_impersonating", False):
        raise HTTPException(403, "Yalnızca ana süperadmin acente kullanıcısı davet edebilir")
    database = get_system_db()
    agency = await database.marketplace_agencies.find_one({"id": agency_id, "status": "active"})
    if not agency:
        raise HTTPException(404, "Aktif acente bulunamadı")
    email = str(data.email).strip().lower()
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Ad soyad en az iki karakter olmalıdır")
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    token_hash = digest(token)
    fields = {
        "agency_invite_hash": token_hash, "agency_invite_expires": now + timedelta(hours=24),
        "agency_invite_sent_at": now, "agency_invite_delivery": "pending",
    }
    existing = await database.users.find_one(build_user_email_query(email))
    if existing:
        # Never repurpose a hotel employee, another agency's user or an activated account.
        if (existing.get("agency_id") != agency_id or existing.get("role") != "marketplace_agent"
                or existing.get("onboarding_status") != "invited"):
            raise HTTPException(409, "Bu e-posta mevcut bir hesaba ait; hesap yetkileri değiştirilmedi")
        updated = await database.users.update_one({
            "id": existing["id"], "agency_id": agency_id, "onboarding_status": "invited",
            "$or": [{"agency_invite_sent_at": {"$lte": now - timedelta(minutes=1)}},
                    {"agency_invite_sent_at": {"$exists": False}}],
        }, {"$set": fields})
        if not updated.modified_count:
            raise HTTPException(409, "Davet yenilenemedi; bir dakika bekleyin ve durumu yenileyin")
        user_id = existing["id"]
    else:
        user_id = str(uuid.uuid4())
        document = encrypt_user_doc({
            "id": user_id, "user_id": user_id, "tenant_id": None, "agency_id": agency_id,
            "name": name, "email": email, "role": "marketplace_agent", "roles": ["marketplace_agent"],
            "hashed_password": hash_password(secrets.token_urlsafe(32)),
            "is_active": False, "email_verified": False, "onboarding_status": "invited",
            "created_at": now.isoformat(), "created_by": current_user.id, **fields,
        })
        try:
            await database.users.insert_one(document)
        except DuplicateKeyError:
            raise HTTPException(409, "Bu e-posta için hesap zaten oluşturulmuş; durumu yenileyin") from None
    # Fragment prevents the invitation secret from entering HTTP access/referrer logs.
    link = f"{_frontend_base_url().rstrip('/')}/agency-activate#token={token}"
    try:
        result = await send_email(email, "Syroce — Acente hesabınızı etkinleştirin", (
            f"<p>Merhaba {html.escape(name)},</p><p>{html.escape(agency['name'])} acente hesabına davet edildiniz.</p>"
            f'<p><a href="{html.escape(link, quote=True)}">Kendi şifremi belirle</a></p>'
            "<p>Bağlantı 24 saat geçerlidir ve yalnız bir kez kullanılabilir. Yeni davet eski bağlantıyı geçersiz kılar.</p>"
        ), sensitive=True)
        sent = bool(result.get("sent"))
    except Exception:
        sent = False
    try:
        await database.users.update_one({"id": user_id, "agency_invite_hash": token_hash}, {
            "$set": {"agency_invite_delivery": "sent" if sent else "failed"},
        })
    except Exception:
        logger.error("Agency invitation delivery status write failed")
    await audit(database, agency_id, "portal_invitation_issued", actor_id=current_user.id, user_id=user_id, email_sent=sent)
    return {"user_id": user_id, "email_sent": sent, "expires_at": fields["agency_invite_expires"].isoformat(),
            "message": "Davet e-posta sağlayıcısına iletildi" if sent else "Hesap davet bekliyor; e-posta gönderilemedi. Yeniden davet edin."}


@router.post("/extranet/invitations/accept")
async def accept(data: AcceptRequest):
    from security.credential_guard import CredentialGuard

    if len(data.password.encode()) > 72 or not CredentialGuard.validate_password_strength(data.password)["is_strong"]:
        raise HTTPException(422, "Şifre en az 12 karakter, büyük/küçük harf ve rakam içermeli; en fazla 72 bayt olmalıdır")
    database = get_system_db()
    query = {"agency_invite_hash": digest(data.token), "agency_invite_expires": {"$gt": datetime.now(UTC)},
             "onboarding_status": "invited", "role": "marketplace_agent", "is_active": False}
    user = await database.users.find_one(query)
    if not user:
        raise HTTPException(400, "Davet geçersiz, kullanılmış veya süresi dolmuş. Yeni davet isteyin.")
    if not await database.marketplace_agencies.find_one({"id": user["agency_id"], "status": "active"}):
        raise HTTPException(403, "Acente aktif değil; yöneticinizle iletişime geçin")
    # One atomic compare-and-set consumes the token and installs the password.
    result = await database.users.update_one({**query, "id": user["id"]}, {
        "$set": {"hashed_password": hash_password(data.password), "is_active": True,
                 "email_verified": True, "onboarding_status": "active",
                 "activated_at": datetime.now(UTC).isoformat()},
        "$unset": {"agency_invite_hash": "", "agency_invite_expires": ""},
    })
    if not result.modified_count:
        raise HTTPException(400, "Davet daha önce kullanılmış veya yenilenmiş. Yeni davet isteyin.")
    await audit(database, user["agency_id"], "portal_invitation_accepted", user_id=user["id"])
    return {"ok": True, "login_path": "/acente-girisi"}


@router.get("/admin/agencies/{agency_id}/readiness")
async def readiness(agency_id: str, check_in: date = Query(...), check_out: date = Query(...),
                    current_user: User = Depends(get_current_user)):
    from core.security import _is_super_admin
    from routers.marketplace_b2b import MarketplaceSearchRequest, agency_search

    if not _is_super_admin(current_user) or getattr(current_user, "is_impersonating", False):
        raise HTTPException(403, "Yalnızca ana süperadmin erişebilir")
    if check_in < datetime.now(UTC).date() or not 0 < (check_out - check_in).days <= 31:
        raise HTTPException(422, "Bugün veya sonrası için 1–31 gecelik tarih aralığı seçin")
    database = get_system_db()
    agency = await database.marketplace_agencies.find_one({"id": agency_id})
    if not agency:
        raise HTTPException(404, "Acente bulunamadı")
    users = await database.users.find({"agency_id": agency_id, "role": "marketplace_agent"}, {
        "_id": 0, "id": 1, "is_active": 1, "onboarding_status": 1,
        "agency_invite_expires": 1, "agency_invite_delivery": 1, "email": 1,
    }).to_list(1000)
    now = datetime.now(UTC)
    invitations = []
    for user in users:
        if user.get("onboarding_status") == "invited":
            expiry = user.get("agency_invite_expires")
            if expiry and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            invitations.append({"user_id": user["id"], "email": decrypt_user_doc(user).get("email", ""), "delivery": user.get("agency_invite_delivery", "unknown"),
                                "expired": not expiry or expiry <= now})
    active_users = sum(user.get("is_active") is not False and user.get("onboarding_status") != "invited" for user in users)
    contract_count = await database.agency_contracts.count_documents({
        "agency_id": agency_id, "status": "approved", "valid_from": {"$lte": check_in.isoformat()},
        "valid_to": {"$gte": (check_out - timedelta(days=1)).isoformat()},
    })
    offers, check_error = [], False
    if agency.get("status") == "active" and contract_count:
        try:
            result = await agency_search(MarketplaceSearchRequest(
                check_in=check_in.isoformat(), check_out=check_out.isoformat(), adults=2, children=0, limit=200,
            ), {"agency_id": agency_id, "agency_name": agency["name"]})
            for hotel in result["results"]:
                for room in hotel["available_room_types"]:
                    if (room.get("total_price", 0) > 0 and room.get("available_rooms", 0) > 0
                            and await verified_offer(agency_id, hotel["tenant_id"], room["room_type"], check_in, check_out)):
                        offers.append({"tenant_id": hotel["tenant_id"], "hotel_name": hotel["hotel_name"],
                                       "room_type": room["room_type"], "total_price": room["total_price"],
                                       "currency": room["currency"], "available_rooms": room["available_rooms"]})
        except Exception:
            logger.warning("Agency readiness sales check failed")
            check_error = True
    checks = {"agency_active": agency.get("status") == "active", "portal_user_active": active_users > 0,
              "contract_approved": contract_count > 0, "sellable_offer": bool(offers)}
    return {"ready": all(checks.values()) and not check_error, "checks": checks,
            "active_users": active_users, "invitations": invitations, "contract_count": contract_count,
            "offers": offers, "check_error": check_error, "checked_at": now.isoformat(),
            "check_in": check_in, "check_out": check_out,
            "scope": "Seçilen tarihlerde 2 yetişkin; her gece için açıkça paylaşılmış fiyat/kontenjan aranır. Anlık kontrol, kontenjan ayırmaz. En fazla 200 tesis taranır."}


async def verified_offer(agency_id, tenant_id, room_type, check_in, check_out):
    """Readiness is conservative: never certify fallback or ambiguous rate plans."""
    from core.tenant_db import tenant_context
    from routers.agency_contracts import has_active_contract
    from routers.marketplace_b2b import _get_listing_or_404, db

    try:
        await _get_listing_or_404(tenant_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return False
        raise
    contract = await has_active_contract(agency_id, tenant_id, on_date=check_in.isoformat(),
                                         through_date=(check_out - timedelta(days=1)).isoformat())
    if not contract or (contract.get("allowed_room_types") and room_type not in contract["allowed_room_types"]):
        return False
    nights = (check_out - check_in).days
    dates = [(check_in + timedelta(days=i)).isoformat() for i in range(nights)]
    with tenant_context(tenant_id):
        rows = await db.agency_rate_calendar.find({
            "tenant_id": tenant_id, "agency_id": agency_id, "room_type_code": room_type,
            "date": {"$in": dates},
        }, {"_id": 0}).to_list(nights * 8 + 1)
    for day in dates:
        matching = [row for row in rows if row.get("date") == day]
        if len(matching) != 1:
            return False
        row = matching[0]
        if (row.get("stop_sell") or float(row.get("rate") or 0) <= 0
                or int(row.get("availability") or 0) <= 0 or int(row.get("min_stay") or 1) > nights
                or (day == dates[0] and row.get("closed_to_arrival"))):
            return False
    return True
