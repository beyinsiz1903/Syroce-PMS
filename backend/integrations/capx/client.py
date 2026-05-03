"""CapX B2B Network HMAC client.

Spec (üreticiden):
  Base: <CAPX_BASE_URL>/api/integrations/v1/pms

  Auth modları:
    - JWT (otel kullanıcısı)            → connect/status/callback/disconnect/recent
    - Bearer API key                    → POST /availability/sync
    - Bearer + HMAC SHA-256 (X-CapX-*)  → POST /reservation/event

  HMAC payload: raw request body (UTF-8 bytes)
  Header: X-CapX-Signature: sha256=<hex>
  Idempotency: X-CapX-Event-Id (UUID4 per event)

Faz 3 — tenant-aware:
  get_capx_client(tenant_id=None) → tenant_id verilirse koleksiyondan oku,
  yoksa env'den (backward-compatible). Cache: tenant_id → CapXClient.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any

import httpx

from .tenant_creds import CapXCreds, resolve_credentials

logger = logging.getLogger(__name__)


class CapXError(Exception):
    """CapX API error wrapper."""

    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CapXClient:
    """Async CapX integration client."""

    PATH_AVAILABILITY = "/api/integrations/v1/pms/availability/sync"
    PATH_RESERVATION = "/api/integrations/v1/pms/reservation/event"
    PATH_STATUS = "/api/integrations/v1/pms/status"
    PATH_RECENT = "/api/integrations/v1/pms/recent"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None,
                 webhook_secret: str | None = None, timeout: float = 15.0,
                 tenant_id: str | None = None):
        self.base_url = (base_url or os.getenv("CAPX_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("CAPX_API_KEY", "")
        self.webhook_secret = webhook_secret or os.getenv("CAPX_WEBHOOK_SECRET", "")
        self.timeout = timeout
        self.tenant_id = tenant_id

    @classmethod
    def from_creds(cls, creds: CapXCreds, *, tenant_id: str | None = None,
                   timeout: float = 15.0) -> "CapXClient":
        return cls(
            base_url=creds.base_url, api_key=creds.api_key,
            webhook_secret=creds.webhook_secret, timeout=timeout, tenant_id=tenant_id,
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _sign(self, body_bytes: bytes) -> str:
        if not self.webhook_secret:
            raise CapXError("CAPX_WEBHOOK_SECRET not set")
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def _bearer_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CapXError("CAPX_API_KEY not set")
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _post(self, path: str, body: dict[str, Any], *, sign: bool = False,
                    event_id: str | None = None, jwt_token: str | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise CapXError("CAPX_BASE_URL not set")
        url = f"{self.base_url}{path}"
        body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        else:
            headers.update(self._bearer_headers())
        if sign:
            headers["X-CapX-Signature"] = self._sign(body_bytes)
            headers["X-CapX-Event-Id"] = event_id or str(uuid.uuid4())

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("CapX network error %s: %s", path, exc)
            raise CapXError(f"network error: {exc}") from exc

        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            logger.warning("CapX %s -> %d: %s", path, resp.status_code, err_body)
            raise CapXError(f"{resp.status_code} {path}", status_code=resp.status_code, body=err_body)

        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text, "status_code": resp.status_code}

    async def _get(self, path: str, *, jwt_token: str | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise CapXError("CAPX_BASE_URL not set")
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        else:
            headers.update(self._bearer_headers())
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise CapXError(f"network error: {exc}") from exc
        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            raise CapXError(f"{resp.status_code} {path}", status_code=resp.status_code, body=err_body)
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    # ── Public API ────────────────────────────────────────────────

    async def push_availability(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Push PMS availability snapshot."""
        return await self._post(self.PATH_AVAILABILITY, snapshot)

    async def push_reservation_event(self, event: dict[str, Any], *,
                                      event_id: str | None = None) -> dict[str, Any]:
        """Push booking lifecycle event (created / cancelled / no_show /
        counter_offer_accepted / counter_offer_rejected)."""
        return await self._post(
            self.PATH_RESERVATION, event, sign=True, event_id=event_id
        )

    async def push_rate_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push date-aware rate update.

        payload shape:
          {
            "room_type": "DBL_STD",
            "rates": [
              {"date": "2026-05-10", "price": 2800.0, "currency": "TRY"},
              ...
            ],
            "pms_external_ref": "syroce-rate-..."
          }

        Faz 3 — CapX `availability/sync` endpoint'i fiyat snapshot'larını da
        kabul ediyor, ancak granüler tarih bazlı bazda olması için her gün için
        ayrı snapshot push'larız (üreticinin önerdiği pattern).
        """
        return await self._post(self.PATH_AVAILABILITY, payload)

    async def get_status(self, jwt_token: str) -> dict[str, Any]:
        """JWT-authenticated status check (otel kullanıcısı)."""
        return await self._get(self.PATH_STATUS, jwt_token=jwt_token)

    async def get_recent(self, jwt_token: str) -> dict[str, Any]:
        return await self._get(self.PATH_RECENT, jwt_token=jwt_token)


# ── Tenant-aware factory ─────────────────────────────────────────
#
# _tenant_clients: tenant_id → (expires_ts, client). TTL 5 dk → tenant_creds
# cache TTL ile aynı. Lock concurrent build'i önler.
# _MAX_TENANT_CLIENTS bellek sınırı (LRU benzeri eviction).

_env_singleton: CapXClient | None = None
_tenant_clients: dict[str, tuple[float, CapXClient]] = {}
_tenant_locks: dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()
_CLIENT_CACHE_TTL = 300  # 5 dk
_MAX_TENANT_CLIENTS = 256


def _build_env_client() -> CapXClient:
    return CapXClient()


def _evict_if_oversized() -> None:
    if len(_tenant_clients) <= _MAX_TENANT_CLIENTS:
        return
    # En eski expire'lı 32 entry'yi at
    sorted_keys = sorted(_tenant_clients.items(), key=lambda kv: kv[1][0])[:32]
    for k, _ in sorted_keys:
        _tenant_clients.pop(k, None)
        _tenant_locks.pop(k, None)


async def get_capx_client_async(
    tenant_id: str | None = None, refresh: bool = False,
) -> CapXClient:
    """Tenant-aware client factory.

    tenant_id verilirse `capx_tenant_credentials` koleksiyonundan oku,
    yoksa env (backward-compatible).

    Cache: env için global singleton, tenant başına TTL'li cache (5 dk).
    Concurrent build'leri önlemek için per-tenant asyncio.Lock kullanılır.
    `refresh=True` → cache'i bypass et.
    """
    if not tenant_id:
        return get_capx_client(refresh=refresh)

    now = time.time()
    if not refresh:
        cached = _tenant_clients.get(tenant_id)
        if cached and cached[0] > now:
            return cached[1]

    # Per-tenant lock (lock kendi de cache'leniyor)
    async with _global_lock:
        lock = _tenant_locks.setdefault(tenant_id, asyncio.Lock())

    async with lock:
        # Double-check (başka coroutine zaten build etmiş olabilir)
        if not refresh:
            cached = _tenant_clients.get(tenant_id)
            if cached and cached[0] > now:
                return cached[1]
        creds = await resolve_credentials(tenant_id)
        if creds.source == "env":
            return get_capx_client(refresh=refresh)
        client = CapXClient.from_creds(creds, tenant_id=tenant_id)
        _tenant_clients[tenant_id] = (now + _CLIENT_CACHE_TTL, client)
        _evict_if_oversized()
        return client


def get_capx_client(refresh: bool = False) -> CapXClient:
    """Backward-compatible env-only sync factory.

    Faz 3 öncesi tüm caller'lar bunu kullanıyordu — değişmedi.
    Tenant-aware kullanım için get_capx_client_async kullanın.
    """
    global _env_singleton
    if _env_singleton is None or refresh:
        _env_singleton = _build_env_client()
    return _env_singleton


def invalidate_client_cache(tenant_id: str | None = None) -> None:
    """Tenant credential değişince çağrılır."""
    global _env_singleton
    if tenant_id is None:
        _env_singleton = None
        _tenant_clients.clear()
        _tenant_locks.clear()
    else:
        _tenant_clients.pop(tenant_id, None)
        _tenant_locks.pop(tenant_id, None)
