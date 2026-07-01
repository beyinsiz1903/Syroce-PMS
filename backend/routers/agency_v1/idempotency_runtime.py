"""
Agency v1 — Idempotency runtime (ADR Karar 4).

Rezervasyon yazan uclar (POST create / PATCH modify / DELETE cancel) icin
idempotency. Bu modul SOGUK katmani (MongoDB `idempotency_cache`) gerceklestirir;
correctness siniri BURADADIR: DB-atomik benzersiz scope index'i (Adim 1'de
basildi: ux_idempotency_cache_scope) es-zamanli claim'leri transaction olmadan
serilestir.

Iki-katmanli saklama (Karar 4) RAM kontrolu icindir: agir rezervasyon yanit
govdelerini 48h Redis RAM'inde tutmamak. Bu implementasyon hicbir sicak govdeyi
Redis'e koymaz; tum davranis matrisi + 48h replay Mongo'da. Bu, frozen kararin
RAM-kontrol amaciyla tutarlidir (doktrin: Redis correctness sinirini
OLUSTURAMAZ; opsiyonel sicak hizlandirici additive olarak onune eklenebilir).

Davranis matrisi (donmus):
  - Ayni scope + ayni govde parmak-izi + completed -> REPLAY (cached yanit).
  - Ayni scope + FARKLI parmak-izi -> CONFLICT (422 idempotency_conflict).
  - Ayni scope + ayni parmak-izi + hala processing -> IN_PROGRESS
    (409 idempotency_in_progress; acente kisa backoff ile retry eder).
  - TTL dolunca (Mongo sweeper) -> yeni islem.

Scope (donmus, Karar 4): (tenant_id, agency_id, method, path, idempotency_key).

ORDER (donmus kural): cagiran uc once begin_agency_idempotency() ile in-flight
slotu alir (processing), SONRA atomik envanter claim yapar. Envanter ASLA
idempotency slotundan ONCE dusmez (overbooking). complete() yalniz islem
basariyla cozulunce cagrilir; envanter/dogrulama reddinde release() (henuz
kalici booking yazilmadigi icin guvenli).

PII-at-rest: yanit govdesi seal_response_body ile sifreli zarf olarak yazilir
(shared_kernel tek kaynak); crypto yoksa fail-closed (bos zarf; plaintext PII
ASLA yazilmaz). Secret/PII loglanmaz.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from shared_kernel.idempotency import seal_response_body, unseal_response_body

logger = logging.getLogger("agency_v1.idempotency")

# In-flight processing slotu icin KISA grace: bir worker crash ederse 48h boyunca
# ayni key bloklanmasin (Mongo TTL sweeper kisa surede temizler). complete()
# expires_at'i 48h replay penceresine iter.
PROCESSING_GRACE_SECONDS = 120
# Replay penceresi: ADR 48h (acente retry penceresinden marjli buyuk).
RETENTION_SECONDS = 48 * 3600

BeginStatus = Literal["acquired", "replay", "conflict", "in_progress"]


def _scope_filter(tenant_id: str, agency_id: str, method: str, path: str, idempotency_key: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "method": method,
        "path": path,
        "idempotency_key": idempotency_key,
    }


class _AgencyIdemLock:
    """begin() 'acquired' dondugunde verilen tutamac.

    complete(): basariyla cozulen yaniti sifreli + 48h TTL ile yazar.
    release(): processing slotunu siler (yalniz ilk kalici yazimdan ONCE guvenli).
    """

    def __init__(self, db_handle: Any, scope_filter: dict[str, Any]):
        self._db = db_handle
        self._scope = scope_filter

    async def complete(self, response_body: dict[str, Any], *, status_code: int) -> bool:
        """Cozulen yaniti sifreli + 48h TTL ile yazar. True doner.

        upsert=False (bilincli): processing slotu cok yavas handler + TTL sweep
        ile silinmisse (matched_count==0) completion DUSURULMEZ-ama-yeni-satir-da
        olusturulmaz; deterministik bir uyari loglanir ve False doner. Yeniden
        olusturmak yaris-acar (silinmis slot baska bir in-flight claim'i temsil
        edebilir). Sessiz dusurme YOK (no fake-green); cagiran False'u gozler.
        """
        now = datetime.now(UTC)
        set_fields: dict[str, Any] = {
            "status": "completed",
            "status_code": int(status_code),
            "completed_at": now.isoformat(),
            "expires_at": now + timedelta(seconds=RETENTION_SECONDS),
        }
        # PII-at-rest: yalniz sifreli zarf. crypto yoksa {} -> plaintext YAZILMAZ
        # (replay bos govdeye duser, sizinti olmaz). Tek kaynak: shared_kernel.
        set_fields.update(seal_response_body(response_body))
        res = await self._db.idempotency_cache.update_one(self._scope, {"$set": set_fields})
        matched = getattr(res, "matched_count", 1)
        if matched == 0:
            logger.warning("agency idempotency: completion lock missing (stale/expired before complete); replay not cached")
            return False
        return True

    async def release(self) -> None:
        await self._db.idempotency_cache.delete_one(self._scope)


@dataclass(frozen=True)
class AgencyIdempotencyResult:
    status: BeginStatus
    response: dict[str, Any] | None = None
    status_code: int | None = None
    lock: _AgencyIdemLock | None = None


async def begin_agency_idempotency(
    db_handle: Any,
    *,
    tenant_id: str,
    agency_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> AgencyIdempotencyResult:
    """ADR Karar 4 davranis matrisini atomik olarak uygular.

    DB-atomik benzersiz scope index'i (Adim 1) es-zamanli claim'leri serilestir;
    transaction gerekmez. Cagiran 'acquired' aldiginda is yapar, sonra
    lock.complete()/lock.release() cagirir.
    """
    from pymongo.errors import DuplicateKeyError  # type: ignore

    scope = _scope_filter(tenant_id, agency_id, method, path, idempotency_key)
    now = datetime.now(UTC)
    doc = {
        **scope,
        "request_fingerprint": request_fingerprint,
        "status": "processing",
        "created_at": now.isoformat(),
        # BSON Date -> TTL sweeper; processing slotu kisa grace ile expire olur.
        "expires_at": now + timedelta(seconds=PROCESSING_GRACE_SECONDS),
    }
    try:
        await db_handle.idempotency_cache.insert_one(doc)
        return AgencyIdempotencyResult(status="acquired", lock=_AgencyIdemLock(db_handle, scope))
    except DuplicateKeyError:
        existing = await db_handle.idempotency_cache.find_one(scope, {"_id": 0})
        if not existing:
            # Yaris: insert ile find arasinda TTL/silinme oldu. Guvenli taraf:
            # in_progress dondur (acente kisa backoff ile retry eder).
            return AgencyIdempotencyResult(status="in_progress")
        # Parmak-izi uyumsuzlugu HER ZAMAN once: ayni key + farkli govde -> 422.
        if existing.get("request_fingerprint") != request_fingerprint:
            return AgencyIdempotencyResult(status="conflict")
        if existing.get("status") == "completed":
            return AgencyIdempotencyResult(
                status="replay",
                response=unseal_response_body(existing),
                status_code=existing.get("status_code"),
            )
        return AgencyIdempotencyResult(status="in_progress")
