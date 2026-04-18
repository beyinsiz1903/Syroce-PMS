"""iyzico ödeme sağlayıcısı için ince bir sarmalayıcı.

API anahtarları henüz tanımlı değilse `is_configured()` False döner ve
çağrıyı yapan endpoint 503 ile yanıt verir. Anahtarlar eklendiği anda
tüm akış otomatik aktive olur — kod değişikliği gerekmez.

Gerekli env değişkenleri:
- IYZICO_API_KEY
- IYZICO_SECRET_KEY
- IYZICO_BASE_URL  (default: https://sandbox-api.iyzipay.com)
- PUBLIC_BASE_URL  (callback için tam URL — örn https://syroce.com)
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _env(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    return v if v not in (None, "") else default


def is_configured() -> bool:
    return bool(_env("IYZICO_API_KEY") and _env("IYZICO_SECRET_KEY"))


def get_options() -> dict:
    return {
        "api_key": _env("IYZICO_API_KEY", ""),
        "secret_key": _env("IYZICO_SECRET_KEY", ""),
        "base_url": _env("IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com"),
    }


def public_callback_url(path: str) -> str:
    base = _env("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        # geliştirme ortamı fallback — production'da ayarlanmalı
        base = (
            (_env("REPLIT_DEV_DOMAIN") and f"https://{_env('REPLIT_DEV_DOMAIN')}") or ""
        ).rstrip("/")
    return f"{base}{path}" if base else path


def init_checkout_form(payload: dict) -> dict:
    """Iyzico Checkout Form Initialize çağırır.
    Başarı durumunda `paymentPageUrl` ve `token` döner."""
    if not is_configured():
        return {"status": "failure", "errorMessage": "iyzico yapılandırılmadı"}
    try:
        import iyzipay  # type: ignore
        cf = iyzipay.CheckoutFormInitialize().create(payload, get_options())
        body = cf.read().decode("utf-8")
        import json as _json
        return _json.loads(body)
    except Exception as e:
        logger.exception("iyzico init_checkout_form error")
        return {"status": "failure", "errorMessage": str(e)}


def retrieve_checkout_form(token: str) -> dict:
    if not is_configured():
        return {"status": "failure", "errorMessage": "iyzico yapılandırılmadı"}
    try:
        import iyzipay  # type: ignore
        cf = iyzipay.CheckoutForm().retrieve(
            {"locale": "tr", "token": token}, get_options()
        )
        body = cf.read().decode("utf-8")
        import json as _json
        return _json.loads(body)
    except Exception as e:
        logger.exception("iyzico retrieve_checkout_form error")
        return {"status": "failure", "errorMessage": str(e)}
