"""Mailing module — Phase 1.

Endpoints to manage email templates, recipients (guests with email),
campaigns, and per-tenant credits. Sending uses the shared `core.email`
helper (Resend). The hotelier's own email is set as Reply-To so guest
replies go straight to them; the visible "From" remains the verified
Syroce domain for deliverability.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.email import send_email
from core.security import get_current_user
from models.schemas import User
from security.encrypted_lookup import decrypt_user_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mailing", tags=["mailing"])

DEFAULT_FREE_CREDITS = 100
RECIPIENT_FETCH_LIMIT = 1000
SEND_BATCH_LIMIT = 500  # max recipients per single campaign send


def _db():
    from server import db  # late import to avoid circulars
    return db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Schemas ─────────────────────────────────────────────────────────────
class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    subject: str = Field(..., min_length=1, max_length=200)
    html: str = Field(..., min_length=1)
    description: Optional[str] = None


class TemplateOut(TemplateIn):
    id: str
    tenant_id: str
    created_at: str
    updated_at: str


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    template_id: Optional[str] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    recipient_ids: list[str] = Field(default_factory=list)
    test_email: Optional[str] = None  # if set, sends only to this address (1 credit)


# ── Credit helpers ──────────────────────────────────────────────────────
async def _get_or_init_credits(tenant_id: str) -> dict:
    db = _db()
    doc = await db.mailing_credits.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc:
        return doc
    doc = {
        "tenant_id": tenant_id,
        "balance": DEFAULT_FREE_CREDITS,
        "lifetime_used": 0,
        "lifetime_purchased": 0,
        "free_granted": DEFAULT_FREE_CREDITS,
        "updated_at": _now_iso(),
    }
    await db.mailing_credits.insert_one({**doc})
    return doc


async def _consume_credits(tenant_id: str, n: int) -> int:
    """Atomically deduct `n` credits. Returns new balance.
    Raises HTTPException(402) if insufficient.
    """
    db = _db()
    await _get_or_init_credits(tenant_id)
    res = await db.mailing_credits.find_one_and_update(
        {"tenant_id": tenant_id, "balance": {"$gte": n}},
        {"$inc": {"balance": -n, "lifetime_used": n}, "$set": {"updated_at": _now_iso()}},
        return_document=True,
    )
    if not res:
        cur = await db.mailing_credits.find_one({"tenant_id": tenant_id}, {"balance": 1, "_id": 0})
        bal = (cur or {}).get("balance", 0)
        raise HTTPException(
            status_code=402,
            detail=f"Yetersiz mailing kredisi. Gerekli: {n}, Mevcut: {bal}. Lütfen paket yükseltin.",
        )
    return res.get("balance", 0)


# ── Credits endpoints ──────────────────────────────────────────────────
@router.get("/credits")
async def get_credits(current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    doc = await _get_or_init_credits(current_user.tenant_id)
    db = _db()
    sent_30d = await db.mailing_sends.count_documents({
        "tenant_id": current_user.tenant_id,
        "sent_at": {"$gte": (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()[:10]},
    })
    return {
        "balance": doc.get("balance", 0),
        "lifetime_used": doc.get("lifetime_used", 0),
        "free_granted": doc.get("free_granted", DEFAULT_FREE_CREDITS),
        "sent_today": sent_30d,
    }


# ── Templates ──────────────────────────────────────────────────────────
@router.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)) -> list[dict]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    cursor = _db().mailing_templates.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("updated_at", -1).limit(200)
    return await cursor.to_list(200)


@router.post("/templates")
async def create_template(payload: TemplateIn, current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **payload.model_dump(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await _db().mailing_templates.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    payload: TemplateIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    res = await _db().mailing_templates.find_one_and_update(
        {"id": template_id, "tenant_id": current_user.tenant_id},
        {"$set": {**payload.model_dump(), "updated_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return res


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    res = await _db().mailing_templates.delete_one(
        {"id": template_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return {"success": True}


# ── Recipients (guests with email) ──────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _extract_guest_email(g: dict) -> Optional[str]:
    """Try to surface a usable email from a (possibly encrypted) guest doc."""
    raw = g.get("email")
    if isinstance(raw, str) and _EMAIL_RE.match(raw):
        return raw.strip().lower()
    try:
        dec = decrypt_user_doc({**g})
        e = dec.get("email")
        if isinstance(e, str) and _EMAIL_RE.match(e):
            return e.strip().lower()
    except Exception:
        return None
    return None


def _guest_display_name(g: dict) -> str:
    if g.get("name"):
        return str(g["name"])
    fn = g.get("first_name") or ""
    ln = g.get("last_name") or ""
    full = f"{fn} {ln}".strip()
    return full or "Misafir"


@router.get("/recipients")
async def list_recipients(
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return guests of this tenant who have a valid email."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    query: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if search:
        rgx = re.escape(search.strip())
        query["$or"] = [
            {"name": {"$regex": rgx, "$options": "i"}},
            {"first_name": {"$regex": rgx, "$options": "i"}},
            {"last_name": {"$regex": rgx, "$options": "i"}},
        ]
    cursor = _db().guests.find(query, {"_id": 0}).sort("created_at", -1).limit(RECIPIENT_FETCH_LIMIT)
    out: list[dict] = []
    async for g in cursor:
        email = _extract_guest_email(g)
        if not email:
            continue
        out.append({
            "id": g.get("id") or g.get("guest_id") or email,
            "name": _guest_display_name(g),
            "email": email,
        })
    return out


# ── Campaigns ──────────────────────────────────────────────────────────
@router.get("/campaigns")
async def list_campaigns(current_user: User = Depends(get_current_user)) -> list[dict]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    cursor = _db().mailing_campaigns.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).limit(200)
    return await cursor.to_list(200)


def _resolve_campaign_content(payload: CampaignCreate, template: Optional[dict]) -> tuple[str, str]:
    subject = (payload.subject or (template or {}).get("subject") or "").strip()
    html = (payload.html or (template or {}).get("html") or "").strip()
    if not subject or not html:
        raise HTTPException(status_code=400, detail="Konu ve içerik zorunlu")
    return subject, html


def _personalize(html: str, subject: str, recipient_name: str, hotel_name: str) -> tuple[str, str]:
    repl = {
        "{{name}}": recipient_name,
        "{{hotel}}": hotel_name,
        "{{misafir}}": recipient_name,
        "{{otel}}": hotel_name,
    }
    for k, v in repl.items():
        html = html.replace(k, v)
        subject = subject.replace(k, v)
    return subject, html


@router.post("/campaigns")
async def create_and_send_campaign(
    payload: CampaignCreate,
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant bulunamadı")

    template = None
    if payload.template_id:
        template = await db.mailing_templates.find_one(
            {"id": payload.template_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    subject, html = _resolve_campaign_content(payload, template)

    # ── Build recipient list ────────────────────────────────────────
    recipients: list[dict] = []
    if payload.test_email:
        if not _EMAIL_RE.match(payload.test_email):
            raise HTTPException(status_code=400, detail="Geçersiz test e-posta")
        recipients = [{"id": "test", "name": "Test", "email": payload.test_email.lower()}]
    else:
        if not payload.recipient_ids:
            raise HTTPException(status_code=400, detail="En az 1 alıcı seçin")
        all_recipients = await list_recipients(current_user=current_user)
        wanted = set(payload.recipient_ids)
        recipients = [r for r in all_recipients if r["id"] in wanted]
        if not recipients:
            raise HTTPException(status_code=400, detail="Seçili alıcılar bulunamadı veya e-postaları yok")

    if len(recipients) > SEND_BATCH_LIMIT:
        raise HTTPException(status_code=400, detail=f"Tek seferde en fazla {SEND_BATCH_LIMIT} alıcı")

    # ── Reserve credits up-front ────────────────────────────────────
    await _consume_credits(current_user.tenant_id, len(recipients))

    # ── Persist campaign as queued ──────────────────────────────────
    campaign_id = str(uuid.uuid4())
    hotel_name = tenant.get("property_name") or tenant.get("name") or "Otel"
    reply_to = tenant.get("email") or None
    campaign_doc = {
        "id": campaign_id,
        "tenant_id": current_user.tenant_id,
        "name": payload.name,
        "subject": subject,
        "template_id": payload.template_id,
        "recipient_count": len(recipients),
        "status": "sending",
        "sent_count": 0,
        "failed_count": 0,
        "created_by": current_user.id,
        "created_at": _now_iso(),
        "is_test": bool(payload.test_email),
    }
    await db.mailing_campaigns.insert_one({**campaign_doc})

    # ── Send synchronously (Phase 1: small batches only) ────────────
    sent = 0
    failed = 0
    for r in recipients:
        psubj, phtml = _personalize(html, subject, r["name"], hotel_name)
        result = await send_email(
            to=r["email"], subject=psubj, html=phtml, reply_to=reply_to
        )
        ok = bool(result.get("sent"))
        if ok:
            sent += 1
        else:
            failed += 1
        await db.mailing_sends.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "campaign_id": campaign_id,
            "recipient_email": r["email"],
            "recipient_id": r["id"],
            "status": "sent" if ok else "failed",
            "provider_id": result.get("id"),
            "error": result.get("error"),
            "sent_at": _now_iso(),
        })

    # ── Refund failed sends ─────────────────────────────────────────
    if failed:
        await db.mailing_credits.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$inc": {"balance": failed, "lifetime_used": -failed}, "$set": {"updated_at": _now_iso()}},
        )

    await db.mailing_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": "completed",
            "sent_count": sent,
            "failed_count": failed,
            "completed_at": _now_iso(),
        }},
    )

    return {
        "campaign_id": campaign_id,
        "recipient_count": len(recipients),
        "sent_count": sent,
        "failed_count": failed,
    }
