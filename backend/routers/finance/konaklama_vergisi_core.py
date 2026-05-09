"""
Konaklama Vergisi (Turkey Accommodation Tax) — shared core helpers.

Bu modül router katmanından bağımsız olarak çağrılabilir; checkout, night-audit
gibi servis akışları buradan tax config'i okur ve folio'ya idempotent posting
uygular.

Tek doğruluk kaynağı:
- Config: ``db.city_tax_rules`` (tenant başına bir aktif kayıt)
- Posting izi: ``db.accommodation_tax_postings`` (folio_id başına tek satır)
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db
from models.enums import ChargeCategory

logger = logging.getLogger(__name__)

DEFAULT_RATE_PERCENT = 2.0


async def load_tax_config(tenant_id: str) -> dict[str, Any]:
    """Tenant için aktif konaklama vergisi config'ini döner.

    `city_tax_rules` koleksiyonu hem yeni (`rate_percent`) hem eski
    (`tax_percentage`) alan adlarını barındırır; her iki tarafa da yazılabilen
    güvenli bir okuma sağlar.
    """
    doc = await db.city_tax_rules.find_one({"tenant_id": tenant_id, "active": True})
    if not doc:
        return {
            "tenant_id": tenant_id,
            "rate_percent": DEFAULT_RATE_PERCENT,
            "active": True,
            "auto_post": False,
            "exempt_segments": [],
        }
    doc.pop("_id", None)
    rate = doc.get("rate_percent", doc.get("tax_percentage", DEFAULT_RATE_PERCENT))
    doc["rate_percent"] = float(rate)
    doc.setdefault("auto_post", False)
    doc.setdefault("active", True)
    doc.setdefault("exempt_segments", [])
    return doc


async def get_accommodation_tax_rate(tenant_id: str) -> float:
    """Vergi oranını ondalık (ör. 0.02) olarak döner. Inactive ise 0.0."""
    cfg = await load_tax_config(tenant_id)
    if not cfg.get("active", True):
        return 0.0
    rate_pct = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))
    return round(rate_pct / 100.0, 6)


async def post_konaklama_vergisi_to_folio(
    tenant_id: str,
    folio_id: str,
    posted_by: str,
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Folyoya konaklama vergisi satırını **idempotent** olarak ekler.

    Bu fonksiyon hem HTTP endpoint'inden hem de checkout/night-audit gibi
    iç akışlardan çağrılabilir; aynı `folio_id` için ikinci çağrıda mevcut
    posting'i tespit eder ve no-op döner.

    Args:
        tenant_id: Posting yapılacak tenant.
        folio_id: Hedef folio id.
        posted_by: Audit izi için kullanıcı/sistem id.
        raise_on_error: True ise hata fırlatır; False (default) ise dict
            içinde ``ok=False`` ile gerekçeyi döndürür — best-effort
            akışlardan (checkout) güvenli çağrı için.
    """
    folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id})
    if not folio:
        msg = "Folio not found"
        if raise_on_error:
            raise ValueError(msg)
        return {"ok": False, "posted": False, "reason": "folio_not_found"}

    existing = await db.accommodation_tax_postings.find_one(
        {"tenant_id": tenant_id, "folio_id": folio_id}
    )
    if existing:
        return {
            "ok": True,
            "posted": False,
            "already_posted": True,
            "posting_id": existing.get("id"),
        }

    cfg = await load_tax_config(tenant_id)
    if not cfg.get("active", True):
        msg = "Konaklama Vergisi devre dışı"
        if raise_on_error:
            raise ValueError(msg)
        return {"ok": False, "posted": False, "reason": "inactive"}

    # v95.7: exempt_segments — booking segmentine göre vergi muafiyeti.
    exempt = [s for s in (cfg.get("exempt_segments") or []) if s]
    if exempt and folio.get("booking_id"):
        booking = await db.bookings.find_one(
            {"id": folio["booking_id"], "tenant_id": tenant_id},
            {"_id": 0, "segment": 1},
        )
        if booking and booking.get("segment") in exempt:
            return {"ok": False, "posted": False, "reason": "exempt_segment"}

    rate_percent = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))

    room_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "charge_category": ChargeCategory.ROOM.value,
            "voided": {"$ne": True},
        }
    ).to_list(length=None)
    base = round(sum(float(c.get("amount") or 0.0) for c in room_charges), 2)
    if base <= 0:
        msg = "Vergilenecek oda satırı yok"
        if raise_on_error:
            raise ValueError(msg)
        return {"ok": False, "posted": False, "reason": "no_room_charges"}

    tax_amount = round(base * (rate_percent / 100.0), 2)
    if tax_amount <= 0:
        return {"ok": False, "posted": False, "reason": "zero_tax"}

    charge_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    charge_doc = {
        "id": charge_id,
        "tenant_id": tenant_id,
        "folio_id": folio_id,
        "booking_id": folio.get("booking_id"),
        "charge_category": ChargeCategory.CITY_TAX.value,
        "description": f"Konaklama Vergisi (%{rate_percent})",
        "unit_price": tax_amount,
        "quantity": 1.0,
        "amount": tax_amount,
        "tax_amount": 0.0,
        "total": tax_amount,
        "date": now_iso,
        "posted_by": posted_by,
        "voided": False,
        "konaklama_vergisi": True,
    }
    await db.folio_charges.insert_one(charge_doc)

    posting_id = str(uuid.uuid4())
    try:
        await db.accommodation_tax_postings.insert_one(
            {
                "id": posting_id,
                "tenant_id": tenant_id,
                "folio_id": folio_id,
                "charge_id": charge_id,
                "base_amount": base,
                "rate_percent": rate_percent,
                "tax_amount": tax_amount,
                "posted_at": now_iso,
                "posted_by": posted_by,
            }
        )
    except Exception as exc:  # noqa: BLE001 — narrow check below
        # v95.7: yalnızca unique-index ihlalini idempotent kabul et;
        # diğer DB hataları (timeout, network, validation) maskelenmesin.
        from pymongo.errors import DuplicateKeyError
        if not isinstance(exc, DuplicateKeyError):
            # Charge'ı geri al ve hatayı yukarı raporla (gerçek bir
            # arıza vardır; "already_posted" gibi sessiz davranma).
            await db.folio_charges.delete_one({"id": charge_id})
            logger.exception(
                "konaklama_vergisi posting insert failed (non-duplicate): "
                "tenant=%s folio=%s",
                tenant_id, folio_id,
            )
            if raise_on_error:
                raise
            return {"ok": False, "posted": False, "reason": "posting_insert_failed"}
        # Duplicate-key race: charge'ı geri al, idempotent dön.
        await db.folio_charges.delete_one({"id": charge_id})
        existing = await db.accommodation_tax_postings.find_one(
            {"tenant_id": tenant_id, "folio_id": folio_id}
        )
        return {
            "ok": True,
            "posted": False,
            "already_posted": True,
            "posting_id": existing.get("id") if existing else None,
        }

    new_balance = round(float(folio.get("balance") or 0.0) + tax_amount, 2)
    await db.folios.update_one({"id": folio_id}, {"$set": {"balance": new_balance}})

    return {
        "ok": True,
        "posted": True,
        "posting_id": posting_id,
        "charge_id": charge_id,
        "base_amount": base,
        "tax_amount": tax_amount,
        "rate_percent": rate_percent,
    }


async def ensure_posting_index() -> None:
    """`accommodation_tax_postings` üzerinde (tenant_id, folio_id) unique index.

    Bu, idempotency'nin DB seviyesinde de garanti edilmesini sağlar — aynı
    folio'ya iki yerden eşzamanlı çağrı gelse bile yalnızca biri kazanır.
    Boot fazında bir kez çağrılması yeterli; tekrar çağrı no-op'tur.
    """
    try:
        await db.accommodation_tax_postings.create_index(
            [("tenant_id", 1), ("folio_id", 1)],
            unique=True,
            name="uniq_tenant_folio_kvb",
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("kvb posting index ensure skipped: %s", exc)
