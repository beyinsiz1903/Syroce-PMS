import asyncio
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from core.database import db
from core.folio_ledger_service import FolioLedgerService
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_op  # v94 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["PMS / Cashier"])

_ledger = FolioLedgerService()

# Tek-açık-vardiya garantisi için partial unique index
_SHIFT_INDEX_LOCK = asyncio.Lock()
_SHIFT_INDEX_CREATED = False
_SHIFT_INDEX_LAST_ATTEMPT = 0.0
_SHIFT_INDEX_RETRY_BACKOFF_SEC = 60.0


async def _ensure_shift_indexes() -> None:
    """Tek-açık-vardiya partial unique index'i oluşturur (idempotent)."""
    global _SHIFT_INDEX_CREATED, _SHIFT_INDEX_LAST_ATTEMPT
    if _SHIFT_INDEX_CREATED:
        return
    now = time.monotonic()
    if (now - _SHIFT_INDEX_LAST_ATTEMPT) < _SHIFT_INDEX_RETRY_BACKOFF_SEC:
        return
    async with _SHIFT_INDEX_LOCK:
        if _SHIFT_INDEX_CREATED:
            return
        _SHIFT_INDEX_LAST_ATTEMPT = time.monotonic()
        try:
            await db.cashier_shifts.create_index(
                [("tenant_id", 1), ("status", 1)],
                unique=True,
                partialFilterExpression={"status": "open"},
                name="uniq_tenant_open_shift",
                background=True,
            )
            _SHIFT_INDEX_CREATED = True
            logger.info("cashier_shifts: ensured unique (tenant_id, status=open) index")
        except Exception as exc:
            logger.warning(
                "cashier_shifts: index creation failed (will retry in %ss): %s",
                int(_SHIFT_INDEX_RETRY_BACKOFF_SEC), exc,
            )


async def _find_active_booking_by_room(tenant_id: str, room_number: str) -> dict | None:
    """Odadaki aktif misafiri (checked_in / in_house) döner."""
    if not room_number:
        return None
    try:
        return await db.bookings.find_one({
            "tenant_id": tenant_id,
            "room_number": str(room_number),
            "status": {"$in": ["checked_in", "in_house"]},
        }, {"_id": 0})
    except Exception as e:
        logger.warning(f"active booking lookup failed: {e}")
        return None


async def _find_open_folio_for_booking(tenant_id: str, booking_id: str) -> dict | None:
    """Booking'e bağlı açık (status=open) folio'yu bulur, yoksa herhangi bir folio'yu döner."""
    if not booking_id:
        return None
    try:
        f = await db.folios.find_one(
            {"tenant_id": tenant_id, "booking_id": booking_id, "status": "open"},
            {"_id": 0},
        )
        if not f:
            f = await db.folios.find_one(
                {"tenant_id": tenant_id, "booking_id": booking_id},
                {"_id": 0},
            )
        return f
    except Exception as e:
        logger.warning(f"folio lookup failed: {e}")
        return None


def _safe_float(val, default=0.0):
    try:
        return float(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid numeric value: {val}")


def _safe_int(val, default=0):
    try:
        return int(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid integer value: {val}")


@router.get("/cashier/current-shift")
async def get_current_shift(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    await _ensure_shift_indexes()
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"},
        sort=[("opened_at", -1)]
    )
    if shift:
        shift["id"] = str(shift.pop("_id"))
        # Embedded transactions array (Atlas 500-koleksiyon limiti pattern'i)
        txns = list(shift.pop("transactions", []) or [])
        # En yeni önce
        txns.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return {"shift": shift, "transactions": txns[:200]}
    return {"shift": None, "transactions": []}


@router.post("/cashier/open-shift")
async def open_shift(body: dict = Body({}), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    await _ensure_shift_indexes()
    existing = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Zaten açık bir vardiya var")
    now = datetime.utcnow()
    opening_amount = _safe_float(body.get("opening_amount", 0))
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "cashier_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        "cashier_email": current_user.email,
        "opening_amount": opening_amount,
        "cash_in": 0,
        "cash_out": 0,
        "status": "open",
        "opened_at": now.isoformat(),
        "opened_by": current_user.email,
        "opened_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        "denominations": body.get("denomination_counts", body.get("denominations", {})),
    }
    try:
        await db.cashier_shifts.insert_one(doc)
    except Exception as e:
        # partial unique index yarış kazanıldı → 400
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(status_code=400, detail="Zaten açık bir vardiya var")
        raise
    doc["id"] = doc.pop("_id")
    return {"shift": doc}


@router.post("/cashier/close-shift")
async def close_shift(body: dict = Body({}), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if not shift:
        raise HTTPException(status_code=404, detail="Acik vardiya bulunamadi")
    now = datetime.utcnow()
    counted_amount = _safe_float(body.get("counted_amount", 0))
    expected = shift.get("opening_amount", 0) + shift.get("cash_in", 0) - shift.get("cash_out", 0)
    difference = counted_amount - expected
    await db.cashier_shifts.update_one(
        {"_id": shift["_id"], "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "closed",
            "closed_at": now.isoformat(),
            "closing_amount": counted_amount,
            "expected_amount": expected,
            "difference": difference,
            "closing_denominations": body.get("denomination_counts", body.get("denominations", {})),
            "closed_by": current_user.email,
            "closed_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        }}
    )
    return {
        "status": "closed",
        "counted_amount": counted_amount,
        "expected_amount": expected,
        "difference": difference,
        "closed_at": now.isoformat(),
        "closed_by": current_user.email,
        "closed_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
    }


@router.post("/cashier/handover-shift")
async def handover_shift(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if not shift:
        raise HTTPException(status_code=404, detail="Acik vardiya bulunamadi")

    target_email = body.get("target_email", "").strip()
    target_password = body.get("target_password", "").strip()
    if not target_email or not target_password:
        raise HTTPException(status_code=400, detail="Devir alacak kullanicinin e-posta ve sifresi gerekli")

    if target_email == current_user.email:
        raise HTTPException(status_code=400, detail="Vardiyayi kendinize devredemezsiniz")

    target_user = await db.users.find_one(
        {"email": target_email, "tenant_id": current_user.tenant_id}
    )
    if not target_user:
        raise HTTPException(status_code=401, detail="Kullanici bulunamadi veya ayni otele ait degil")

    stored_hash = target_user.get("hashed_password") or target_user.get("password_hash") or ""
    if not pwd_ctx.verify(target_password, stored_hash):
        raise HTTPException(status_code=401, detail="Sifre hatali. Devir alacak kisi kendi sifresini girmeli")

    target_name = target_user.get("name") or target_user.get("full_name") or target_email
    now = datetime.utcnow()
    expected = shift.get("opening_amount", 0) + shift.get("cash_in", 0) - shift.get("cash_out", 0)

    await db.cashier_shifts.update_one(
        {"_id": shift["_id"], "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "handed_over",
            "closed_at": now.isoformat(),
            "closing_amount": expected,
            "expected_amount": expected,
            "difference": 0,
            "closed_by": current_user.email,
            "closed_by_name": current_user.name if hasattr(current_user, "name") else current_user.email,
            "handover_to_email": target_email,
            "handover_to_name": target_name,
            "handover_at": now.isoformat(),
            "handover_note": body.get("note", ""),
        }}
    )
    new_doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "cashier_name": target_name,
        "cashier_email": target_email,
        "opening_amount": expected,
        "cash_in": 0,
        "cash_out": 0,
        "status": "open",
        "opened_at": now.isoformat(),
        "opened_by": target_email,
        "opened_by_name": target_name,
        "previous_shift_id": str(shift["_id"]),
        "handover_from_email": current_user.email,
        "handover_from_name": current_user.name if hasattr(current_user, "name") else current_user.email,
    }
    await db.cashier_shifts.insert_one(new_doc)
    new_doc["id"] = new_doc.pop("_id")
    return {
        "status": "handed_over",
        "previous_shift_closed": True,
        "new_shift": new_doc,
        "target_name": target_name,
    }


@router.post("/cashier/manual-transaction")
async def manual_transaction(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    """
    Manuel kasa hareketi (Paid-Out / Cash-In / düzeltme).
    Body: { amount, direction: 'in'|'out', method: 'cash'|'card'..., description, type? }
    """
    from domains.pms.cashier_service import record_cash_transaction
    amount = _safe_float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Tutar 0'dan büyük olmalı")
    direction = (body.get("direction") or "").lower()
    if direction not in {"in", "out"}:
        raise HTTPException(status_code=400, detail="Yön 'in' veya 'out' olmalı")
    method = (body.get("method") or "cash").lower()
    description = (body.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Açıklama zorunludur")
    txn_type = body.get("type") or ("paid_out" if direction == "out" else "manual_in")

    # Aktif vardiya zorunlu (tüm manuel işlemler için)
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if not shift:
        raise HTTPException(status_code=409, detail="Aktif kasa vardiyası yok. Önce 'Vardiya Aç' işlemini yapın.")

    txn = await record_cash_transaction(
        tenant_id=current_user.tenant_id,
        amount=amount,
        method=method,
        direction=direction,
        description=description,
        txn_type=txn_type,
        ref_type="manual",
        ref_id=None,
        created_by=current_user.email,
        created_by_name=getattr(current_user, "name", None) or current_user.email,
    )
    return {"ok": True, "transaction": txn}


@router.get("/cashier/shift-history")
async def shift_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    # transactions array büyük olabilir → liste görünümünde dahil etme
    cursor = db.cashier_shifts.find(
        {"tenant_id": current_user.tenant_id},
        {"transactions": 0}
    ).sort("opened_at", -1).skip(skip).limit(limit)
    shifts = await cursor.to_list(limit)
    for s in shifts:
        s["id"] = str(s.pop("_id"))
    total = await db.cashier_shifts.count_documents({"tenant_id": current_user.tenant_id})
    return {"shifts": shifts, "total": total}


# Atlas 500 koleksiyon limitini aşmamak için laundry_orders'ı da
# tenant_settings dokümanı içinde array olarak tutuyoruz.

async def _get_laundry_orders_array(tenant_id: str) -> list[dict]:
    settings = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "laundry_orders": 1}
    )
    return ((settings or {}).get("laundry_orders") or [])


@router.get("/laundry/orders")
async def get_laundry_orders(skip: int = 0, limit: int = 100, status: str = None, current_user: User = Depends(get_current_user)):
    orders = await _get_laundry_orders_array(current_user.tenant_id)
    if status:
        orders = [o for o in orders if o.get("status") == status]
    # En yeni önce
    orders.sort(key=lambda o: o.get("created_at") or "", reverse=True)
    return {"orders": orders[skip:skip + limit]}


@router.post("/laundry/orders")
async def create_laundry_order(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    if not body.get("room_number"):
        raise HTTPException(status_code=400, detail="Oda numarasi gerekli")
    if not body.get("items") or len(body["items"]) == 0:
        raise HTTPException(status_code=400, detail="En az bir urun gerekli")
    now = datetime.utcnow()
    total = sum(_safe_float(i.get("total", 0)) for i in body["items"])

    # Aktif misafir/folio autofill (frontend göndermediyse de bağlamak için)
    booking_id = body.get("booking_id") or ""
    folio_id = body.get("folio_id") or ""
    guest_name = body.get("guest_name") or ""
    if not booking_id:
        active = await _find_active_booking_by_room(current_user.tenant_id, body.get("room_number", ""))
        if active:
            booking_id = active.get("id") or active.get("booking_id") or ""
            if not guest_name:
                guest_name = active.get("guest_name") or active.get("primary_guest_name") or ""
    if booking_id and not folio_id:
        folio = await _find_open_folio_for_booking(current_user.tenant_id, booking_id)
        if folio:
            folio_id = folio.get("id") or ""

    doc = {
        "id": str(uuid.uuid4()),
        "room_number": body.get("room_number", ""),
        "guest_name": guest_name,
        "service_type": body.get("service_type", "wash_iron"),
        "items": body.get("items", []),
        "total": total,
        "notes": body.get("notes", ""),
        "priority": body.get("priority", "normal"),
        "status": "pending",
        "booking_id": booking_id,
        "folio_id": folio_id,
        "folio_charged": False,
        "folio_entry_id": None,
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$setOnInsert": {"tenant_id": current_user.tenant_id}, "$push": {"laundry_orders": doc}},
        upsert=True,
    )
    return doc


@router.patch("/laundry/orders/{order_id}")
async def update_laundry_order(order_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    update_fields = {k: v for k, v in body.items() if k not in ("id", "tenant_id")}
    update_fields["updated_at"] = datetime.utcnow().isoformat()
    set_doc = {f"laundry_orders.$.{k}": v for k, v in update_fields.items()}
    result = await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id, "laundry_orders.id": order_id},
        {"$set": set_doc},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi")

    # status=delivered → folio'ya LAUNDRY charge (idempotent)
    folio_charge_result = None
    if update_fields.get("status") == "delivered":
        # Atomik claim: yalnızca folio_charged=false ise true'ya çevir.
        # Concurrent isteklerden sadece biri ledger'a charge POST eder.
        claim = await db.tenant_settings.update_one(
            {
                "tenant_id": current_user.tenant_id,
                "laundry_orders": {"$elemMatch": {"id": order_id, "folio_charged": {"$ne": True}}},
            },
            {"$set": {"laundry_orders.$.folio_charged": True}},
        )
        # Ilgili siparisi tekrar oku
        orders = await _get_laundry_orders_array(current_user.tenant_id)
        order = next((o for o in orders if o.get("id") == order_id), None)
        if order and claim.modified_count > 0:
            booking_id = order.get("booking_id") or ""
            folio_id = order.get("folio_id") or ""
            # Eski siparişler için lookup
            if not booking_id:
                active = await _find_active_booking_by_room(
                    current_user.tenant_id, order.get("room_number", "")
                )
                if active:
                    booking_id = active.get("id") or active.get("booking_id") or ""
            if booking_id and not folio_id:
                folio = await _find_open_folio_for_booking(current_user.tenant_id, booking_id)
                if folio:
                    folio_id = folio.get("id") or ""

            if folio_id and booking_id:
                try:
                    items_desc = ", ".join(
                        f"{i.get('name', '?')} x{i.get('quantity', 1)}"
                        for i in (order.get("items") or [])
                    )
                    desc = f"Çamaşırhane - Oda {order.get('room_number', '?')}"
                    if items_desc:
                        desc += f" ({items_desc})"
                    posted = await _ledger.post_charge(
                        tenant_id=current_user.tenant_id,
                        folio_id=folio_id,
                        booking_id=booking_id,
                        amount=_safe_float(order.get("total", 0)),
                        description=desc,
                        charge_code="LAUNDRY",
                        idempotency_key=f"laundry:{order_id}",
                        posted_by=current_user.email,
                        metadata={
                            "laundry_order_id": order_id,
                            "service_type": order.get("service_type"),
                            "items": order.get("items", []),
                        },
                    )
                    # folio_charged zaten claim aşamasında set edilmişti;
                    # burada entry_id/folio_id/booking_id metadata'yı yansıt
                    await db.tenant_settings.update_one(
                        {"tenant_id": current_user.tenant_id, "laundry_orders.id": order_id},
                        {"$set": {
                            "laundry_orders.$.folio_entry_id": posted.get("entry_id"),
                            "laundry_orders.$.folio_id": folio_id,
                            "laundry_orders.$.booking_id": booking_id,
                        }},
                    )
                    folio_charge_result = {
                        "charged": True,
                        "amount": _safe_float(order.get("total", 0)),
                        "entry_id": posted.get("entry_id"),
                        "new_balance": posted.get("new_balance"),
                    }
                except Exception as e:
                    # Charge başarısız → claim'i geri al ki yeniden denenebilsin
                    logger.error(f"laundry folio charge failed for {order_id}: {e}")
                    await db.tenant_settings.update_one(
                        {"tenant_id": current_user.tenant_id, "laundry_orders.id": order_id},
                        {"$set": {"laundry_orders.$.folio_charged": False}},
                    )
                    folio_charge_result = {"charged": False, "error": str(e)}
            else:
                # Booking/folio bulunamadı → claim'i geri al
                await db.tenant_settings.update_one(
                    {"tenant_id": current_user.tenant_id, "laundry_orders.id": order_id},
                    {"$set": {"laundry_orders.$.folio_charged": False}},
                )
                folio_charge_result = {
                    "charged": False,
                    "reason": "no_active_booking_or_folio",
                }

    return {
        "id": order_id,
        "status": update_fields.get("status", "updated"),
        "folio_charge": folio_charge_result,
    }


@router.delete("/laundry/orders/{order_id}")
async def delete_laundry_order(order_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    result = await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$pull": {"laundry_orders": {"id": order_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi")
    return {"id": order_id, "status": "deleted"}


# ═══════════════════════════════════════════════════════════════
# Çamaşırhane Fiyat Yönetimi (tenant_settings.laundry_items)
# Atlas 500-koleksiyon limiti nedeniyle ayrı koleksiyon yerine
# mevcut tenant_settings dokümanı içinde tutulur.
# ═══════════════════════════════════════════════════════════════

DEFAULT_LAUNDRY_ITEMS = [
    {"code": "shirt", "name": "Gomlek", "price": 30.0},
    {"code": "pants", "name": "Pantolon", "price": 40.0},
    {"code": "suit", "name": "Takim Elbise", "price": 80.0},
    {"code": "dress", "name": "Elbise", "price": 60.0},
    {"code": "tshirt", "name": "Tisort", "price": 20.0},
    {"code": "underwear", "name": "Ic Camasiri", "price": 15.0},
    {"code": "socks", "name": "Corap (Cift)", "price": 10.0},
    {"code": "coat", "name": "Mont/Kaban", "price": 100.0},
    {"code": "skirt", "name": "Etek", "price": 35.0},
    {"code": "scarf", "name": "Atki/Sal", "price": 25.0},
]


def _seed_default_items() -> list[dict]:
    now = datetime.utcnow().isoformat()
    return [
        {
            "id": str(uuid.uuid4()),
            "code": it["code"],
            "name": it["name"],
            "price": it["price"],
            "active": True,
            "created_at": now,
        }
        for it in DEFAULT_LAUNDRY_ITEMS
    ]


async def _get_laundry_items_array(tenant_id: str) -> list[dict]:
    """tenant_settings'ten laundry_items dizisini döner; yoksa default'ları seed eder."""
    settings = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "laundry_items": 1}
    )
    items = (settings or {}).get("laundry_items")
    if items is None:
        seeded = _seed_default_items()
        try:
            # Race-safe seed: yalnızca alan mevcut değilse ekle (concurrent
            # $push ile veri kaybı olmasın diye filter'a $exists:false koyduk)
            await db.tenant_settings.update_one(
                {"tenant_id": tenant_id, "laundry_items": {"$exists": False}},
                {"$setOnInsert": {"tenant_id": tenant_id}, "$set": {"laundry_items": seeded}},
                upsert=True,
            )
            # Yeniden oku (başka bir istek seed etmiş olabilir)
            settings2 = await db.tenant_settings.find_one(
                {"tenant_id": tenant_id}, {"_id": 0, "laundry_items": 1}
            )
            return ((settings2 or {}).get("laundry_items")) or seeded
        except Exception as e:
            logger.warning(f"laundry_items seed failed: {e}; returning defaults in-memory")
            return seeded
    return items


@router.get("/laundry/items")
async def get_laundry_items(current_user: User = Depends(get_current_user)):
    """Tenant'a ait çamaşırhane fiyat listesi (tenant_settings.laundry_items)."""
    items = await _get_laundry_items_array(current_user.tenant_id)
    items_sorted = sorted(items, key=lambda x: (x.get("name") or "").lower())
    return {"items": items_sorted}


@router.post("/laundry/items")
async def create_laundry_item(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    code = (body.get("code") or "").strip().lower()
    name = (body.get("name") or "").strip()
    price = _safe_float(body.get("price", 0))
    if not code or not name:
        raise HTTPException(status_code=400, detail="Kod ve ad zorunludur")
    if price < 0:
        raise HTTPException(status_code=400, detail="Fiyat negatif olamaz")

    items = await _get_laundry_items_array(current_user.tenant_id)
    if any((it.get("code") or "").lower() == code for it in items):
        raise HTTPException(status_code=409, detail=f"'{code}' kodu zaten mevcut")

    new_item = {
        "id": str(uuid.uuid4()),
        "code": code,
        "name": name,
        "price": price,
        "active": bool(body.get("active", True)),
        "created_at": datetime.utcnow().isoformat(),
        "created_by": current_user.email,
    }
    await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$setOnInsert": {"tenant_id": current_user.tenant_id}, "$push": {"laundry_items": new_item}},
        upsert=True,
    )
    return new_item


@router.put("/laundry/items/{item_id}")
async def update_laundry_item(item_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    set_fields = {}
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Ad bos olamaz")
        set_fields["name"] = name
    if "price" in body:
        price = _safe_float(body.get("price", 0))
        if price < 0:
            raise HTTPException(status_code=400, detail="Fiyat negatif olamaz")
        set_fields["price"] = price
    if "active" in body:
        set_fields["active"] = bool(body["active"])
    if not set_fields:
        raise HTTPException(status_code=400, detail="Guncellenecek alan yok")
    set_fields["updated_at"] = datetime.utcnow().isoformat()

    update_doc = {f"laundry_items.$.{k}": v for k, v in set_fields.items()}
    result = await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id, "laundry_items.id": item_id},
        {"$set": update_doc},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Urun bulunamadi")
    return {"id": item_id, **set_fields}


@router.delete("/laundry/items/{item_id}")
async def delete_laundry_item(item_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    result = await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$pull": {"laundry_items": {"id": item_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Urun bulunamadi")
    return {"id": item_id, "deleted": True}


# ═══════════════════════════════════════════════════════════════
# Aktif misafir lookup (oda no → guest_name + booking_id)
# ═══════════════════════════════════════════════════════════════

@router.get("/bookings/active-by-room/{room_number}")
async def get_active_booking_by_room(room_number: str, current_user: User = Depends(get_current_user)):
    """Verilen oda no için checked_in/in_house misafiri döner."""
    booking = await _find_active_booking_by_room(current_user.tenant_id, room_number)
    if not booking:
        return {"found": False}
    folio = await _find_open_folio_for_booking(
        current_user.tenant_id, booking.get("id") or booking.get("booking_id") or ""
    )
    return {
        "found": True,
        "booking_id": booking.get("id") or booking.get("booking_id") or "",
        "guest_name": booking.get("guest_name") or booking.get("primary_guest_name") or "",
        "room_number": booking.get("room_number") or room_number,
        "check_in": booking.get("check_in"),
        "check_out": booking.get("check_out"),
        "status": booking.get("status"),
        "folio_id": (folio or {}).get("id") or "",
    }

