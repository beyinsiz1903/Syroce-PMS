"""
Integrations Overview (Super-Admin)
====================================

Tek bakışta tüm 3. parti entegrasyonların durumunu döner:

  • ready              — kod tamam + tüm gerekli credential'lar mevcut
  • needs_credentials  — kod tamam, eksik API key/secret var
  • in_development     — kod henüz tamamlanmamış (UI gri pasif)

Her entegrasyon ayrı bir kalem olarak listelenir (Quick-ID, Sadakat,
CapX, WhatsApp, OpenAI, Gemini, Exely, HotelRunner, Resend, Sentry,
Iyzico, vb.) — owner bunları otellere ayrı modüller olarak atayıp
ayrı ayrı ücretlendirebilsin diye.

Credential mevcudiyeti kontrolü:
  • os.environ      — Replit Secrets / deployment env
  • integration_credentials koleksiyonu (DB'de şifreli saklanan)

Bir env eksiği DB'den ya da Secrets'tan girilince bir sonraki refresh'te
entegrasyon otomatik olarak `needs_credentials` → `ready` geçer.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends

from core.database import db
from core.helpers import require_super_admin_guard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/integrations-overview",
    tags=["Integrations Overview"],
    dependencies=[Depends(require_super_admin_guard())],
)


# ── Integration Catalog ──────────────────────────────────────────────
# Her entegrasyon için:
#   key             : stabil kimlik
#   name            : TR ekran adı
#   category        : ai | messaging | channel-manager | loyalty | b2b |
#                     monitoring | infrastructure | identity | payment
#   description     : kısa TR açıklama
#   required_envs   : zorunlu env key listesi (boşsa per-tenant DB'de)
#   per_tenant      : True ise credential'lar tenant başına DB'de tutulur
#                     (env kontrolü yapılmaz, kod hazır kabul edilir)
#   code_status     : "ready" | "in_development"
#   module_key      : entitlements modül anahtarı (otele atama için)
#   doc_url         : opsiyonel sağlayıcı dökümantasyon linki
#   pricing_note    : opsiyonel TR ücretlendirme notu (owner için ipucu)
INTEGRATIONS: list[dict[str, Any]] = [
    # ─── AI / LLM ───────────────────────────────────────────────
    {
        "key": "openai",
        "name": "OpenAI (ChatGPT / GPT-4)",
        "category": "ai",
        "description": "Akıllı upsell, misafir mesaj asistanı, dinamik fiyat önerisi.",
        "required_envs": ["OPENAI_API_KEY"],
        "code_status": "ready",
        "module_key": "ai_openai",
        "doc_url": "https://platform.openai.com/api-keys",
        "pricing_note": "Kullanım başına token ücretlendirmesi.",
    },
    {
        "key": "gemini",
        "name": "Google Gemini",
        "category": "ai",
        "description": "Alternatif LLM sağlayıcı (görsel + metin).",
        "required_envs": ["GEMINI_API_KEY"],
        "code_status": "ready",
        "module_key": "ai_gemini",
        "doc_url": "https://aistudio.google.com/apikey",
    },
    {
        "key": "anthropic",
        "name": "Anthropic Claude",
        "category": "ai",
        "description": "Fallback LLM (Claude 3.5).",
        "required_envs": ["ANTHROPIC_API_KEY"],
        "code_status": "ready",
        "module_key": "ai_anthropic",
        "doc_url": "https://console.anthropic.com/settings/keys",
    },

    # ─── Messaging ──────────────────────────────────────────────
    {
        "key": "whatsapp",
        "name": "WhatsApp Business (Meta)",
        "category": "messaging",
        "description": "Misafir bildirim, onay, template (HSM) gönderimi + inbound webhook.",
        "required_envs": [],  # tenant başına messaging_provider_configs
        "per_tenant": True,
        "code_status": "ready",
        "module_key": "messaging_whatsapp",
        "doc_url": "https://developers.facebook.com/docs/whatsapp",
        "pricing_note": "Meta WABA onayı + template başına ücret.",
    },
    {
        "key": "resend",
        "name": "Resend (E-posta)",
        "category": "messaging",
        "description": "Şifre sıfırlama, rezervasyon onay e-postaları.",
        "required_envs": ["RESEND_API_KEY"],
        "code_status": "ready",
        "module_key": "messaging_email",
        "doc_url": "https://resend.com/api-keys",
    },
    {
        "key": "smtp",
        "name": "SMTP (E-posta — alternatif)",
        "category": "messaging",
        "description": "Resend yerine kendi SMTP sunucunuz (per-tenant ayar).",
        "required_envs": [],
        "per_tenant": True,
        "code_status": "ready",
        "module_key": "messaging_email",
    },

    # ─── Channel Manager ────────────────────────────────────────
    {
        "key": "exely",
        "name": "Exely (Channel Manager)",
        "category": "channel-manager",
        "description": "OTA dağıtımı, rezervasyon webhook, rate push.",
        "required_envs": [],
        "per_tenant": True,
        "code_status": "ready",
        "module_key": "channel_exely",
        "pricing_note": "Per-otel lisans + IP whitelist gerekir.",
    },
    {
        "key": "hotelrunner",
        "name": "HotelRunner",
        "category": "channel-manager",
        "description": "Booking.com / Expedia köprüsü, rezervasyon pull.",
        "required_envs": [],
        "per_tenant": True,
        "code_status": "ready",
        "module_key": "channel_hotelrunner",
    },
    {
        "key": "sabre_synxis",
        "name": "Sabre SynXis (HTNG 2024B)",
        "category": "channel-manager",
        "description": "Sabre/SynXis CRS XML köprüsü — kurumsal zincirler için.",
        "required_envs": [],
        "per_tenant": True,
        "code_status": "in_development",
        "module_key": "channel_sabre",
    },

    # ─── Identity ───────────────────────────────────────────────
    {
        "key": "quickid",
        "name": "Quick-ID (Kimlik OCR)",
        "category": "identity",
        "description": "TC Kimlik / Pasaport tarama + KVKK uyumlu doğrulama.",
        "required_envs": ["QUICKID_SERVICE_KEY"],
        "code_status": "ready",
        "module_key": "quickid",
        "pricing_note": "Tarama başına ücret.",
    },

    # ─── Loyalty ────────────────────────────────────────────────
    {
        "key": "afsadakat",
        "name": "AF Sadakat (Loyalty)",
        "category": "loyalty",
        "description": "Misafir sadakat programı + SSO + puan/üye sync.",
        "required_envs": ["AFSADAKAT_BASE_URL", "AFSADAKAT_ADMIN_TOKEN", "AFSADAKAT_SSO_SECRET"],
        "code_status": "ready",
        "module_key": "loyalty_afsadakat",
        "pricing_note": "Aylık tenant lisansı.",
    },

    # ─── B2B Network ────────────────────────────────────────────
    {
        "key": "capx",
        "name": "CapX (B2B Acente Ağı)",
        "category": "b2b",
        "description": "Acente sözleşme + rezervasyon push (HMAC + Bearer).",
        "required_envs": ["CAPX_BASE_URL", "CAPX_API_KEY", "CAPX_WEBHOOK_SECRET"],
        "code_status": "ready",
        "module_key": "capx",
    },
    {
        "key": "marketplace",
        "name": "Syroce Marketplace (B2B)",
        "category": "b2b",
        "description": "Dahili acente pazaryeri admin API'si.",
        "required_envs": ["MARKETPLACE_ADMIN_TOKEN"],
        "code_status": "ready",
        "module_key": "marketplace",
    },

    # ─── Payment ────────────────────────────────────────────────
    {
        "key": "iyzico",
        "name": "Iyzico (Ödeme)",
        "category": "payment",
        "description": "Kart ödeme, 3DS, iade işlemleri.",
        "required_envs": ["IYZICO_API_KEY", "IYZICO_SECRET_KEY", "IYZICO_BASE_URL"],
        "code_status": "in_development",
        "module_key": "payment_iyzico",
        "pricing_note": "Henüz sözleşme yok — kod altyapısı hazır, anlaşma sonrası canlıya alınır.",
    },
    {
        "key": "stripe",
        "name": "Stripe (Ödeme — uluslararası)",
        "category": "payment",
        "description": "Yurtdışı kart kabulü.",
        "required_envs": ["STRIPE_API_KEY", "STRIPE_WEBHOOK_SECRET"],
        "code_status": "in_development",
        "module_key": "payment_stripe",
    },

    # ─── Monitoring / Observability ─────────────────────────────
    {
        "key": "sentry",
        "name": "Sentry (Hata İzleme)",
        "category": "monitoring",
        "description": "Backend + frontend hata telemetrisi.",
        "required_envs": ["SENTRY_DSN"],
        "code_status": "ready",
        "module_key": "monitoring_sentry",
    },
    {
        "key": "alert_webhook",
        "name": "Uyarı Webhook (Slack/Discord)",
        "category": "monitoring",
        "description": "Operasyonel uyarıları kanala düşürür.",
        "required_envs": ["ALERT_WEBHOOK_URL"],
        "code_status": "ready",
        "module_key": "monitoring_alerts",
    },

    # ─── Infrastructure ─────────────────────────────────────────
    {
        "key": "aws_kms",
        "name": "AWS KMS (Şifreleme Anahtarı)",
        "category": "infrastructure",
        "description": "Üretim ortamında credential şifreleme için master key.",
        "required_envs": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_KMS_KEY_ARN", "AWS_REGION"],
        "code_status": "ready",
        "module_key": "infra_kms",
    },
]

CATEGORY_LABELS = {
    "ai": "AI & LLM",
    "messaging": "Mesajlaşma",
    "channel-manager": "Kanal Yöneticisi",
    "identity": "Kimlik & KVKK",
    "loyalty": "Sadakat",
    "b2b": "B2B Ağ",
    "payment": "Ödeme",
    "monitoring": "İzleme",
    "infrastructure": "Altyapı",
}


async def _db_credential_keys() -> set[str]:
    """integration_credentials koleksiyonundaki tüm doldurulmuş key'ler."""
    keys: set[str] = set()
    try:
        async for doc in db["integration_credentials"].find(
            {"value_encrypted": {"$exists": True, "$ne": ""}},
            {"_id": 0, "key": 1},
        ):
            k = doc.get("key")
            if k:
                keys.add(k)
    except Exception:
        logger.exception("integration_credentials okuma hatası")
    return keys


def _env_set(key: str) -> bool:
    v = os.environ.get(key)
    return bool(v and v.strip())


@router.get("")
async def overview():
    """Tüm entegrasyonları durumlarına göre 3 gruba ayırarak döner."""
    db_keys = await _db_credential_keys()

    ready: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    in_dev: list[dict[str, Any]] = []

    for it in INTEGRATIONS:
        required = list(it.get("required_envs", []))
        per_tenant = bool(it.get("per_tenant", False))

        # missing = env'de YOK ve DB credential catalog'unda da YOK
        missing = [k for k in required if not _env_set(k) and k not in db_keys]

        if it["code_status"] == "in_development":
            effective = "in_development"
        elif per_tenant or not required:
            # per-tenant credential'lar bu owner ekranında "hazır" sayılır;
            # otele atanırken kendi panelinden girilecek.
            effective = "ready"
        elif missing:
            effective = "needs_credentials"
        else:
            effective = "ready"

        item = {
            "key": it["key"],
            "name": it["name"],
            "category": it["category"],
            "category_label": CATEGORY_LABELS.get(it["category"], it["category"]),
            "description": it["description"],
            "required_envs": required,
            "missing_envs": missing,
            "per_tenant": per_tenant,
            "code_status": it["code_status"],
            "effective_status": effective,
            "module_key": it.get("module_key", ""),
            "doc_url": it.get("doc_url", ""),
            "pricing_note": it.get("pricing_note", ""),
        }

        if effective == "ready":
            ready.append(item)
        elif effective == "needs_credentials":
            needs.append(item)
        else:
            in_dev.append(item)

    return {
        "ready": ready,
        "needs_credentials": needs,
        "in_development": in_dev,
        "totals": {
            "ready": len(ready),
            "needs_credentials": len(needs),
            "in_development": len(in_dev),
            "all": len(INTEGRATIONS),
        },
    }
