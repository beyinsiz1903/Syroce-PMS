"""QR Rozet koleksiyonları için MongoDB index'leri.

Phase D bootstrap'ta çağrılır. Best-effort: hata oluşsa da uygulamayı
durdurmaz, log'a düşer.

Index seçimi
------------
* `guest_qr_tokens`:
  - (tenant_id, token) UNIQUE — validate her tarayışta bu sorguyu yapar.
  - (tenant_id, booking_id, status) — yeni token üretilirken eski
    aktif tokenları rotated yapan update_many için.
  - (tenant_id, expires_at) — gelecekte cleanup worker'ı için.
* `pending_qr_charges`:
  - (id, tenant_id) UNIQUE — approve/reject atomic find_one_and_update'in
    ana filtresi.
  - (tenant_id, guest_user_id, status, created_at desc) — misafirin
    bekleyen şarjlarını listeleme (pending list endpoint).
  - (tenant_id, status, expires_at) — lazy expire update_many için.
"""
from __future__ import annotations

import logging

from core.database import db

logger = logging.getLogger(__name__)


async def ensure_qr_badge_indexes() -> None:
    """QR Rozet koleksiyonları için index'leri oluşturur (best-effort)."""
    try:
        await db.guest_qr_tokens.create_index(
            [("tenant_id", 1), ("token", 1)],
            unique=True,
            name="uniq_tenant_token",
        )
        await db.guest_qr_tokens.create_index(
            [("tenant_id", 1), ("booking_id", 1), ("status", 1)],
            name="idx_tenant_booking_status",
        )
        await db.guest_qr_tokens.create_index(
            [("tenant_id", 1), ("expires_at", 1)],
            name="idx_tenant_expires",
        )
        logger.info("✅ guest_qr_tokens indexes ensured")
    except Exception as e:
        logger.warning("guest_qr_tokens index error: %s", e)

    try:
        await db.pending_qr_charges.create_index(
            [("id", 1), ("tenant_id", 1)],
            unique=True,
            name="uniq_id_tenant",
        )
        await db.pending_qr_charges.create_index(
            [("tenant_id", 1), ("guest_user_id", 1), ("status", 1), ("created_at", -1)],
            name="idx_tenant_guest_status_created",
        )
        await db.pending_qr_charges.create_index(
            [("tenant_id", 1), ("status", 1), ("expires_at", 1)],
            name="idx_tenant_status_expires",
        )
        logger.info("✅ pending_qr_charges indexes ensured")
    except Exception as e:
        logger.warning("pending_qr_charges index error: %s", e)
