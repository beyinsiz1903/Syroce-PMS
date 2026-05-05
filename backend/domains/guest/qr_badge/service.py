"""
QR Rozet servisi — token üretimi, doğrulama, bekleyen şarj akışı.

Tasarım notları
---------------
* **Token rotasyonu**: Her token rastgele 16 karakter base32, 60 sn TTL.
  Mobil 30 sn'de bir yeniler, böylece personel taradığında en az 30 sn
  headroom var. Aynı booking'in eski tokenları yeni biri istendiğinde
  status="rotated" olarak işaretlenir, böylece eski ekran görüntüsü
  çalışmaz (replay koruması).

* **Doğrulama**: Personel `validate` çağırdığında token aktif mi diye
  bakılır; doğrulanan token "active" kalır (tek bir tarama farklı POS'lara
  birden fazla şarj başlatabilir — örn. garson hem yemek hem içki yazıyor).
  60 sn dolduğunda status="expired" olur ve artık doğrulanamaz.

* **Bekleyen şarj** (pending_charge): Personel "şu kadara folyoya yaz"
  dediğinde DB'ye `pending_qr_charges` koleksiyonuna pending_approval ile
  yazılır, misafire push gider. 5 dakika içinde misafir onaylamazsa
  status="expired" olur — folyoya hiç yazılmaz.

* **Onay → folyo**: Misafir approve dediğinde FolioHardeningService.post_charge
  çağırılır. Folyo bulunmazsa şarj rejected oluyor (oda check-in olmamış).

Güvenlik
--------
* Tenant izolasyonu her sorguda zorunlu.
* Token üretimi `secrets.token_urlsafe` — kriptografik rastgele.
* Replay: `_consume_token` token'ın hâlâ "active" olduğunu atomik
  $set ile garanti eder (find_one_and_update).
* Misafir kendi olmayan şarjı approve edemez (booking_id eşleşmesi
  + guest e-posta eşleşmesi).
"""
from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from modules.pms_core.folio_hardening_service import FolioHardeningService
from services.expo_push import fire_and_forget_expo_push

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────
TOKEN_TTL_SECONDS = 60          # mobil 30 sn'de bir yeniler → 30 sn headroom
TOKEN_LENGTH = 16               # base32 alfabesinden
PENDING_CHARGE_TTL_SECONDS = 300  # 5 dakika
TOKEN_ALPHABET = string.ascii_uppercase + "23456789"  # base32, ambiguous chars çıkarıldı

# Outlet whitelist — POS şu an sadece bunlardan birini kabul eder.
ALLOWED_OUTLETS = {
    "restaurant": "Restoran",
    "bar": "Bar",
    "spa": "Spa",
    "pool": "Havuz",
    "minibar": "Minibar",
    "room_service": "Oda Servisi",
    "laundry": "Çamaşırhane",
    "shop": "Mağaza",
    "other": "Diğer",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _generate_token() -> str:
    """16 karakter rastgele token (base32 alfabesi, ambiguous chars hariç)."""
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


# ─────────────────────────────────────────────────────────────────────────
# TOKEN LIFECYCLE
# ─────────────────────────────────────────────────────────────────────────

async def issue_or_refresh_token(
    *,
    tenant_id: str,
    booking_id: str,
    guest_user_id: str,
) -> dict[str, Any]:
    """Yeni token üret, eski aktif tokenları rotated işaretle.

    Returns
    -------
    {
      "token": "ABCDEF...",
      "expires_at": "2026-05-05T12:34:56+00:00",
      "ttl_seconds": 60,
      "booking_id": "...",
    }
    """
    now = _utcnow()
    expires_at = now + timedelta(seconds=TOKEN_TTL_SECONDS)
    token = _generate_token()

    # Eski aktif tokenları bu booking için "rotated" yap.
    await db.guest_qr_tokens.update_many(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "status": "active",
        },
        {"$set": {"status": "rotated", "rotated_at": now.isoformat()}},
    )

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "guest_user_id": guest_user_id,
        "token": token,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "status": "active",
        "scan_count": 0,
    }
    await db.guest_qr_tokens.insert_one(doc)

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": TOKEN_TTL_SECONDS,
        "booking_id": booking_id,
    }


async def validate_token(
    *,
    tenant_id: str,
    token: str,
) -> dict[str, Any]:
    """Personel tarafından çağrılır. Token aktif mi kontrol eder; misafir
    bilgilerini döner.

    Raises
    ------
    ValueError("invalid"|"expired"|"consumed")
    """
    if not token or len(token) != TOKEN_LENGTH:
        raise ValueError("invalid")

    row = await db.guest_qr_tokens.find_one(
        {"tenant_id": tenant_id, "token": token},
        {"_id": 0},
    )
    if not row:
        raise ValueError("invalid")

    status = row.get("status")
    if status != "active":
        # Token statüleri: active / rotated / expired. Diğer her şey
        # de süre dolmuş gibi davranılır (architect Tur-15: "consumed"
        # yolu ölü koddu, kaldırıldı).
        raise ValueError("expired")

    # Süre kontrolü
    try:
        exp_dt = datetime.fromisoformat(row["expires_at"])
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=UTC)
    except Exception:
        exp_dt = _utcnow() - timedelta(seconds=1)

    if exp_dt < _utcnow():
        # Late expiration — tenbele expired bırak.
        await db.guest_qr_tokens.update_one(
            {"tenant_id": tenant_id, "token": token, "status": "active"},
            {"$set": {"status": "expired", "expired_at": _utcnow().isoformat()}},
        )
        raise ValueError("expired")

    booking_id = row.get("booking_id")
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not booking:
        raise ValueError("invalid")

    if booking.get("status") not in ("checked_in", "in_house", "confirmed"):
        # Şu an check-in olmamış misafir folyoya yazdıramaz.
        raise ValueError("not_in_house")

    # Scan count'u artır (replay metriği için).
    await db.guest_qr_tokens.update_one(
        {"tenant_id": tenant_id, "token": token},
        {
            "$inc": {"scan_count": 1},
            "$set": {"last_scanned_at": _utcnow().isoformat()},
        },
    )

    # Oda + misafir adı için zenginleştirme (POS UI'de göstermek için).
    room_no = None
    if booking.get("room_id"):
        room = await db.rooms.find_one(
            {"id": booking["room_id"], "tenant_id": tenant_id},
            {"_id": 0, "room_number": 1},
        )
        if room:
            room_no = room.get("room_number")

    guest_name = None
    if booking.get("guest_id"):
        guest = await db.guests.find_one(
            {"id": booking["guest_id"], "tenant_id": tenant_id},
            {"_id": 0, "first_name": 1, "last_name": 1, "full_name": 1},
        )
        if guest:
            guest_name = guest.get("full_name") or " ".join(
                [guest.get("first_name", ""), guest.get("last_name", "")]
            ).strip() or None

    return {
        "valid": True,
        "booking_id": booking_id,
        "guest_name": guest_name,
        "room_number": room_no,
        "expires_at": row.get("expires_at"),
        "guest_user_id": row.get("guest_user_id"),
    }


# ─────────────────────────────────────────────────────────────────────────
# PENDING CHARGE
# ─────────────────────────────────────────────────────────────────────────

async def create_pending_charge(
    *,
    tenant_id: str,
    token: str,
    outlet: str,
    amount: float,
    description: str,
    created_by_user_id: str,
    items: list[dict] | None = None,
    currency: str = "TRY",
    outlet_name: str | None = None,
) -> dict[str, Any]:
    """Personel POS'tan çağırır. Token'ı doğrular, pending_qr_charges
    koleksiyonuna ekler, misafire push gönderir.

    Raises
    ------
    ValueError("invalid_token"|"expired_token"|"invalid_amount"|"invalid_outlet")
    """
    if outlet not in ALLOWED_OUTLETS:
        raise ValueError("invalid_outlet")

    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("invalid_amount")

    if amount > 50_000:
        raise ValueError("amount_too_high")

    # Önce token'ı doğrula (booking_id + guest_user_id alıyoruz).
    try:
        validation = await validate_token(tenant_id=tenant_id, token=token)
    except ValueError as e:
        if str(e) == "expired":
            raise ValueError("expired_token") from None
        raise ValueError("invalid_token") from None

    booking_id = validation["booking_id"]
    guest_user_id = validation["guest_user_id"]
    now = _utcnow()
    charge_id = f"QRC-{uuid.uuid4().hex[:10].upper()}"

    doc = {
        "id": charge_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "guest_user_id": guest_user_id,
        "outlet": outlet,
        "outlet_name": outlet_name or ALLOWED_OUTLETS[outlet],
        "items": items or [],
        "amount": round(float(amount), 2),
        "currency": currency,
        "description": description.strip()[:240] if description else ALLOWED_OUTLETS[outlet],
        "status": "pending_approval",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=PENDING_CHARGE_TTL_SECONDS)).isoformat(),
        "approved_at": None,
        "rejected_at": None,
        "folio_charge_id": None,
        "created_by_user_id": created_by_user_id,
    }
    await db.pending_qr_charges.insert_one(doc)

    # Misafire anlık bildirim gönder (best-effort).
    # Mobil push handler `data.type` üzerinden routing yapar — `kind`
    # backward-compat için (ilerideki analytics) bırakıldı.
    try:
        fire_and_forget_expo_push(
            tenant_id,
            title=f"{doc['outlet_name']} — Onay bekliyor",
            body=f"{doc['description']} • {doc['amount']:.2f} {currency}",
            data={
                "type": "qr_charge_approval",
                "kind": "qr_charge_approval",
                "charge_id": charge_id,
                "outlet": outlet,
                "amount": doc["amount"],
                "currency": currency,
            },
            user_ids=[guest_user_id] if guest_user_id else None,
            priority="high",
        )
    except Exception:
        logger.exception("[qr_badge] push failed for charge %s", charge_id)

    doc.pop("_id", None)
    return doc


async def list_pending_charges_for_guest(
    *,
    tenant_id: str,
    guest_user_id: str,
) -> list[dict[str, Any]]:
    """Misafirin bekleyen şarjları (yeni → eski). Süresi dolanları arada
    expired olarak işaretler."""
    now = _utcnow()

    # Lazy expire — misafir listeyi açtığında geç süreli olanları kapat.
    await db.pending_qr_charges.update_many(
        {
            "tenant_id": tenant_id,
            "guest_user_id": guest_user_id,
            "status": "pending_approval",
            "expires_at": {"$lt": now.isoformat()},
        },
        {"$set": {"status": "expired", "expired_at": now.isoformat()}},
    )

    cursor = db.pending_qr_charges.find(
        {
            "tenant_id": tenant_id,
            "guest_user_id": guest_user_id,
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(50)

    return await cursor.to_list(50)


async def approve_pending_charge(
    *,
    tenant_id: str,
    charge_id: str,
    guest_user_id: str,
) -> dict[str, Any]:
    """Misafir kendi şarjını onaylar. Folyoya yazılır.

    Eşzamanlılık (architect Tur-15 kritik bulgusu): atomic
    `find_one_and_update` ile pending_approval → processing geçişi
    serileştirilir. İki paralel approve isteği sadece tek bir folyo
    postu üretir; ikinci `not_pending` alır.

    Raises
    ------
    ValueError("not_found"|"not_yours"|"not_pending"|"expired"|"folio_missing"|"folio_post_failed")
    """
    from pymongo import ReturnDocument

    now = _utcnow()

    # ── 1) Atomic claim — sadece bir kazanan ───────────────────────
    claimed = await db.pending_qr_charges.find_one_and_update(
        {
            "id": charge_id,
            "tenant_id": tenant_id,
            "guest_user_id": guest_user_id,
            "status": "pending_approval",
            "expires_at": {"$gt": now.isoformat()},
        },
        {
            "$set": {
                "status": "processing",
                "claimed_at": now.isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )

    if not claimed:
        # Neden başaramadığımızı teşhis et — kullanıcıya net hata için.
        existing = await db.pending_qr_charges.find_one(
            {"id": charge_id, "tenant_id": tenant_id},
            {"_id": 0},
        )
        if not existing:
            raise ValueError("not_found")
        if existing.get("guest_user_id") != guest_user_id:
            raise ValueError("not_yours")
        st = existing.get("status")
        if st in ("approved", "rejected", "failed", "processing"):
            # processing → başka bir paralel onay sürüyor
            raise ValueError("not_pending")
        # status=pending_approval ama claim başarısız → süresi geçmiş
        try:
            exp_dt = datetime.fromisoformat(existing["expires_at"])
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
        except Exception:
            exp_dt = now - timedelta(seconds=1)
        if exp_dt < now:
            await db.pending_qr_charges.update_one(
                {"id": charge_id, "tenant_id": tenant_id, "status": "pending_approval"},
                {"$set": {"status": "expired", "expired_at": now.isoformat()}},
            )
            raise ValueError("expired")
        # Beklenmedik — fail-safe
        raise ValueError("not_pending")

    charge = claimed
    booking_id = charge.get("booking_id")

    # ── 2) Folyo arama ─────────────────────────────────────────────
    folio = await db.folios.find_one(
        {"booking_id": booking_id, "tenant_id": tenant_id, "status": "open"},
        {"_id": 0},
    )
    if not folio:
        # Folyo kapalı/yok — claim'i geri alma, "failed" olarak kapat
        # ki ikinci bir onay denemesi olmasın (idempotency).
        await db.pending_qr_charges.update_one(
            {"id": charge_id, "tenant_id": tenant_id, "status": "processing"},
            {
                "$set": {
                    "status": "failed",
                    "failed_at": now.isoformat(),
                    "failure_reason": "folio_missing",
                }
            },
        )
        raise ValueError("folio_missing")

    # ── 3) Folyo postu ─────────────────────────────────────────────
    folio_svc = FolioHardeningService()
    try:
        posted = await folio_svc.post_charge(
            tenant_id=tenant_id,
            folio_id=folio["id"],
            booking_id=booking_id,
            charge_data={
                "category": charge.get("outlet", "other"),
                "description": (
                    f"[QR] {charge.get('outlet_name', '')} — "
                    f"{charge.get('description', '')}"
                ).strip(),
                "amount": float(charge["amount"]),
                "quantity": 1.0,
                "tax_rate": 0,
                "department": charge.get("outlet"),
            },
            posted_by=f"qr-approval:{guest_user_id}",
        )
    except Exception:
        await db.pending_qr_charges.update_one(
            {"id": charge_id, "tenant_id": tenant_id, "status": "processing"},
            {
                "$set": {
                    "status": "failed",
                    "failed_at": now.isoformat(),
                    "failure_reason": "folio_post_exception",
                }
            },
        )
        logger.exception("[qr_badge] folio post raised for %s", charge_id)
        raise ValueError("folio_post_failed") from None

    if not posted.get("success"):
        await db.pending_qr_charges.update_one(
            {"id": charge_id, "tenant_id": tenant_id, "status": "processing"},
            {
                "$set": {
                    "status": "failed",
                    "failed_at": now.isoformat(),
                    "failure_reason": "folio_post_failed",
                }
            },
        )
        raise ValueError("folio_post_failed")

    folio_charge_id = posted.get("charge", {}).get("id")
    await db.pending_qr_charges.update_one(
        {"id": charge_id, "tenant_id": tenant_id, "status": "processing"},
        {
            "$set": {
                "status": "approved",
                "approved_at": now.isoformat(),
                "folio_charge_id": folio_charge_id,
            }
        },
    )

    # Audit
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "actor_id": guest_user_id,
            "actor_role": "guest",
            "action": "qr_charge_approved",
            "entity_type": "pending_qr_charge",
            "entity_id": charge_id,
            "details": {
                "booking_id": booking_id,
                "amount": float(charge["amount"]),
                "outlet": charge.get("outlet"),
                "folio_charge_id": folio_charge_id,
            },
            "severity": "info",
            "created_at": now.isoformat(),
        })
    except Exception:
        logger.exception("[qr_badge] audit insert failed for %s", charge_id)

    return {
        "status": "approved",
        "charge_id": charge_id,
        "folio_charge_id": folio_charge_id,
        "amount": float(charge["amount"]),
        "approved_at": now.isoformat(),
    }


async def reject_pending_charge(
    *,
    tenant_id: str,
    charge_id: str,
    guest_user_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Misafir şarjı reddeder. Folyoya yazılmaz. Personele bildirim gider.

    Eşzamanlılık (architect Tur-15): atomic find_one_and_update ile
    pending_approval → rejected geçişi serileştirilir; processing
    durumundaki (onay sürmekte olan) şarj reddedilemez.
    """
    from pymongo import ReturnDocument

    now = _utcnow()

    updated = await db.pending_qr_charges.find_one_and_update(
        {
            "id": charge_id,
            "tenant_id": tenant_id,
            "guest_user_id": guest_user_id,
            "status": "pending_approval",
        },
        {
            "$set": {
                "status": "rejected",
                "rejected_at": now.isoformat(),
                "rejection_reason": (reason or "").strip()[:240] or None,
            }
        },
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )

    if not updated:
        existing = await db.pending_qr_charges.find_one(
            {"id": charge_id, "tenant_id": tenant_id},
            {"_id": 0},
        )
        if not existing:
            raise ValueError("not_found")
        if existing.get("guest_user_id") != guest_user_id:
            raise ValueError("not_yours")
        raise ValueError("not_pending")

    charge = updated

    # Personele push (best-effort).
    try:
        created_by = charge.get("created_by_user_id")
        if created_by:
            fire_and_forget_expo_push(
                tenant_id,
                title="Misafir şarjı reddetti",
                body=f"{charge.get('outlet_name', '')} • {float(charge['amount']):.2f} {charge.get('currency', 'TRY')}",
                data={
                    "type": "qr_charge_rejected",
                    "kind": "qr_charge_rejected",
                    "charge_id": charge_id,
                    "outlet": charge.get("outlet"),
                },
                user_ids=[created_by],
                priority="high",
            )
    except Exception:
        logger.exception("[qr_badge] reject push failed for %s", charge_id)

    # Audit (severity warning — incele).
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "actor_id": guest_user_id,
            "actor_role": "guest",
            "action": "qr_charge_rejected",
            "entity_type": "pending_qr_charge",
            "entity_id": charge_id,
            "details": {
                "booking_id": charge.get("booking_id"),
                "amount": float(charge["amount"]),
                "outlet": charge.get("outlet"),
                "created_by_user_id": charge.get("created_by_user_id"),
                "reason": (reason or "").strip()[:240] or None,
            },
            "severity": "warning",
            "created_at": now.isoformat(),
        })
    except Exception:
        logger.exception("[qr_badge] audit insert failed for %s", charge_id)

    return {
        "status": "rejected",
        "charge_id": charge_id,
        "rejected_at": now.isoformat(),
    }
