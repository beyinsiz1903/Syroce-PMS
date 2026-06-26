"""
Agency v1 — S2S HMAC imza dogrulama dependency (ADR Karar 2).

Her acente->PMS istegi su header'lari tasir:
  - `Authorization: Bearer <key_id>`  (public tanimlayici; SIR DEGIL)
  - `X-Agency-Timestamp` (Unix saniye), `X-Agency-Nonce` (essiz jti),
    `X-Agency-Signature` (hex hmac_sha256)

Kanonik string-to-sign (DONMUS, Karar 2):
  key_id\\nmethod\\npath\\ncanonical_query\\ntimestamp\\nnonce\\nsha256_hex(body)
  X-Agency-Signature = hex(hmac_sha256(shared_secret, string_to_sign))

`canonical_query`: query parametreleri ad'a gore siralanmis + URL-encode (bos -> "").
Bu referans implementasyon kanoniklestirmeyi `urlencode(sorted(multi_items),
quote_via=quote_plus)` olarak SABITLER; acente SDK'si ayni uretmeli.

Tazelik penceresi (DONMUS): +/-300s tazelik + /-60s saat-kaymasi = etkin +/-360s.
Replay korumasi: `(key_id, nonce)` DB-atomik replay-cache'te (agency_nonces, _id
benzersiz); ayni nonce -> 401. Cache TTL = 600s (>= 360s kabul penceresi; degismez
kural: TTL >= pencere, aksi halde nonce suresi dolup timestamp gecerliyken replay
acilir).

Body TUKETME TUZAGI: imza body hash'i `await request.body()` ile okunur —
Starlette bunu `request._body`'de cache'ler; Pydantic ayni cache'i okur (govde
tukenmez). ASGI middleware `receive()` tuzagina DUSULMEZ.

Doktrin: gecersiz/eksik imza, pencere disi timestamp, tekrar nonce, cozulemeyen
sir, devre disi key -> fail-closed 401. shared_secret/imza degerleri ASLA
loglanmaz/yanitta gecmez. Kimlik (tenant/agency) SUNUCU tarafinda key_id'den
cozulur; istek govdesinden ASLA guvenilmez.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import quote_plus, urlencode

from fastapi import HTTPException, Request

from .signing_store import resolve_signing_secret

logger = logging.getLogger("agency_v1.auth")

ACCEPT_WINDOW_SECONDS = 360  # +/-300 tazelik + /-60 saat-kaymasi (donmus)
NONCE_TTL_SECONDS = 600      # >= ACCEPT_WINDOW_SECONDS (degismez kural)

_UNAUTHORIZED = "unauthorized"


def _canonical_query(request: Request) -> str:
    items = sorted(request.query_params.multi_items())
    if not items:
        return ""
    return urlencode(items, quote_via=quote_plus)


def _build_string_to_sign(
    *, key_id: str, method: str, path: str, canonical_query: str,
    timestamp: str, nonce: str, body: bytes,
) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join(
        [key_id, method, path, canonical_query, timestamp, nonce, body_hash]
    )


def _bearer_key_id(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    key_id = authorization[len(prefix):].strip()
    return key_id or None


async def _claim_nonce(sysdb, key_id: str, nonce: str) -> bool:
    """DB-atomik nonce claim. True=ilk gorulus, False=replay (DuplicateKeyError).

    `_id` benzersizligi serilestir; TTL (expires_at, now+600s) Mongo sweeper ile
    temizler. TTL index ayri (perf_indexes / bootstrap)."""
    from datetime import UTC, datetime, timedelta

    try:
        from pymongo.errors import DuplicateKeyError
    except Exception:  # pragma: no cover
        DuplicateKeyError = Exception  # type: ignore

    now = datetime.now(UTC)
    try:
        await sysdb.agency_nonces.insert_one(
            {
                "_id": f"{key_id}:{nonce}",
                "expires_at": now + timedelta(seconds=NONCE_TTL_SECONDS),
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def verify_agency_signature(request: Request) -> dict:
    """FastAPI dependency: HMAC imzayi dogrular, kimligi (tenant/agency) doner.

    Basari -> {"key_id","tenant_id","agency_id"} + tenant context set edilir.
    Herhangi bir basarisizlik -> 401 (fail-closed). Sir/imza loglanmaz.
    """
    from core.tenant_db import get_system_db, set_tenant_context

    headers = request.headers
    key_id = _bearer_key_id(headers.get("authorization"))
    timestamp = headers.get("x-agency-timestamp")
    nonce = headers.get("x-agency-nonce")
    signature = headers.get("x-agency-signature")
    if not (key_id and timestamp and nonce and signature):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    # Tazelik penceresi (imza dogrulamadan once ucuz reddet).
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
    if abs(int(time.time()) - ts_int) > ACCEPT_WINDOW_SECONDS:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    sysdb = get_system_db()

    # Sir + kimlik cozumu (signing_store; kendi is_active revoke kapisi var).
    resolved = await resolve_signing_secret(sysdb, key_id)
    if not resolved:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    # Revoke kapisi: key_id ayni zamanda agency_api_keys.id'dir; api key devre
    # disi birakilirsa agency_v1 erisimi de kapanmali (auth zayiflatilmaz).
    apikey = await sysdb.agency_api_keys.find_one(
        {"id": key_id, "is_active": True}, {"_id": 0, "tenant_id": 1, "agency_id": 1}
    )
    if not apikey:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
    # Savunma derinligi: signing dokumani ile api key ayni (tenant, agency)
    # ciftine baglanmali; uyumsuzluk -> tamper -> 401.
    if (apikey.get("tenant_id") != resolved["tenant_id"]
            or apikey.get("agency_id") != resolved["agency_id"]):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    # Body-cache guvenli okuma (tuketme yok).
    body = await request.body()
    string_to_sign = _build_string_to_sign(
        key_id=key_id,
        method=request.method,
        path=request.url.path,
        canonical_query=_canonical_query(request),
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    expected = hmac.new(
        resolved["shared_secret"].encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    # Imza gecerli -> SIMDI nonce claim (gecersiz isteklerle cache'i doldurma).
    if not await _claim_nonce(sysdb, key_id, nonce):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    set_tenant_context(resolved["tenant_id"])
    return {
        "key_id": key_id,
        "tenant_id": resolved["tenant_id"],
        "agency_id": resolved["agency_id"],
    }
