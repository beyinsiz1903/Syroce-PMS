"""Migration advisory lock — çoklu-instance güvenliği (race-safe + lease/TTL).

Aynı anda iki instance/worker açıldığında migration'lar yalnızca bir kez
koşmalı. Bu kilit tek-belge bir advisory lock'tur:

  - Sabit ``_id`` (``LOCK_DOC_ID``) sayesinde insert race'i ``DuplicateKeyError``
    ile çözülür (night-audit lock deseni; race-safe).
  - Lease/TTL: kilit ``expires_at`` taşır. Lock sahibi çökerse lease süresi
    dolunca bir sonraki runner kilidi devralabilir (deadlock yok).
  - Yalnızca kilit sahibi (``owner`` token) kilidi serbest bırakabilir.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from .base import LOCK_COLLECTION

logger = logging.getLogger("bootstrap.migrations.lock")

LOCK_DOC_ID = "schema_migrations"


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def acquire_lock(db, owner: str, lease_seconds: float) -> bool:
    """Advisory lock'u almaya çalışır. Alındıysa ``True``, alınamadıysa ``False``.

    Kilit serbest (yok) veya lease'i dolmuşsa devralınır; aktif ve canlıysa
    alınamaz (başka bir runner çalışıyor → çağıran atlar/bekler).
    """
    now = _now()
    expires = now + timedelta(seconds=lease_seconds)

    # 1) Kilit serbestse VEYA lease'i dolmuşsa atomik olarak devral.
    res = await db[LOCK_COLLECTION].update_one(
        {
            "_id": LOCK_DOC_ID,
            "$or": [{"active": False}, {"expires_at": {"$lt": now}}],
        },
        {
            "$set": {
                "active": True,
                "owner": owner,
                "acquired_at": now,
                "expires_at": expires,
            }
        },
    )
    if res.modified_count == 1:
        return True

    # 2) Kilit belgesi hiç yoksa oluştur (sabit _id → race DuplicateKeyError ile çözülür).
    try:
        await db[LOCK_COLLECTION].insert_one(
            {
                "_id": LOCK_DOC_ID,
                "active": True,
                "owner": owner,
                "acquired_at": now,
                "expires_at": expires,
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def renew_lock(db, owner: str, lease_seconds: float) -> bool:
    """Uzun süren migration zinciri için lease'i uzatır (yalnızca sahip)."""
    now = _now()
    expires = now + timedelta(seconds=lease_seconds)
    res = await db[LOCK_COLLECTION].update_one(
        {"_id": LOCK_DOC_ID, "owner": owner, "active": True},
        {"$set": {"expires_at": expires, "renewed_at": now}},
    )
    return res.modified_count == 1


async def release_lock(db, owner: str) -> bool:
    """Kilidi serbest bırakır (yalnızca sahip)."""
    res = await db[LOCK_COLLECTION].update_one(
        {"_id": LOCK_DOC_ID, "owner": owner},
        {"$set": {"active": False, "released_at": _now()}},
    )
    return res.modified_count == 1


async def lock_status(db) -> dict[str, Any]:
    """Ops görünürlüğü için kilit durumunu döndürür."""
    doc = await db[LOCK_COLLECTION].find_one({"_id": LOCK_DOC_ID})
    if not doc:
        return {"held": False, "owner": None, "acquired_at": None, "expires_at": None, "expired": None}
    expires = _as_aware(doc.get("expires_at"))
    active = bool(doc.get("active"))
    expired = bool(expires and expires < _now())
    return {
        "held": active and not expired,
        "active": active,
        "owner": doc.get("owner"),
        "acquired_at": _as_aware(doc.get("acquired_at")).isoformat() if _as_aware(doc.get("acquired_at")) else None,
        "expires_at": expires.isoformat() if expires else None,
        "expired": expired,
    }
