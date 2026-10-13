"""Zoho Mail HTTPS transport. No arbitrary endpoints or SMTP fallback.

OAuth credentials belong to the tenant configuration. Response bodies and
exceptions are intentionally not logged: they may contain tokens or messages.
"""

import asyncio
import hashlib
import time

import httpx

from integrations.xchange.safety import EgressDenied, safe_request_async

DOMAINS = {"eu": "zoho.eu", "us": "zoho.com"}
SECRET_KEYS = {"zoho_client_secret", "zoho_refresh_token"}
_tokens = {}
_lock = asyncio.Lock()


def validate_credentials(creds):
    if creds.get("zoho_region") not in DOMAINS:
        raise ValueError("Zoho bölgesi EU veya US olmalı.")
    if not str(creds.get("zoho_account_id", "")).isascii() or not str(creds.get("zoho_account_id", "")).isdigit():
        raise ValueError("Zoho hesap kimliği yalnız rakam içermeli.")
    for key in ("zoho_client_id", "zoho_client_secret", "zoho_refresh_token", "from_email"):
        if not isinstance(creds.get(key), str) or not creds[key].strip():
            raise ValueError("Zoho OAuth bilgileri ve gönderen adresi eksiksiz olmalı.")
        if creds[key].startswith(("SYR1:", "aes256gcm:")):
            raise ValueError("Zoho anahtarları çözülemedi; sunucu şifreleme yapılandırmasını kontrol edin.")


class ZohoError(Exception):
    pass


async def access_token(creds):
    # Bounded process-local cache; rotated credentials cannot reuse an old token.
    key = hashlib.sha256(repr(tuple(creds.get(k) for k in (
        "zoho_region", "zoho_client_id", "zoho_client_secret", "zoho_refresh_token",
    ))).encode()).hexdigest()
    async with _lock:
        cached = _tokens.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        response = await safe_request_async(
            "POST",
            f"https://accounts.{DOMAINS[creds['zoho_region']]}/oauth/v2/token",
            timeout=15,
            data={"grant_type": "refresh_token", "client_id": creds["zoho_client_id"],
                  "client_secret": creds["zoho_client_secret"], "refresh_token": creds["zoho_refresh_token"]},
        )
        payload = response.json()
        token = payload.get("access_token")
        if response.status_code != 200 or not isinstance(token, str) or not token:
            raise ZohoError("Zoho OAuth yenilemesi başarısız; bölge ve OAuth yetkisini kontrol edin.")
        ttl = min(max(int(payload.get("expires_in", 3600)) - 60, 0), 3540)
        if len(_tokens) >= 128:
            _tokens.clear()
        _tokens[key] = (token, time.monotonic() + ttl)
        return token


async def account(creds, token):
    response = await safe_request_async(
        "GET",
        f"https://mail.{DOMAINS[creds['zoho_region']]}/api/accounts",
        timeout=15,
        headers={"Authorization": f"Zoho-oauthtoken {token}"},
    )
    payload = response.json()
    if response.status_code != 200 or payload.get("status", {}).get("code") != 200:
        raise ZohoError("Zoho hesabı doğrulanamadı; ZohoMail.accounts.READ iznini kontrol edin.")
    for item in payload.get("data", []):
        if str(item.get("accountId")) != creds["zoho_account_id"]:
            continue
        addresses = {str(a.get("mailId", "")).lower() for a in item.get("emailAddress", []) if a.get("isConfirmed")}
        if creds["from_email"].lower() not in addresses or item.get("outgoingBlocked") or item.get("enabled") is False:
            break
        return
    raise ZohoError("Zoho hesap kimliği/gönderen adresi eşleşmiyor veya gönderim engelli.")


async def check_health(creds):
    try:
        validate_credentials(creds)
        token = await access_token(creds)
        await account(creds, token)
        return {"status": "healthy", "note": "OAuth ve gönderen doğrulandı; mesaj gönderilmedi. Gönderim izni test e-postasıyla doğrulanmalıdır."}
    except (ValueError, TypeError, AttributeError, ZohoError) as exc:
        return {"status": "unhealthy", "error": str(exc) if isinstance(exc, ZohoError) else "Zoho yapılandırması veya yanıtı geçersiz."}
    except (httpx.HTTPError, EgressDenied):
        return {"status": "unhealthy", "error": "Zoho HTTPS bağlantısı tamamlanamadı."}


async def send(recipient, body, subject, creds):
    started = time.monotonic()
    attempted = False
    try:
        validate_credentials(creds)
        token = await access_token(creds)
        await account(creds, token)
        attempted = True
        response = await safe_request_async(
            "POST", f"https://mail.{DOMAINS[creds['zoho_region']]}/api/accounts/{creds['zoho_account_id']}/messages",
            timeout=20, headers={"Authorization": f"Zoho-oauthtoken {token}"},
            json={"fromAddress": creds["from_email"], "toAddress": recipient,
                  "subject": subject or "Otel Bilgilendirme", "content": body,
                  "mailFormat": "html" if any(tag in body.lower() for tag in ("<html", "<div", "<p>")) else "plaintext",
                  "encoding": "UTF-8"},
        )
        payload = response.json()
        message_id = (payload.get("data") or {}).get("messageId")
        if response.status_code == 200 and payload.get("status", {}).get("code") == 200 and message_id:
            return {"success": True, "provider_message_id": str(message_id), "latency_ms": (time.monotonic() - started) * 1000}
        return {"success": False, "outcome_unknown": response.status_code >= 500 or response.status_code == 200,
                "error_class": "provider_error", "error": f"Zoho gönderimi doğrulanamadı (HTTP {response.status_code}); Zoho gönderilenler klasörünü kontrol edin."}
    except (httpx.HTTPError, EgressDenied, ValueError, TypeError, AttributeError, ZohoError):
        return {"success": False, "outcome_unknown": attempted, "error_class": "zoho_error",
                "error": "Zoho HTTPS gönderimi tamamlanamadı. OAuth, hesap ve bağlantı ayarlarını kontrol edin."}
