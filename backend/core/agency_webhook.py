"""
Agency v1 — Adim 4: Outbound imzali webhook teslimi (PMS -> Acente).
=====================================================================
ADR docs/adr/2026-06-agency-pms-integration.md Karar 6.

PMS, envanter/fiyat/restriksiyon degisikliginde acenteye **imzali webhook**
firlatir. Teslim MEVCUT SXI outbox + worker uzerinden yapilir; bu modul yalniz
agency event'lerinin DISPATCH tarafini ekler (yeni event tipleri additive,
EventSyncService/CM yoluna ASLA dusmez).

Operator karari (devre kesici): olu/araliksiz hata veren bir acente endpoint'i
sistemi yormasin diye per-(tenant, agency) bir devre kesici (Redis-backed,
infra/circuit_breaker_store) ile korunur. Devre OPEN iken HTTP cagrisi YAPILMAZ
(endpoint dovulmez); olay "retryable: circuit_open" ile yeniden zamanlanir ve
deneme sayar. 8 denemeden sonra DLQ (status=failed) — sessiz drop YOK. webhook_url
konfigurasyonu ASLA otomatik silinmez (kalici disable degil); kurtarma half-open
probe ile otomatiktir.

Imza: inbound (acente->PMS) ile SIMETRIK semadir; kanonik string-to-sign tek
kaynaktan (routers.agency_v1.auth._build_string_to_sign) reuse edilir. Outbound
yon header'lari: X-Syroce-Signature / X-Syroce-Nonce / X-Syroce-Timestamp.
Imzalanan govde = GONDERILEN bytes (httpx content=body); tekrar serialize edilmez.

Doktrin: shared_secret / imza / payload govdesi ASLA loglanmaz veya yanitta
gecmez. Sozlesme/webhook_url/shared_secret cozulemezse fail-closed permanent.
agency_id<->tenant_id eslemesi PMS cekirdegine gomulmez (Karar 7); bu modul SXI
kenarinda izole durur.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse

from infra.circuit_breaker_store import circuit_breaker_store
from integrations.xchange.safety import EgressDenied, safe_post_async

logger = logging.getLogger("core.agency_webhook")


# ── Event tipleri (additive; OTA setine GIRMEZ -> CM/EventSyncService'e ulasmaz) ──
AGENCY_INVENTORY_UPDATED = "agency.inventory.availability.updated.v1"
AGENCY_RATE_UPDATED = "agency.rate.updated.v1"
AGENCY_RESTRICTION_UPDATED = "agency.restriction.updated.v1"

AGENCY_OUTBOX_EVENT_TYPES = {
    AGENCY_INVENTORY_UPDATED,
    AGENCY_RATE_UPDATED,
    AGENCY_RESTRICTION_UPDATED,
}

# Acente webhook'lari olu bir acenteyi ~24h boyunca (8 deneme) dener, sonra DLQ.
# RETRY_BACKOFF keys 6/7/8 outbox_service'te eklenir (OTA max 5, etkilenmez).
AGENCY_MAX_ATTEMPTS = 8

# Outbound imza header'lari (PMS -> Acente yonu; ADR Karar 6 donmus).
_SIG_HEADER = "X-Syroce-Signature"
_NONCE_HEADER = "X-Syroce-Nonce"
_TS_HEADER = "X-Syroce-Timestamp"

# Devre kesici esikleri (per-(tenant, agency) endpoint). Env ile ayarlanabilir.
_CB_FAILURE_THRESHOLD = int(os.getenv("AGENCY_WEBHOOK_CB_FAILURE_THRESHOLD", "5"))
_CB_RECOVERY_TIMEOUT = int(os.getenv("AGENCY_WEBHOOK_CB_RECOVERY_SECONDS", "300"))
_CB_HALF_OPEN_MAX = int(os.getenv("AGENCY_WEBHOOK_CB_HALF_OPEN_MAX", "2"))

_OUTBOUND_TIMEOUT = float(os.getenv("AGENCY_WEBHOOK_TIMEOUT_SECONDS", "15") or "15")


def _serialize_body(payload: dict[str, Any]) -> bytes:
    """Deterministik govde serilestirme. Imzalanan ve gonderilen bytes AYNIDIR."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _outbound_canonical_query(query: str) -> str:
    """Inbound _canonical_query ile birebir ayni kanoniklestirme (sorted + quote_plus)."""
    items = sorted(parse_qsl(query, keep_blank_values=True))
    if not items:
        return ""
    return urlencode(items, quote_via=quote_plus)


def _sign_outbound(
    *, key_id: str, shared_secret: str, webhook_url: str, body: bytes
) -> dict[str, str]:
    """Outbound imza header'larini uretir. Imza, inbound ile simetrik kanonik
    string-to-sign uzerinden (tek kaynak reuse) hesaplanir."""
    from routers.agency_v1.auth import _build_string_to_sign

    parsed = urlparse(webhook_url)
    path = parsed.path or "/"
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    string_to_sign = _build_string_to_sign(
        key_id=key_id,
        method="POST",
        path=path,
        canonical_query=_outbound_canonical_query(parsed.query),
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    signature = hmac.new(
        shared_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": f"Bearer {key_id}",
        _TS_HEADER: timestamp,
        _NONCE_HEADER: nonce,
        _SIG_HEADER: signature,
        "Content-Type": "application/json",
    }


async def _resolve_outbound_secret(
    sysdb, tenant_id: str, agency_id: str
) -> dict | None:
    """(tenant_id, agency_id) icin aktif imza kimligini cozer. agency_signing_secrets
    _id=key_id ile saklanir; burada (tenant, agency) ile aktif olani bulup
    shared_secret'i AAD-bagli cozeriz. Cozulemezse fail-closed None."""
    from routers.agency_v1.signing_store import resolve_signing_secret

    doc = await sysdb.agency_signing_secrets.find_one(
        {"tenant_id": tenant_id, "agency_id": agency_id, "is_active": True},
        {"_id": 1},
        sort=[("created_at", -1)],
    )
    if not doc:
        return None
    key_id = doc["_id"]
    return await resolve_signing_secret(sysdb, key_id)


async def _cb_record_failure(cb_key: str) -> None:
    if not circuit_breaker_store.enabled:
        return
    try:
        await circuit_breaker_store.record_failure(cb_key, _CB_FAILURE_THRESHOLD)
    except Exception:  # pragma: no cover - CB store hatasi teslimi engellemez
        pass


async def _cb_record_success(cb_key: str) -> None:
    if not circuit_breaker_store.enabled:
        return
    try:
        await circuit_breaker_store.record_success(cb_key, _CB_HALF_OPEN_MAX)
    except Exception:  # pragma: no cover
        pass


async def dispatch_agency_webhook(event: dict[str, Any]) -> tuple[bool, str]:
    """Bir agency outbox event'ini imzali webhook olarak acenteye teslim eder.

    Returns (success, message). message prefix'leri worker sozlesmesiyle uyumlu:
      - (True, "...")            -> teslim edildi (CM mapping'e ASLA gitmez)
      - (False, "retryable: ..") -> gecici; backoff ile yeniden denenir
      - (False, "permanent: ..") -> kalici; DLQ (status=failed) + alarm
    """
    event_type = event.get("event_type", "")
    tenant_id = event.get("tenant_id", "")
    payload = event.get("payload", {}) or {}
    agency_id = payload.get("agency_id") or event.get("agency_id") or ""
    event_id = event.get("id", "unknown")

    if not tenant_id or not agency_id:
        return False, "permanent: missing tenant_id/agency_id"

    from core.tenant_db import get_system_db

    sysdb = get_system_db()

    # 1) Hedef webhook_url'i aktif sozlesmeden coz (fail-closed).
    from routers.agency_contracts import has_active_contract

    contract = await has_active_contract(agency_id, tenant_id)
    if not contract:
        return False, "permanent: no active agency contract"
    webhook_url = contract.get("webhook_url")
    if not webhook_url:
        return False, "permanent: agency contract has no webhook_url"

    # 2) Imza kimligini coz (fail-closed not_configured).
    resolved = await _resolve_outbound_secret(sysdb, tenant_id, agency_id)
    if not resolved:
        return False, "permanent: agency signing secret not_configured"

    # 3) Devre kesici kapisi (olu endpoint'i dovme).
    cb_key = f"agency_webhook:{tenant_id}:{agency_id}"
    admitted = True
    if circuit_breaker_store.enabled:
        try:
            _state, admitted = await circuit_breaker_store.try_acquire(
                cb_key, _CB_RECOVERY_TIMEOUT, _CB_HALF_OPEN_MAX
            )
        except Exception:  # pragma: no cover - CB store hatasi -> fail-open dene
            admitted = True
    if not admitted:
        # OPEN: HTTP cagrisi YAPILMAZ; deneme sayilir, backoff ile beklenir.
        return False, "retryable: circuit_open agency webhook endpoint"

    # 4) Imzala + rebinding-safe teslim et. Imzalanan ve gonderilen govde AYNI bytes.
    body = _serialize_body(payload)
    headers = _sign_outbound(
        key_id=resolved["key_id"],
        shared_secret=resolved["shared_secret"],
        webhook_url=webhook_url,
        body=body,
    )

    try:
        resp = await safe_post_async(
            webhook_url, timeout=_OUTBOUND_TIMEOUT, content=body, headers=headers
        )
    except EgressDenied as e:
        # SSRF/private/yanlis konfig -> sonsuz retry anlamsiz; DLQ + alarm.
        return False, f"permanent: egress denied: {str(e)[:200]}"
    except Exception as e:
        # Baglanti hatasi/timeout -> endpoint erisilemez -> CB failure + retry.
        # Yalniz exception SINIF adi kullanilir; str(e) webhook_url'i (ve olasi
        # query token'ini) gomeebilir -> doktrin geregi mesaja/persiste edilen
        # last_error'a URL SIZDIRILMAZ.
        await _cb_record_failure(cb_key)
        logger.warning(
            "Agency webhook delivery error: event=%s agency=%s err=%s",
            event_id, agency_id, type(e).__name__,
        )
        return False, f"retryable: delivery error: {type(e).__name__}"

    code = resp.status_code
    if 200 <= code < 300:
        await _cb_record_success(cb_key)
        return True, f"delivered: {code}"

    if code in (408, 429) or code >= 500:
        # Endpoint erisilebilir ama hata veriyor -> dovme; CB failure + retry.
        await _cb_record_failure(cb_key)
        return False, f"retryable: webhook returned {code}"

    # Diger 4xx -> kalici red. Endpoint erisilebilir -> CB success.
    await _cb_record_success(cb_key)
    return False, f"permanent: webhook returned {code}"


async def enqueue_agency_webhook_event(
    db,
    *,
    session=None,
    tenant_id: str,
    agency_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Agency outbound webhook event'ini outbox'a atomik yazar (is islemiyle ayni
    transaction'da cagrilmali). provider="agency" (super_admin replay filtresi),
    max_attempts=8. agency_id payload'a routing kimligi olarak gomulur (SXI kenari).
    """
    if event_type not in AGENCY_OUTBOX_EVENT_TYPES:
        raise ValueError(f"unsupported agency event_type: {event_type}")

    from core.outbox_service import enqueue_outbox_event

    enriched = dict(payload)
    enriched["agency_id"] = agency_id
    return await enqueue_outbox_event(
        db,
        session=session,
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=enriched,
        provider="agency",
        correlation_id=correlation_id,
        max_attempts=AGENCY_MAX_ATTEMPTS,
    )
