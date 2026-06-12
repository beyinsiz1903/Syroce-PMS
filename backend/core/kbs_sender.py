"""KBS gönderim katmanı — PMS içinden polis konaklama bildirimini iletir.

Bu modül, kuyruğa alınmış bir KBS işinin payload'unu yapılandırılabilir bir
KBS uç noktasına / entegratöre HTTP üzerinden gönderir ve dönen resmi referans
numarasını üretir. Gönderim **fail-closed**'dur:

  * `KBS_API_URL` + `KBS_API_TOKEN` ortam değişkenleri ayarlı DEĞİLSE gönderim
    yapılmaz — `KBSCredentialsMissing` fırlatılır. Sahte başarı YAZILMAZ.
  * `KBS_TEST_MODE=1` iken gerçek çağrı yapılmaz; `TEST-` ön ekli sentetik bir
    referans üretilir (complete endpoint'i zaten `TEST-` ön ekini zorunlu kılar,
    booking üzerine `kbs_test=true` işaretlenir). Bu, sertifika gelmeden uçtan
    uca akışı denemek içindir ve açıkça test olarak etiketlenir.

Dış HTTP çağrısı SSRF'e karşı sabit (DNS-rebind güvenli + private-IP reddi)
``integrations.xchange.safety.safe_post_async`` üzerinden yapılır.
"""
from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger("core.kbs_sender")

_DEFAULT_TIMEOUT_SECONDS = 30.0


class KBSCredentialsMissing(Exception):
    """KBS_API_URL / KBS_API_TOKEN ayarlı değil — gönderim yapılamaz (fail-closed)."""


class KBSSendError(Exception):
    """KBS uç noktası gönderimi reddetti veya geçerli referans dönmedi (retry'lanır)."""


def kbs_test_mode() -> bool:
    """KBS_TEST_MODE=1 → gerçek gönderim yapılmaz, TEST- referans üretilir."""
    return os.environ.get("KBS_TEST_MODE", "0") == "1"


def kbs_credentials_configured() -> bool:
    """Gerçek gönderim için gerekli ortam değişkenleri ayarlı mı?"""
    return bool(
        os.environ.get("KBS_API_URL", "").strip()
        and os.environ.get("KBS_API_TOKEN", "").strip()
    )


def kbs_dispatch_active() -> bool:
    """PMS-içi otomatik gönderici aktif mi?

    Aktif olması için (test mode) VEYA (gerçek kimlik bilgileri ayarlı) olmalı,
    ve açık `KBS_AUTO_DISPATCH=0` kill-switch'i set EDİLMEMİŞ olmalı. Kimlik
    bilgileri yoksa legacy harici-bot modeli bozulmadan çalışmaya devam eder
    (gönderici no-op döner).
    """
    if os.environ.get("KBS_AUTO_DISPATCH", "1") == "0":
        return False
    return kbs_test_mode() or kbs_credentials_configured()


def _send_timeout() -> float:
    try:
        return float(os.environ.get("KBS_SEND_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS


def _build_request_body(payload: dict, action: str) -> dict:
    """KBS asgari şemasına göre gönderim gövdesi kur (EGM/Jandarma alanları)."""
    return {
        "action": action,  # "checkin" | "checkout"
        "guest_name": payload.get("guest_name", ""),
        "nationality": payload.get("nationality", "TC"),
        "id_number": payload.get("id_number", ""),
        "passport_number": payload.get("passport_number", ""),
        "birth_date": payload.get("birth_date", ""),
        "gender": payload.get("gender", ""),
        "father_name": payload.get("father_name", ""),
        "mother_name": payload.get("mother_name", ""),
        "birth_place": payload.get("birth_place", ""),
        "address": payload.get("address", ""),
        "room_number": payload.get("room_number", ""),
        "check_in": payload.get("check_in", ""),
        "check_out": payload.get("check_out", ""),
    }


def _extract_reference(data: object) -> str:
    """Yanıttan KBS referans numarasını çıkar; bulunamazsa boş döner."""
    if not isinstance(data, dict):
        return ""
    for key in ("kbs_reference", "reference", "reference_no", "ref", "tckn_ref", "id"):
        val = data.get(key)
        if val:
            return str(val).strip()
    return ""


async def send_kbs_notification(payload: dict, action: str = "checkin") -> str:
    """Tek bir konaklama bildirimini KBS'ye gönder; resmi referansı döndür.

    Returns: KBS referans numarası (boş olmaz).
    Raises:
        KBSCredentialsMissing: kimlik bilgileri ayarlı değil (fail-closed).
        KBSSendError: uç nokta reddetti / referans dönmedi (retry edilebilir).
    """
    if kbs_test_mode():
        # Açıkça test: gerçek çağrı yok, TEST- referans. complete endpoint'i
        # bu ön eki zorunlu kılar; booking kbs_test=true işaretlenir.
        ref = f"TEST-{uuid.uuid4().hex[:16].upper()}"
        logger.info("KBS test-mode gönderim: action=%s ref=%s", action, ref)
        return ref

    if not kbs_credentials_configured():
        raise KBSCredentialsMissing(
            "KBS_API_URL / KBS_API_TOKEN ayarlı değil — gönderim yapılamaz"
        )

    from integrations.xchange.safety import EgressDenied, safe_post_async

    url = os.environ.get("KBS_API_URL", "").strip()
    token = os.environ.get("KBS_API_TOKEN", "").strip()
    body = _build_request_body(payload, action)

    try:
        resp = await safe_post_async(
            url,
            timeout=_send_timeout(),
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    except EgressDenied as exc:
        # Yapılandırma hatası (private-IP / çözümlenemeyen host); retry boşuna.
        raise KBSSendError(f"KBS_API_URL egress reddedildi: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — ağ/timeout → retry edilebilir
        raise KBSSendError(f"KBS gönderim ağ hatası: {exc}") from exc

    if resp.status_code >= 400:
        snippet = (resp.text or "")[:300]
        raise KBSSendError(f"KBS uç noktası HTTP {resp.status_code}: {snippet}")

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001 — JSON değilse referans çıkarılamaz
        data = None

    reference = _extract_reference(data)
    if not reference:
        raise KBSSendError(
            f"KBS yanıtında referans yok (HTTP {resp.status_code})"
        )
    return reference
