"""
Integration Credentials Admin

Super-admin only endpoints for managing 3rd-party API keys/tokens (OpenAI,
Gemini, Resend, Sentry, AWS, Quick-ID service key, etc.).

Design:
  • Values are encrypted at rest via core.crypto.service
  • On save, os.environ is also updated immediately (no restart needed)
  • On startup, load_credentials_to_env() hydrates os.environ from DB so
    that existing os.getenv(...) call-sites throughout the codebase pick
    up stored values automatically without any additional code

Credentials are organized in CREDENTIAL_DEFINITIONS which serves as the
single source of truth both for the UI and for the startup loader.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.crypto import get_crypto_service
from core.database import db
from core.helpers import require_super_admin_guard
from core.security import get_current_user
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

require_super_admin = require_super_admin_guard()

router = APIRouter(
    prefix="/api/admin/integration-credentials",
    tags=["Integration Credentials"],
    dependencies=[Depends(require_super_admin)],
)

COLLECTION = "integration_credentials"


# ── Credential Catalog ───────────────────────────────────────────────
# key must match the exact os.environ variable used in the codebase.
CREDENTIAL_DEFINITIONS: list[dict[str, Any]] = [
    # --- AI & LLM ---
    {"key": "OPENAI_API_KEY", "name": "OpenAI API Key", "category": "ai",
     "description": "ChatGPT / GPT-4 entegrasyonu için (sk-... ile başlar).",
     "doc_url": "https://platform.openai.com/api-keys"},
    {"key": "GEMINI_API_KEY", "name": "Google Gemini API Key", "category": "ai",
     "description": "Google Gemini modelleri için.",
     "doc_url": "https://aistudio.google.com/apikey"},
    {"key": "ANTHROPIC_API_KEY", "name": "Anthropic Claude API Key", "category": "ai",
     "description": "Claude modelleri için (opsiyonel fallback).",
     "doc_url": "https://console.anthropic.com/settings/keys"},

    # --- Email ---
    {"key": "RESEND_API_KEY", "name": "Resend API Key", "category": "email",
     "description": "Email gönderimi (şifre sıfırlama, bildirimler).",
     "doc_url": "https://resend.com/api-keys"},
    {"key": "MAIL_PROVIDER", "name": "Mail Provider", "category": "email",
     "description": "Aktif mail sağlayıcı: 'resend' veya 'smtp'.",
     "doc_url": ""},

    # --- Monitoring & Observability ---
    {"key": "SENTRY_DSN", "name": "Sentry DSN", "category": "monitoring",
     "description": "Hata izleme için Sentry DSN URL'i.",
     "doc_url": "https://sentry.io/settings/projects/"},
    {"key": "ALERT_WEBHOOK_URL", "name": "Alert Webhook URL", "category": "monitoring",
     "description": "Uyarı webhook endpoint'i (Slack/Discord/Generic).",
     "doc_url": ""},
    {"key": "OPS_WEBHOOK_URL", "name": "Ops Webhook URL", "category": "monitoring",
     "description": "Operasyonel olayların webhook endpoint'i.",
     "doc_url": ""},

    # --- Infrastructure ---
    {"key": "MONGO_ATLAS_URI", "name": "MongoDB Atlas URI", "category": "infrastructure",
     "description": "Prod MongoDB bağlantı string'i (mongodb+srv://...).",
     "doc_url": "https://www.mongodb.com/cloud/atlas"},

    # --- Integrations ---
    {"key": "QUICKID_SERVICE_KEY", "name": "Quick-ID Service Key", "category": "integrations",
     "description": "Quick-ID servisine servis-arası kimlik doğrulama anahtarı.",
     "doc_url": ""},
    {"key": "MARKETPLACE_ADMIN_TOKEN", "name": "Marketplace Admin Token", "category": "integrations",
     "description": "B2B marketplace yönetim token'ı.",
     "doc_url": ""},
    {"key": "AFSADAKAT_ADMIN_TOKEN", "name": "AF Sadakat Admin Token", "category": "integrations",
     "description": "AF Sadakat programı yönetim token'ı.",
     "doc_url": ""},
    {"key": "AFSADAKAT_SSO_SECRET", "name": "AF Sadakat SSO Secret", "category": "integrations",
     "description": "AF Sadakat tek oturum açma secret'ı.",
     "doc_url": ""},

    # --- AWS / KMS ---
    {"key": "AWS_ACCESS_KEY_ID", "name": "AWS Access Key ID", "category": "aws",
     "description": "AWS IAM access key (S3, KMS için).",
     "doc_url": "https://console.aws.amazon.com/iam/home#/security_credentials"},
    {"key": "AWS_SECRET_ACCESS_KEY", "name": "AWS Secret Access Key", "category": "aws",
     "description": "AWS IAM secret access key.",
     "doc_url": "https://console.aws.amazon.com/iam/home#/security_credentials"},
    {"key": "AWS_KMS_KEY_ARN", "name": "AWS KMS Key ARN", "category": "aws",
     "description": "Şifreleme için kullanılan KMS key ARN.",
     "doc_url": ""},
    {"key": "AWS_REGION", "name": "AWS Region", "category": "aws",
     "description": "AWS bölgesi (örn. eu-central-1).",
     "doc_url": ""},
]

_KEYS_BY_NAME: dict[str, dict[str, Any]] = {c["key"]: c for c in CREDENTIAL_DEFINITIONS}


# ── Pydantic models ──────────────────────────────────────────────────

class CredentialUpsert(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1)


class CredentialStatus(BaseModel):
    key: str
    name: str
    category: str
    description: str
    doc_url: str
    is_set: bool
    masked_value: str | None = None
    source: str  # "db" | "env" | "none"
    updated_at: str | None = None
    updated_by: str | None = None


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return value[:3] + "•" * (len(value) - 6) + value[-3:]


async def _load_db_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    async for doc in db[COLLECTION].find({}, {"_id": 0}):
        records[doc["key"]] = doc
    return records


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/catalog")
async def list_catalog():
    """List every known credential slot with current is_set status."""
    db_records = await _load_db_records()
    items: list[CredentialStatus] = []
    for defn in CREDENTIAL_DEFINITIONS:
        key = defn["key"]
        rec = db_records.get(key)
        env_val = os.environ.get(key)
        db_plain = ""
        if rec and rec.get("value_encrypted"):
            try:
                db_plain = get_crypto_service().decrypt(rec["value_encrypted"])
            except Exception:
                db_plain = ""

        # Precedence for display: what is actually ACTIVE in os.environ right now?
        # Startup hydration rule = "pre-existing env wins over DB". So if env_val exists
        # and differs from db_plain, the active source is env.
        if env_val and (not db_plain or env_val != db_plain):
            items.append(CredentialStatus(
                key=key, name=defn["name"], category=defn["category"],
                description=defn["description"], doc_url=defn.get("doc_url", ""),
                is_set=True, masked_value=_mask(env_val), source="env",
                updated_at=rec.get("updated_at") if rec else None,
                updated_by=rec.get("updated_by") if rec else None,
            ))
        elif db_plain:
            items.append(CredentialStatus(
                key=key, name=defn["name"], category=defn["category"],
                description=defn["description"], doc_url=defn.get("doc_url", ""),
                is_set=True, masked_value=_mask(db_plain), source="db",
                updated_at=rec.get("updated_at"),
                updated_by=rec.get("updated_by"),
            ))
        else:
            items.append(CredentialStatus(
                key=key, name=defn["name"], category=defn["category"],
                description=defn["description"], doc_url=defn.get("doc_url", ""),
                is_set=False, source="none",
            ))
    return {"items": [i.model_dump() for i in items], "count": len(items)}


@router.post("/upsert")
async def upsert_credential(payload: CredentialUpsert, current_user=Depends(get_current_user)):
    if payload.key not in _KEYS_BY_NAME:
        raise HTTPException(status_code=400, detail=f"Unknown credential key: {payload.key}")
    value = payload.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value cannot be empty")

    try:
        encrypted = get_crypto_service().encrypt(value)
    except Exception as e:
        logger.exception("encryption failed for %s", payload.key)
        raise HTTPException(status_code=500, detail=f"Encryption failed: {e}") from e

    now = datetime.now(UTC).isoformat()
    updated_by = getattr(current_user, "email", None) or getattr(current_user, "username", None) or "super_admin"
    await db[COLLECTION].update_one(
        {"key": payload.key},
        {"$set": {
            "key": payload.key,
            "value_encrypted": encrypted,
            "updated_at": now,
            "updated_by": updated_by,
        }},
        upsert=True,
    )
    # Runtime inject — existing os.getenv(...) call-sites pick it up immediately
    os.environ[payload.key] = value
    logger.info("integration credential updated: key=%s by=%s", payload.key, updated_by)
    return {"ok": True, "key": payload.key, "masked_value": _mask(value), "updated_at": now}


@router.delete("/{key}")
async def delete_credential(key: str):
    if key not in _KEYS_BY_NAME:
        raise HTTPException(status_code=400, detail=f"Unknown credential key: {key}")
    result = await db[COLLECTION].delete_one({"key": key})
    # Only remove from os.environ when we actually deleted a DB-sourced value.
    # If the env var came from deployment secrets (no DB doc), leave it alone.
    if result.deleted_count > 0:
        os.environ.pop(key, None)
    return {"ok": True, "key": key, "deleted_count": result.deleted_count}


# ── Startup hook (called from server.py) ─────────────────────────────

async def load_credentials_to_env() -> int:
    """Hydrate os.environ from encrypted DB records at startup.

    Values already set in the environment take precedence (Replit Secrets
    wins over DB-saved values).
    """
    try:
        loaded = 0
        async for doc in db[COLLECTION].find({}, {"_id": 0, "key": 1, "value_encrypted": 1}):
            key = doc.get("key")
            enc = doc.get("value_encrypted")
            if not key or not enc:
                continue
            # Only hydrate keys present in the catalog — prevents arbitrary env
            # injection if non-catalog documents end up in the collection.
            if key not in _KEYS_BY_NAME:
                logger.warning("skipping non-catalog integration credential: %s", key)
                continue
            if key in os.environ and os.environ[key]:
                continue  # env has precedence
            try:
                os.environ[key] = get_crypto_service().decrypt(enc)
                loaded += 1
            except Exception:
                logger.warning("could not decrypt integration credential: %s", key)
        if loaded:
            logger.info("integration credentials loaded to env: %d", loaded)
        return loaded
    except Exception:
        logger.exception("integration credentials startup load failed")
        return 0
