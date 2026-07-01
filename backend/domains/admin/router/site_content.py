"""
site_content

Public landing-page content (GLOBAL singleton) — editable by super_admin.

  - GET  /api/site-content        (public)        → stored content or {}
  - PUT  /api/admin/site-content  (super_admin)   → upsert global content

Content is stored as a single document (``_id='global_landing'``) in the
``site_content`` collection. There is NO tenant scoping: the landing page is
served before any login, so it must be globally readable. Writes use the raw
system DB so STRICT_TENANT_MODE does not block the un-scoped upsert.

All string fields are PLAIN TEXT only (no HTML/markup): the frontend renders
them as text and the validator rejects any value containing angle brackets, so
stored content can never carry markup even if the React escape boundary moves.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, conlist, constr, field_validator

from core.helpers import require_super_admin_guard
from core.security import get_current_user
from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Admin / Operations"])
require_super_admin = require_super_admin_guard()

SITE_CONTENT_ID = "global_landing"
SITE_CONTENT_COLLECTION = "site_content"

# Only these fields are ever exposed on the PUBLIC GET. Internal/admin
# metadata (``_id``, ``updated_at``, ``updated_by``) must never leak to the
# unauthenticated landing endpoint (``updated_by`` can be an admin id/email).
_PUBLIC_FIELDS = ("brandName", "hero", "contact", "solutions", "faqs")


def _reject_html(value):
    """Reject any string containing markup characters (plain text only)."""
    if isinstance(value, str) and ("<" in value or ">" in value):
        raise ValueError("HTML/markup karakterleri (< >) kabul edilmez; yalnizca duz metin.")
    return value


class HeroContent(BaseModel):
    badge: constr(max_length=120) = ""
    titlePre: constr(max_length=80) = ""
    titleAccent: constr(max_length=80) = ""
    titlePost: constr(max_length=80) = ""
    description: constr(max_length=600) = ""
    descriptionAccent: constr(max_length=160) = ""

    @field_validator("*")
    @classmethod
    def _no_html(cls, v):
        return _reject_html(v)


class ContactContent(BaseModel):
    phone: constr(max_length=60) = ""
    email: constr(max_length=160) = ""
    address: constr(max_length=200) = ""

    @field_validator("*")
    @classmethod
    def _no_html(cls, v):
        return _reject_html(v)


class SolutionCard(BaseModel):
    title: constr(max_length=120) = ""
    desc: constr(max_length=400) = ""

    @field_validator("*")
    @classmethod
    def _no_html(cls, v):
        return _reject_html(v)


class FAQItem(BaseModel):
    q: constr(max_length=200) = ""
    a: constr(max_length=1000) = ""

    @field_validator("*")
    @classmethod
    def _no_html(cls, v):
        return _reject_html(v)


class SiteContent(BaseModel):
    brandName: constr(max_length=80) = ""
    hero: HeroContent = HeroContent()
    contact: ContactContent = ContactContent()
    solutions: conlist(SolutionCard, max_length=12) = []
    faqs: conlist(FAQItem, max_length=20) = []

    @field_validator("brandName")
    @classmethod
    def _no_html(cls, v):
        return _reject_html(v)


@router.get("/site-content")
async def get_site_content():
    """Public read of the global landing content. Always 200; ``{}`` when unset
    so the frontend overlays its built-in defaults (landing is never blank)."""
    try:
        sys_db = get_system_db()
        doc = await sys_db[SITE_CONTENT_COLLECTION].find_one({"_id": SITE_CONTENT_ID})
        if not doc:
            return {}
        # Allowlist: never expose _id / updated_at / updated_by (admin metadata/PII)
        return {k: doc[k] for k in _PUBLIC_FIELDS if k in doc}
    except Exception as exc:  # pragma: no cover - defensive, never break landing
        logger.warning("get_site_content failed, returning empty: %s", exc)
        return {}


@router.put("/admin/site-content")
async def update_site_content(
    payload: SiteContent,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_super_admin),
):
    """Upsert the global landing content. Super-admin only."""
    sys_db = get_system_db()
    content = payload.model_dump()
    now = datetime.now(UTC).isoformat()
    updated_by = None
    if isinstance(current_user, dict):
        updated_by = current_user.get("id") or current_user.get("email")
    else:
        updated_by = getattr(current_user, "id", None) or getattr(current_user, "email", None)

    stored = {**content, "updated_at": now, "updated_by": updated_by}
    await sys_db[SITE_CONTENT_COLLECTION].update_one(
        {"_id": SITE_CONTENT_ID},
        {"$set": stored, "$setOnInsert": {"_id": SITE_CONTENT_ID}},
        upsert=True,
    )
    return {**content, "updated_at": now}
