"""
pos_core

Auto-split sub-router (shared imports/classes inlined).
"""

"""
PMS / POS & F&B Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
    with_resource_locks,
)
from core.database import db
from core.outbox_service import POS_CHARGE_POSTED, enqueue_outbox_event
from core.security import (
    get_current_user,
    security,
)
from domains.pms.pos_extensions._idem import ensure_compound_unique, ensure_idem_index
from models.enums import ChargeCategory, FolioStatus
from models.schemas import CreatePOSTransactionRequest, FolioCharge, User
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_op  # v89 DW

try:
    from websocket_server import broadcast_kitchen_orders
except Exception:  # pragma: no cover

    async def broadcast_kitchen_orders(tenant_id: str, orders: Any):
        return None


async def _get_active_kitchen_orders(tenant_id: str, statuses: list[str] | None = None):
    query = {"tenant_id": tenant_id}
    if statuses:
        query["status"] = {"$in": statuses}
    else:
        query["status"] = {"$in": ["pending", "preparing"]}
    return await db.kitchen_orders.find(query, {"_id": 0}).sort([("priority", -1), ("ordered_at", 1)]).to_list(200)


async def _next_kitchen_order_number(tenant_id: str) -> int:
    last_order = await db.kitchen_orders.find({"tenant_id": tenant_id}).sort("order_number", -1).limit(1).to_list(1)
    if not last_order:
        return 1
    try:
        return int(last_order[0].get("order_number", 0)) + 1
    except (TypeError, ValueError):
        return 1


async def _broadcast_kitchen_queue(tenant_id: str) -> None:
    try:
        orders = await _get_active_kitchen_orders(tenant_id)
        await broadcast_kitchen_orders(tenant_id, orders)
    except Exception as exc:
        logging.warning(f"Kitchen broadcast failed: {exc}")


# ── Adisyon (check) numbering + business date ──────────────────────────────
# Restaurant adisyon numbers must be sequential per outlet and reset every
# business day, mirroring how Turkish F&B outlets number their physical checks.
# A naive read-max+1 races under concurrent waiters; we use an atomic
# find_one_and_update counter keyed by (tenant_id, outlet_id, business_date).

_CATEGORY_STATION = {
    "food": "hot_kitchen",
    "appetizer": "cold_kitchen",
    "salad": "cold_kitchen",
    "dessert": "pastry",
    "bakery": "pastry",
    "beverage": "bar",
    "alcohol": "bar",
    "wine": "bar",
    "cocktail": "bar",
}

_ADISYON_COUNTER_INDEX_READY = False


async def _ensure_adisyon_counter_index() -> None:
    """Best-effort unique index so concurrent upserts can't fork the counter."""
    global _ADISYON_COUNTER_INDEX_READY
    if _ADISYON_COUNTER_INDEX_READY:
        return
    try:
        await db.pos_adisyon_counters.create_index(
            [("tenant_id", 1), ("outlet_id", 1), ("business_date", 1)],
            unique=True,
            name="uq_adisyon_counter",
        )
        _ADISYON_COUNTER_INDEX_READY = True
    except Exception as exc:  # pragma: no cover - index race/permission
        logging.warning(f"adisyon counter index ensure failed: {exc}")


def _station_for_category(category: Any) -> str:
    raw = getattr(category, "value", category)
    return _CATEGORY_STATION.get(str(raw).lower(), "hot_kitchen")


async def _get_pos_business_date(tenant_id: str) -> str:
    """Current business date (hotel-day) for the tenant.

    Reuses the night-audit business_date stored on tenant_settings so the
    adisyon reset boundary matches the hotel's operational day rollover rather
    than naive UTC midnight. Falls back to UTC date when unset.
    """
    try:
        settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "business_date": 1})
        if settings and settings.get("business_date"):
            return str(settings["business_date"])
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning(f"business_date lookup failed: {exc}")
    return datetime.now(UTC).date().isoformat()


async def _next_adisyon_number(tenant_id: str, outlet_id: str | None, business_date: str) -> int:
    """Atomic, daily-resetting, per-outlet sequential adisyon number."""
    await _ensure_adisyon_counter_index()
    key = {
        "tenant_id": tenant_id,
        "outlet_id": outlet_id or "default",
        "business_date": business_date,
    }
    for _ in range(3):
        try:
            doc = await db.pos_adisyon_counters.find_one_and_update(
                key,
                {
                    "$inc": {"seq": 1},
                    "$setOnInsert": {"created_at": datetime.now(UTC)},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return int(doc["seq"])
        except DuplicateKeyError:
            # Concurrent first-insert raced us; the row now exists, retry $inc.
            continue
    # Last resort: plain increment without upsert (row guaranteed to exist).
    doc = await db.pos_adisyon_counters.find_one_and_update(key, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER)
    return int(doc["seq"]) if doc else 1


async def _auto_kds_and_kot(order: "POSOrder", tenant_id: str, ordered_by: str) -> None:
    """On a freshly-created POS order, auto-create the KDS ticket and enqueue the
    kitchen KOT print job(s). Best-effort: a failure here must never roll back the
    already-durable order — but the gap stays visible (KDS broadcast / print_jobs
    status). Idempotent via the order id so a replay never double-fires.
    """
    items = [
        {
            "name": it.item_name,
            "quantity": it.quantity,
            "station": _station_for_category(it.category),
            "special_instructions": None,
        }
        for it in order.order_items
    ]
    if not items:
        return

    table_label = order.table_number or (f"Oda {order.booking_id}" if order.booking_id else None)

    # 1. KDS ticket (idempotent on the order id).
    try:
        idemp = f"pos-{order.id}"
        existing = await db.kitchen_orders.find_one({"tenant_id": tenant_id, "idempotency_key": idemp}, {"_id": 0})
        if not existing:
            kds_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "order_number": await _next_kitchen_order_number(tenant_id),
                "adisyon_number": order.adisyon_number,
                "business_date": order.business_date,
                "outlet_id": order.outlet_id,
                "table_number": table_label,
                "room_number": None,
                "priority": "normal",
                "status": "pending",
                "station": items[0]["station"] if len(items) == 1 else "mixed",
                "items": items,
                "notes": order.notes,
                "source_pos_order_id": order.id,
                "idempotency_key": idemp,
                "ordered_by": ordered_by,
                "ordered_at": datetime.now(UTC).isoformat(),
            }
            try:
                await db.kitchen_orders.insert_one(kds_doc)
            except DuplicateKeyError:
                pass  # concurrent create raced us; ticket already exists
            await _broadcast_kitchen_queue(tenant_id)
    except Exception as exc:  # pragma: no cover - best effort
        logging.warning(f"auto KDS create failed for order {order.id}: {exc}")

    # 2. KOT print job(s) — one ticket per kitchen station, best-effort. Failures
    # surface in print_jobs status (operators see a printer that needs setup).
    try:
        from ..pos_extensions.pos_print_spool import (
            enqueue_print_job,
            resolve_kot_printer,
        )

        by_station: dict[str, list[dict]] = {}
        for it in items:
            by_station.setdefault(it["station"], []).append(it)
        for station, station_items in by_station.items():
            try:
                # Resolve the physical printer for this (outlet, station) pair so
                # the same station can target a different printer per outlet.
                routing = await resolve_kot_printer(tenant_id, order.outlet_id, station)
                routing_warning = None
                if not routing.get("matched"):
                    routing_warning = f"({order.outlet_id or 'default'}/{station}) icin kayitli yazici yok; '{routing['printer_id']}' istasyon adina yonlendirildi"
                    logging.warning("auto KOT for order %s: %s", order.id, routing_warning)
                await enqueue_print_job(
                    tenant_id=tenant_id,
                    kind="kitchen",
                    payload={
                        "station": station,
                        "table": table_label,
                        "adisyon_number": order.adisyon_number,
                        "business_date": order.business_date,
                        "items": station_items,
                    },
                    idempotency_key=f"kot-{order.id}-{station}",
                    printer_id=routing["printer_id"],
                    created_by=ordered_by,
                    auto_dispatch=True,
                    routing_warning=routing_warning,
                )
            except Exception as exc:  # pragma: no cover - best effort
                logging.warning(f"auto KOT print failed for order {order.id}/{station}: {exc}")
    except Exception as exc:  # pragma: no cover - import/best effort
        logging.warning(f"auto KOT print unavailable for order {order.id}: {exc}")


def calculate_table_duration(opened_at: Any) -> int:
    """Return open-table duration in minutes; 0 on bad input."""
    if not opened_at:
        return 0
    try:
        if isinstance(opened_at, str):
            dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        else:
            dt = opened_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int((datetime.now(UTC) - dt).total_seconds() // 60)
    except Exception:
        return 0


def create_default_table_layout() -> list[dict[str, Any]]:
    """Return a generic 8-table layout for first-time setup."""
    return [{"id": str(uuid.uuid4()), "number": str(i + 1), "capacity": 4, "status": "available", "zone": "main"} for i in range(8)]


async def recalculate_folio_balance(folio_id: str, tenant_id: str) -> float:
    """F&B post sonrası bakiye yeniden hesabı — core helper'a delege (fail-closed)."""
    from core.utils import calculate_folio_balance

    return await calculate_folio_balance(folio_id, tenant_id)


async def _folio_balance_in_session(folio_id: str, tenant_id: str, session=None) -> float:
    """Ledger'dan (charges − payments) bakiye — transaction içinde session ile.

    `core.utils.calculate_folio_balance` ile aynı formül; tek farkı session
    geçirebilmesi (snapshot okuması transaction'ın gördüğü committed + kendi
    yazdığı satırları kapsar). Bakiye bir cache'tir, ledger tek doğruluk
    kaynağıdır — $inc YOK, her zaman ledger'dan türetilir.
    """
    ch_pipe = [
        {"$match": {"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total", "$amount"]}}}},
    ]
    pay_pipe = [
        {"$match": {"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    ch_doc = await db.folio_charges.aggregate(ch_pipe, session=session).to_list(1)
    pay_doc = await db.payments.aggregate(pay_pipe, session=session).to_list(1)
    total_charges = float(ch_doc[0]["total"]) if ch_doc else 0.0
    total_payments = float(pay_doc[0]["total"]) if pay_doc else 0.0
    return round(total_charges - total_payments, 2)


async def _ensure_pos_atomicity_indexes(folio_post: bool) -> None:
    """POS create-order için gereken benzersiz partial index'leri kur (fail-closed).

    - pos_orders (tenant_id, idempotency_key): retry/çift-dokunmada tek sipariş.
    - folio_charges (tenant_id, source_pos_order_id, line_no): kısmi-hata
      sonrası DB seviyesinde çift-postlama engeli.

    Her iki index de PARTIAL: legacy dokümanlar bu alanları taşımaz; partial
    olmasaydı index kurulumu sessizce patlar (fake-green). Helper gerçek hatada
    `raise` eder (fail-closed); caller bunu 503'e çevirir — sessizce idempotent
    olmayan/yaris-guvensiz yazıma DÜŞMEZ.
    """
    await ensure_idem_index(db.pos_orders, index_name="ux_pos_orders_tenant_idemp")
    if folio_post:
        await ensure_compound_unique(
            db.folio_charges,
            [("tenant_id", 1), ("source_pos_order_id", 1), ("line_no", 1)],
            partial_filter={"source_pos_order_id": {"$type": "string"}},
            name="ux_folio_charges_pos_source",
        )


async def _persist_pos_order_atomic(
    *,
    order_doc: dict,
    charge_docs: list[dict],
    folio_id: str | None,
    tenant_id: str,
    idempotency_key: str | None,
    outbox_payload: dict | None = None,
) -> tuple[dict, bool]:
    """Sipariş kaydı + IC outbox olayını tek transaction'da yazar (intent durable).

    Dönüş: (effective_order, was_idempotent_replay).

    Task #389 — Outbox/Compensation: hot path artık folyoyu SENKRON mutasyona
    UĞRATMAZ. Sadece (a) idempotent sipariş insert'i ve (b) `pos.charge.posted.v1`
    IC outbox olayını AYNI transaction'da yazar; gerçek folio_charge postlaması +
    bakiye recalc'ı async, garantili, idempotent consumer (core.pos_folio_consumer)
    tarafından yapılır.

    - Idempotency: pos_orders'a insert; aynı (tenant, idempotency_key) varsa
      DuplicateKeyError → mevcut sipariş replay olarak döner, outbox olayı
      TEKRAR ENQUEUE EDİLMEZ (ilk başarılı transaction zaten durable yazdı; ayrıca
      outbox'ın kendi idempotency_key'i çift-enqueue'yu da dedup eder).
    - Atomicity: sipariş + outbox insert'i tek transaction; yarıda hata → ikisi
      de geri alınır (sipariş var ama niyet yok / niyet var ama sipariş yok olmaz).
    - Hot path folyoya yazmadığı için folio lock'a gerek YOK (contention azaltıldı);
      eşzamanlı postlamaların serileşmesi ve ledger'dan tek-stratejiyle bakiye
      recalc'ı consumer tarafında ele alınır.
    """

    async def _txn(session) -> tuple[dict, bool]:
        # 1. Idempotency gate — order insert.
        try:
            await db.pos_orders.insert_one(dict(order_doc), session=session)
        except DuplicateKeyError:
            existing = await db.pos_orders.find_one(
                {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
                {"_id": 0},
                session=session,
            )
            # Replay: prior order (and its IC outbox event) already durable.
            return existing or order_doc, True

        # 2. Durable intent — enqueue the IC folio-posting event in the SAME
        #    transaction as the order. The async consumer applies the charges +
        #    balance recalc idempotently (and guards closed folios at apply time).
        if folio_id and charge_docs:
            await enqueue_outbox_event(
                db,
                session=session,
                tenant_id=tenant_id,
                event_type=POS_CHARGE_POSTED,
                entity_type="folio",
                entity_id=order_doc["id"],
                payload=outbox_payload or {},
            )

        clean = dict(order_doc)
        clean.pop("_id", None)
        return clean, False

    # Hot path folyoyu mutasyona uğratmadığı için kaynak lock'u gerekmez; yine de
    # sipariş + outbox insert'inin all-or-nothing olması için lock'suz transaction
    # kullanırız.
    try:
        return await with_resource_locks(
            client=db.client,
            db=db,
            tenant_id=tenant_id,
            locks_collection="folio_locks",
            resources=[],
            callback=_txn,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code == 112 or "WriteConflict" in str(exc):
            raise HTTPException(
                status_code=409,
                detail="Folyo eş zamanlı güncellendi; lütfen tekrar deneyin.",
            )
        if not is_replica_set_unavailable(exc):
            raise
        if not standalone_fallback_allowed():
            # Production-safe default: refuse rather than risk a non-atomic
            # order/intent write.
            raise HTTPException(
                status_code=503,
                detail=("POS sipariş yazımı atomik garanti sağlayamıyor (Mongo replica set gerekli)."),
            )
        # Dev opt-in: best-effort non-transactional fallback. The pos_orders
        # unique index still provides idempotency; the outbox idempotency_key
        # dedups the enqueue. Only the all-or-nothing guarantee is relaxed.
        return await _txn(None)


def get_menu_recommendation(_guest_profile: dict | None = None) -> list[str]:
    """Heuristic menu recommendation stub — to be replaced by ML model."""
    return ["Chef's Special", "Local Wine Pairing", "Seasonal Dessert"]


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


# ── Inline Models ──

from enum import Enum


class POSCategory(str, Enum):
    FOOD = "food"
    BEVERAGE = "beverage"
    ALCOHOL = "alcohol"
    DESSERT = "dessert"
    APPETIZER = "appetizer"


class POSMenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_name: str
    category: POSCategory
    unit_price: float
    available: bool = True


class POSOrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    item_name: str
    category: POSCategory
    quantity: int
    unit_price: float
    total_price: float


class POSOrderItemRequest(BaseModel):
    item_id: str
    quantity: int = 1


class POSOrderCreateRequest(BaseModel):
    booking_id: str | None = None
    folio_id: str | None = None
    order_items: list[POSOrderItemRequest]
    # Waiter-terminal context — outlet drives per-outlet adisyon numbering and
    # the table/notes/payment metadata are carried onto the order + KOT ticket.
    outlet_id: str | None = None
    table_number: str | None = None
    notes: str | None = None
    payment_method: str | None = None  # room_charge, cash, card
    # Guest signature (base64 data URL) captured on the touch terminal when a
    # check is charged to the room — proof of authorization.
    guest_signature: str | None = None
    # Idempotency: client supplies a fresh key per genuine order attempt; the
    # same key on a retry / double-tap / network replay returns the original
    # order (and its single charge set) instead of double-posting.
    idempotency_key: str | None = None


class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str | None = None
    guest_id: str | None = None
    folio_id: str | None = None
    outlet_id: str | None = None
    table_number: str | None = None
    adisyon_number: int | None = None
    business_date: str | None = None
    payment_method: str | None = None
    guest_signature: str | None = None
    notes: str | None = None
    order_items: list[POSOrderItem]
    subtotal: float
    tax_amount: float
    total_amount: float
    status: str = "pending"  # pending, completed, cancelled
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment_type: str  # in, out, adjustment
    quantity: int
    reason: str
    notes: str | None = None


class UpdateOrderStatusRequest(BaseModel):
    status: str  # pending, preparing, ready, served
    notes: str | None = None


class TableLayout(BaseModel):
    """Table layout for restaurant floor plan"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    outlet_id: str
    table_number: str
    seats: int
    position_x: float  # X coordinate on floor plan
    position_y: float  # Y coordinate on floor plan
    shape: str = "rectangle"  # rectangle, circle, square
    width: float = 100
    height: float = 100
    status: str = "available"  # available, occupied, reserved, dirty
    current_transaction_id: str | None = None
    server_assigned: str | None = None


class KitchenOrderItem(BaseModel):
    """Kitchen order item for KDS"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_id: str
    table_number: str
    item_name: str
    quantity: int
    special_instructions: str | None = None
    station: str  # hot_kitchen, cold_kitchen, bar, pastry
    status: str = "pending"  # pending, preparing, ready, served
    priority: str = "normal"  # urgent, high, normal
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ready_at: datetime | None = None
    served_at: datetime | None = None


class Alert(BaseModel):
    """Universal alert model"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    alert_type: str  # housekeeping, maintenance, ota, overbooking, rms, ar, marketplace, review
    priority: str  # low, normal, high, urgent
    title: str
    description: str
    source_module: str
    source_id: str | None = None
    assigned_to: str | None = None
    status: str = "unread"  # unread, read, acknowledged, resolved
    action_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None


# ============= PHOTO UPLOAD (KAT HİZMETLERİ İÇİN) =============


# rbac-allow: cache-rbac — POS F&B orders operasyonel

# ============= HOTEL INVENTORY MANAGEMENT =============


# ============= CHANNEL MANAGER ENHANCEMENTS =============


# ============= HOTEL INTERNAL MESSAGING =============


# ===== 5. MESSAGING MODULE (WHATSAPP / SMS / AUTO MESSAGES) =====


# NOTE: GET /pos/orders moved to pos_router.py — canonical implementation
# reads from pos_menu_transactions (same source as Z-report) with legacy
# fallback to db.transactions and db.pos_orders. The duplicate that used to
# live here would have shadowed the canonical version with stale data.

# ============= MOBILE ENDPOINTS — MOVED to domains/pms/mobile_router.py =============

# ============================================================================
# FAZ 1 - HIZLI EKLENEBİLİR ÖZELLIKLER
# ============================================================================
# ============= GM DASHBOARD & ANALYTICS — MOVED to domains/revenue/analytics_router.py =============

# ============= MAINTENANCE TASKS ENDPOINT =============


# 2. GET /api/pos/mobile/order/{order_id} - Get detailed order info


# 3. PUT /api/pos/mobile/order/{order_id}/status - Update order status


# 4. GET /api/pos/mobile/order-history - Get order history with filters


# ============================================================================
# INVENTORY/STOCK MOBILE ENDPOINTS
# ============================================================================

# 5. GET /api/pos/mobile/inventory-movements - Get stock movements


# 6. GET /api/pos/mobile/stock-levels - Get current stock levels


# 7. GET /api/pos/mobile/low-stock-alerts - Get low stock alerts


# 8. POST /api/pos/mobile/stock-adjust - Adjust stock (Warehouse/F&B Manager only)


# ============================================================================
# APPROVALS MODULE - Onay Mekanizmaları
# ============================================================================

# Approval Models


_ME_RECOMMENDATIONS = {
    "Stars": "Yıldız ürün - menüde öne çıkar, kaliteyi koru, fiyat esnekliğini test et",
    "Plowhorses": "İş ineği - maliyeti düşür (porsiyon/tedarikçi), üst-satış kombinasyonu öner",
    "Puzzles": "Bulmaca - tanıtım/sunum iyileştir, menüde üst sıraya taşı, ad değiştir",
    "Dogs": "Köpek - menüden çıkar veya tarifi yeniden tasarla",
}


@cached(ttl=180, key_prefix="menu_engineering")
async def _build_menu_engineering(
    tenant_id: str,
    start_iso: str,
    end_iso: str,
    outlet_id: str | None,
) -> dict[str, Any]:
    """Sprint 33 R9: Kasavana-Smith menu engineering matrisi.

    Popülerlik eşiği = (1 / N) × %70 (klasik menu-mix ortalaması).
    Karlılık eşiği = ağırlıklı ortalama katkı payı (CM/birim).
    """
    # 1) Menü kataloğu — fiyat + maliyet için
    catalog_raw = await db.pos_menu_items.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)
    catalog: dict[str, dict[str, Any]] = {}
    for it in catalog_raw:
        nm = it.get("name") or it.get("item_name")
        if not nm:
            continue
        catalog[nm] = {
            "price": float(it.get("price", 0) or 0),
            "cost": float(it.get("cost", 0) or 0),
            "menu_category": it.get("category") or "Diğer",
        }

    # 2) Sipariş satırlarını topla
    order_filter: dict[str, Any] = {
        "tenant_id": tenant_id,
        "created_at": {"$gte": start_iso, "$lte": end_iso},
    }
    if outlet_id:
        order_filter["outlet_id"] = outlet_id

    orders = await db.pos_orders.find(order_filter, {"_id": 0, "items": 1}).to_list(20000)

    agg: dict[str, dict[str, float]] = {}
    for order in orders:
        for line in order.get("items", []) or []:
            nm = line.get("item_name") or line.get("name") or "Bilinmiyor"
            qty = float(line.get("quantity", 1) or 1)
            line_price = float(line.get("price", 0) or 0)
            row = agg.setdefault(nm, {"qty": 0.0, "revenue": 0.0})
            row["qty"] += qty
            row["revenue"] += qty * line_price

    if not agg:
        return {
            "period": {"start_date": start_iso[:10], "end_date": end_iso[:10]},
            "outlet_id": outlet_id,
            "stars": 0,
            "plowhorses": 0,
            "puzzles": 0,
            "dogs": 0,
            "menu_items": [],
            "thresholds": {"popularity_pct": 0, "avg_cm_per_unit": 0},
            "totals": {"items": 0, "units_sold": 0, "revenue": 0.0, "contribution_margin": 0.0},
            "cost_estimation_used": False,
            "cost_estimated_items": 0,
        }

    # 3) Birim ekonomisi — gerçek katalog maliyeti varsa onu kullan; yoksa %35
    # food-cost varsayımına düş ve item'i `cost_estimated=True` ile dürüstçe işaretle
    # (sahte kesin maliyet sunma; rapor tahmini olduğunu açıkça bildirir).
    enriched = []
    total_qty = 0.0
    total_cm = 0.0
    for nm, row in agg.items():
        cat = catalog.get(nm, {})
        unit_price = cat.get("price") or (row["revenue"] / row["qty"] if row["qty"] else 0)
        _real_cost = cat.get("cost")
        cost_estimated = not (isinstance(_real_cost, (int, float)) and not isinstance(_real_cost, bool) and _real_cost > 0)
        unit_cost = (unit_price * 0.35) if cost_estimated else float(_real_cost)
        cost_total = unit_cost * row["qty"]
        cm_total = row["revenue"] - cost_total
        cm_per_unit = cm_total / row["qty"] if row["qty"] else 0
        margin_pct = (cm_total / row["revenue"] * 100) if row["revenue"] else 0
        enriched.append(
            {
                "_name": nm,
                "_menu_cat": cat.get("menu_category", "Diğer"),
                "_qty": row["qty"],
                "_revenue": row["revenue"],
                "_cost": cost_total,
                "_cm_total": cm_total,
                "_cm_unit": cm_per_unit,
                "_margin_pct": margin_pct,
                "_unit_price": unit_price,
                "_unit_cost": unit_cost,
                "_cost_estimated": cost_estimated,
            }
        )
        total_qty += row["qty"]
        total_cm += cm_total

    # 4) Eşikler
    n_items = len(enriched)
    pop_threshold_pct = (1.0 / n_items) * 70.0  # menu-mix klasik %70
    cm_threshold = (total_cm / total_qty) if total_qty else 0

    # 5) Sınıflandırma
    out_items = []
    counts = {"Stars": 0, "Plowhorses": 0, "Puzzles": 0, "Dogs": 0}
    for e in enriched:
        pop_pct = (e["_qty"] / total_qty * 100) if total_qty else 0
        high_pop = pop_pct >= pop_threshold_pct
        high_cm = e["_cm_unit"] >= cm_threshold
        if high_pop and high_cm:
            cls = "Stars"
        elif high_pop and not high_cm:
            cls = "Plowhorses"
        elif not high_pop and high_cm:
            cls = "Puzzles"
        else:
            cls = "Dogs"
        counts[cls] += 1
        out_items.append(
            {
                "item_name": e["_name"],
                "menu_category": e["_menu_cat"],
                "category": cls,  # frontend bunu rozet için kullanıyor
                "classification": cls,
                "quantity_sold": int(e["_qty"]),
                "revenue": round(e["_revenue"], 2),
                "unit_price": round(e["_unit_price"], 2),
                "unit_cost": round(e["_unit_cost"], 2),
                "cost_estimated": e["_cost_estimated"],
                "contribution_margin": round(e["_cm_total"], 2),
                "cm_per_unit": round(e["_cm_unit"], 2),
                "profit_margin": round(e["_margin_pct"], 1),
                "popularity_pct": round(pop_pct, 2),
                "recommendation": _ME_RECOMMENDATIONS[cls],
            }
        )

    # Yıldızlar önce, köpekler sonra
    rank = {"Stars": 0, "Puzzles": 1, "Plowhorses": 2, "Dogs": 3}
    out_items.sort(key=lambda x: (rank[x["classification"]], -x["revenue"]))

    return {
        "period": {"start_date": start_iso[:10], "end_date": end_iso[:10]},
        "outlet_id": outlet_id,
        "stars": counts["Stars"],
        "plowhorses": counts["Plowhorses"],
        "puzzles": counts["Puzzles"],
        "dogs": counts["Dogs"],
        "menu_items": out_items,
        "cost_estimation_used": any(e["_cost_estimated"] for e in enriched),
        "cost_estimated_items": sum(1 for e in enriched if e["_cost_estimated"]),
        "thresholds": {
            "popularity_pct": round(pop_threshold_pct, 2),
            "avg_cm_per_unit": round(cm_threshold, 2),
            "method": "Kasavana-Smith (1/N × 70% popülerlik, ağırlıklı CM ortalaması)",
        },
        "totals": {
            "items": n_items,
            "units_sold": int(total_qty),
            "revenue": round(sum(e["_revenue"] for e in enriched), 2),
            "contribution_margin": round(total_cm, 2),
        },
    }


router = APIRouter(prefix="/api", tags=["PMS / POS & F&B"])


# ── POST /pos/transaction ──
@router.post("/pos/transaction")
async def create_pos_transaction(
    request: CreatePOSTransactionRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Create POS transaction"""
    transaction = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "transaction_date": datetime.now(UTC).date().isoformat(),
        "transaction_time": datetime.now(UTC).time().isoformat(),
        "amount": request.amount,
        "payment_method": request.payment_method,
        "folio_id": request.folio_id,
        "status": "completed",
        "processed_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }

    transaction_copy = transaction.copy()
    await db.pos_transactions.insert_one(transaction_copy)
    return transaction


# ── POST /pos/check-split ──
@router.post("/pos/check-split")
async def split_check(
    transaction_id: str,
    split_type: str,  # equal, by_item, custom
    split_count: int | None = 2,
    # `embed=True` so the body MUST be `{ "split_details": {...} }` rather
    # than the bare dict — matches the e2e contract and avoids the
    # ambiguous "whole body becomes split_details" FastAPI default that
    # caused 400 "no valid item indices" regressions (CI 2026-05-25).
    split_details: dict | None = Body(default=None, embed=True),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """
    Split restaurant check
    - Equal split (N ways)
    - By item
    - Custom amounts
    """
    transaction = await db.pos_transactions.find_one({"id": transaction_id, "tenant_id": current_user.tenant_id})

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    total_amount = transaction.get("total_amount", 0)
    # Item field is stored as 'order_items' on POS orders; older transactions used 'items'.
    items = transaction.get("order_items") or transaction.get("items", [])
    # Legacy fallback: transactions closed before the v2 close handler
    # snapshotted order_items into the txn doc may have no items field.
    # Fetch from pos_orders via order_id (tenant-scoped) so split_check
    # still works for old data. This is the safety net for the same-class
    # bug fixed in pos_fnb_service_v2.complete_order (CI 2026-05-25).
    if not items:
        order_id = transaction.get("order_id")
        if order_id:
            parent_order = await db.pos_orders.find_one(
                {"id": order_id, "tenant_id": current_user.tenant_id},
                {"order_items": 1, "_id": 0},
            )
            if parent_order:
                items = parent_order.get("order_items", []) or []

    split_transactions = []

    if split_type == "equal":
        # Equal split
        amount_per_split = total_amount / split_count
        for i in range(split_count):
            split_transactions.append({"split_number": i + 1, "amount": round(amount_per_split, 2), "items": "All items (split equally)"})

    elif split_type == "by_item":
        # By item (from split_details)
        if not split_details:
            raise HTTPException(status_code=400, detail="split_details required for by_item split")

        # Schema-agnostic field resolution: v2 close writes
        # `{item_name, unit_price, quantity, total}`; legacy POS rows used
        # `{name, price}`. split_check must read BOTH (CI 2026-05-25 D —
        # without this, valid indices produced 0.0 splits silently).
        def _line_amount(it):
            for key in ("total", "price"):
                v = it.get(key)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
            unit = it.get("unit_price")
            qty = it.get("quantity", 1)
            if unit is not None:
                try:
                    return float(unit) * float(qty or 1)
                except (TypeError, ValueError):
                    pass
            return 0.0

        def _line_label(it):
            return it.get("item_name") or it.get("name")

        total_raw_indices = 0
        total_valid_indices = 0
        for split_num, item_indices in split_details.items():
            safe_indices = []
            for raw_idx in item_indices or []:
                total_raw_indices += 1
                try:
                    idx_int = int(raw_idx)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx_int < len(items):
                    safe_indices.append(idx_int)
                    total_valid_indices += 1
            split_amount = sum(_line_amount(items[i]) for i in safe_indices)
            split_items = [_line_label(items[i]) for i in safe_indices]
            try:
                split_number = int(split_num)
            except (TypeError, ValueError):
                split_number = len(split_transactions) + 1
            split_transactions.append({"split_number": split_number, "amount": round(split_amount, 2), "items": split_items})

        if total_raw_indices > 0 and total_valid_indices == 0:
            raise HTTPException(status_code=400, detail="by_item split: no valid item indices in split_details (all out of range or non-numeric)")

    elif split_type == "custom":
        # Custom amounts
        if not split_details:
            raise HTTPException(status_code=400, detail="split_details required for custom split")

        for split_num, amount in split_details.items():
            try:
                amount_f = float(amount)
            except (TypeError, ValueError):
                amount_f = 0.0
            try:
                split_number = int(split_num)
            except (TypeError, ValueError):
                split_number = len(split_transactions) + 1
            split_transactions.append({"split_number": split_number, "amount": round(amount_f, 2), "items": "Custom split"})

    # Update original transaction.
    # SECURITY: tenant_id filter required (same bug class as KDS IDOR fixed
    # earlier in this batch). The earlier find_one above already enforces
    # tenant scope, so this update logically cannot cross tenants — but
    # leaving the filter open invites regressions if a future caller skips
    # the find_one. Keep both call-sites tenant-scoped.
    await db.pos_transactions.update_one({"id": transaction_id, "tenant_id": current_user.tenant_id}, {"$set": {"status": "split", "split_type": split_type, "split_count": len(split_transactions)}})

    splits_total = round(sum(float(s.get("amount", 0) or 0) for s in split_transactions), 2)
    expected_total = round(float(total_amount or 0), 2)
    total_validation = {
        "expected": expected_total,
        "actual": splits_total,
        "delta": round(splits_total - expected_total, 2),
        "match": abs(splits_total - expected_total) < 0.01,
    }

    return {
        "success": True,
        "original_transaction_id": transaction_id,
        "original_amount": expected_total,
        "split_type": split_type,
        "split_count": len(split_transactions),
        "splits": split_transactions,
        "total_validation": total_validation,
    }


# ── POST /pos/transfer-table ──
@router.post("/pos/transfer-table")
async def transfer_table(
    from_table: str,
    to_table: str,
    outlet_id: str,
    transfer_all: bool = True,
    items_to_transfer: list[Any] | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Transfer items from one table to another with hardened consistency.
    Note: Real atomic Mongo transactions are not used here due to replica set constraints.
    Instead, this relies on a "best-effort defensive update" approach with tenant-scoped
    update filters and status checks to prevent concurrent modification.
    """
    tenant_id = current_user.tenant_id

    # 1. Fetch Source Transaction
    source_transaction = await db.pos_transactions.find_one({
        "tenant_id": tenant_id, 
        "outlet_id": outlet_id, 
        "table_number": from_table, 
        "status": "open"
    })

    if not source_transaction:
        raise HTTPException(status_code=404, detail=f"No active transaction found for table {from_table}")

    source_id = source_transaction.get("_id")
    source_uuid = source_transaction.get("id")

    if transfer_all:
        # Transfer entire table.
        # SECURITY: defense-in-depth with tenant_id filter.
        await db.pos_transactions.update_one(
            {"_id": source_id, "tenant_id": tenant_id, "status": "open"}, 
            {"$set": {
                "table_number": to_table,
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": current_user.username
            }}
        )

        return {
            "success": True,
            "message": f"Table {from_table} transferred to {to_table}",
            "transaction_id": source_uuid,
            "items_transferred": len(source_transaction.get("items", [])),
        }
    else:
        # Partial Transfer
        if not items_to_transfer:
            raise HTTPException(status_code=400, detail="items_to_transfer list is required for partial transfer")

        src_items = source_transaction.get("items", [])
        transferred_items = []
        remaining_items = []

        # Handle both list[int] (legacy index) and list[dict] (quantity-based)
        transfer_requests = {}
        for req in items_to_transfer:
            if isinstance(req, int):
                transfer_requests[req] = None  # None means transfer all quantity
            elif isinstance(req, dict) and "index" in req:
                transfer_requests[req["index"]] = req.get("quantity", None)

        for idx, item in enumerate(src_items):
            if idx in transfer_requests:
                requested_qty = transfer_requests[idx]
                current_qty = item.get("quantity", 1)
                
                if requested_qty is not None:
                    if requested_qty <= 0:
                        raise HTTPException(status_code=400, detail="quantity must be > 0")
                    if requested_qty > current_qty:
                        raise HTTPException(status_code=400, detail="quantity exceeds source item quantity")
                    
                    if requested_qty < current_qty:
                        # Partial quantity transfer
                        transfer_item = item.copy()
                        transfer_item["quantity"] = requested_qty
                        transferred_items.append(transfer_item)
                        
                        remain_item = item.copy()
                        remain_item["quantity"] = current_qty - requested_qty
                        remaining_items.append(remain_item)
                    else:
                        # Full quantity transfer
                        transferred_items.append(item)
                else:
                    # Full quantity transfer
                    transferred_items.append(item)
            else:
                remaining_items.append(item)

        if not transferred_items:
            raise HTTPException(status_code=400, detail="None of the specified items were found in the transaction")

        def _recalc_totals(items_list):
            sub = sum(float(i.get("price", 0)) * float(i.get("quantity", 1)) for i in items_list)
            tax = sum(float(i.get("tax_amount", 0)) for i in items_list) if any("tax_amount" in i for i in items_list) else (sub * 0.18)
            return round(sub + tax, 2)

        new_source_total = _recalc_totals(remaining_items)
        new_target_total_delta = _recalc_totals(transferred_items)

        # We must carefully read the target and either insert or update
        target_transaction = await db.pos_transactions.find_one({
            "tenant_id": tenant_id, 
            "outlet_id": outlet_id, 
            "table_number": to_table, 
            "status": "open"
        })

        target_id = None
        if target_transaction:
            # Append items, aggregate duplicates if item_id matches (optional but good for POS)
            target_items = target_transaction.get("items", [])
            for t_item in transferred_items:
                merged = False
                if t_item.get("item_id"):
                    for existing in target_items:
                        if existing.get("item_id") == t_item.get("item_id"):
                            existing["quantity"] = existing.get("quantity", 1) + t_item.get("quantity", 1)
                            # recalculate item tax if exists
                            if "tax_amount" in existing and "tax_amount" in t_item:
                                existing["tax_amount"] += t_item.get("tax_amount", 0)
                            merged = True
                            break
                if not merged:
                    target_items.append(t_item)
            
            new_target_total = _recalc_totals(target_items)

            # Atomic update on target
            res = await db.pos_transactions.update_one(
                {"_id": target_transaction["_id"], "tenant_id": tenant_id},
                {"$set": {
                    "items": target_items, 
                    "total_amount": new_target_total, 
                    "updated_at": datetime.now(UTC).isoformat()
                }}
            )
            if res.modified_count == 0:
                raise HTTPException(status_code=409, detail="Target table state changed unexpectedly.")
            
            target_id = target_transaction.get("id")
        else:
            # Create new target transaction
            target_id = str(uuid.uuid4())
            new_doc = {
                "id": target_id,
                "tenant_id": tenant_id,
                "outlet_id": outlet_id,
                "table_number": to_table,
                "status": "open",
                "items": transferred_items,
                "total_amount": new_target_total_delta,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "created_by": current_user.username,
            }
            await db.pos_transactions.insert_one(new_doc)

        # Atomic update on source
        # Only modify if it hasn't been closed/mutated unexpectedly
        src_res = await db.pos_transactions.update_one(
            {"_id": source_id, "tenant_id": tenant_id, "status": "open"}, 
            {"$set": {
                "items": remaining_items, 
                "total_amount": new_source_total, 
                "updated_at": datetime.now(UTC).isoformat()
            }}
        )

        if src_res.modified_count == 0:
            # Revert target if possible, though strict atomic is hard without session. 
            # In a replica-set, we would wrap this all in session.start_transaction().
            raise HTTPException(status_code=409, detail="Source table state changed during transfer. Operation aborted or partially failed.")

        return {
            "success": True,
            "message": f"Partially transferred {len(transferred_items)} items to table {to_table}",
            "source_transaction_id": source_uuid,
            "target_transaction_id": target_id,
            "items_transferred": len(transferred_items),
        }


# ── POST /pos/happy-hour ──
@router.post("/pos/happy-hour")
async def apply_happy_hour_discount(
    outlet_id: str,
    discount_pct: float,
    start_time: str,  # HH:MM
    end_time: str,
    applicable_categories: list[str] = [],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """
    Apply happy hour discount
    - Time-based automatic discount
    - Category-specific (e.g., only beverages)
    """
    happy_hour = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "outlet_id": outlet_id,
        "discount_pct": discount_pct,
        "start_time": start_time,
        "end_time": end_time,
        "applicable_categories": applicable_categories,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db.happy_hour_rules.insert_one(happy_hour)

    return {"success": True, "happy_hour_id": happy_hour["id"], "message": f"Happy hour created: {discount_pct}% off {start_time}-{end_time}"}


# ── GET /pos/table-layout/{outlet_id} ──
@router.get("/pos/table-layout/{outlet_id}")
async def get_table_layout(outlet_id: str, current_user: User = Depends(get_current_user)):
    """
    Get restaurant floor plan with table layout
    - Visual table arrangement
    - Table status (available, occupied, reserved, dirty)
    - Current transactions
    """
    tables = []
    raw_tables = await db.table_layouts.find({"tenant_id": current_user.tenant_id, "outlet_id": outlet_id}).to_list(length=None)
    # Batch-fetch all open transactions referenced by tables
    txn_ids = [t.get("current_transaction_id") for t in raw_tables if t.get("current_transaction_id")]
    txns_by_id: dict = {}
    if txn_ids:
        async for tx in db.pos_transactions.find(
            {"id": {"$in": txn_ids}, "tenant_id": current_user.tenant_id},
            {"_id": 0, "id": 1, "total_amount": 1, "guests": 1},
        ):
            txns_by_id[tx["id"]] = tx
    for table in raw_tables:
        transaction = txns_by_id.get(table.get("current_transaction_id"))

        tables.append(
            {
                "id": table.get("id"),
                "table_number": table.get("table_number"),
                "seats": table.get("seats"),
                "position": {"x": table.get("position_x"), "y": table.get("position_y")},
                "shape": table.get("shape"),
                "width": table.get("width"),
                "height": table.get("height"),
                "status": table.get("status"),
                "server_assigned": table.get("server_assigned"),
                "current_bill": round(transaction.get("total_amount", 0), 2) if transaction else 0,
                "guest_count": transaction.get("guests", 0) if transaction else 0,
                "duration_minutes": calculate_table_duration(table) if table.get("status") == "occupied" else 0,
            }
        )

    # If no tables exist, only auto-create when outlet is real (avoid 500 for unknown ids)
    if not tables:
        outlet = await db.pos_outlets.find_one(
            {
                "id": outlet_id,
                "tenant_id": current_user.tenant_id,
            }
        )
        if not outlet:
            raise HTTPException(status_code=404, detail="Outlet bulunamadi")
        default_tables = create_default_table_layout(current_user.tenant_id, outlet_id)
        for table_data in default_tables:
            await db.table_layouts.insert_one(table_data)
            tables.append(
                {
                    "id": table_data["id"],
                    "table_number": table_data["table_number"],
                    "seats": table_data["seats"],
                    "position": {"x": table_data["position_x"], "y": table_data["position_y"]},
                    "shape": table_data["shape"],
                    "width": table_data["width"],
                    "height": table_data["height"],
                    "status": "available",
                    "server_assigned": None,
                    "current_bill": 0,
                    "guest_count": 0,
                    "duration_minutes": 0,
                }
            )

    return {
        "outlet_id": outlet_id,
        "total_tables": len(tables),
        "available": sum(1 for t in tables if t["status"] == "available"),
        "occupied": sum(1 for t in tables if t["status"] == "occupied"),
        "reserved": sum(1 for t in tables if t["status"] == "reserved"),
        "tables": tables,
    }


# ── POST /pos/table-layout/update ──
@router.post("/pos/table-layout/update")
async def update_table_layout(
    table_id: str,
    position_x: float | None = None,
    position_y: float | None = None,
    seats: int | None = None,
    server_assigned: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """Update table layout - drag & drop positioning"""
    updates = {}
    if position_x is not None:
        updates["position_x"] = position_x
    if position_y is not None:
        updates["position_y"] = position_y
    if seats is not None:
        updates["seats"] = seats
    if server_assigned is not None:
        updates["server_assigned"] = server_assigned

    await db.table_layouts.update_one({"id": table_id, "tenant_id": current_user.tenant_id}, {"$set": updates})

    return {"success": True, "message": "Table layout updated"}


# ── GET /pos/split-bill-ui/{transaction_id} ──
@router.get("/pos/split-bill-ui/{transaction_id}")
async def get_split_bill_ui_data(transaction_id: str, current_user: User = Depends(get_current_user)):
    """
    Get transaction data formatted for split bill UI
    - Line items with selection
    - Multiple payment methods
    - Split strategies
    """
    transaction = await db.pos_transactions.find_one({"id": transaction_id, "tenant_id": current_user.tenant_id})

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    items = transaction.get("items", [])

    # Format items for split UI
    formatted_items = []
    for idx, item in enumerate(items):
        formatted_items.append(
            {
                "index": idx,
                "name": item.get("name"),
                "quantity": item.get("quantity", 1),
                "unit_price": item.get("price", 0),
                "total": item.get("price", 0) * item.get("quantity", 1),
                "selected_for_split": False,
                "split_assignee": None,  # Which guest (1, 2, 3, etc.)
            }
        )

    return {
        "transaction_id": transaction_id,
        "table_number": transaction.get("table_number"),
        "total_amount": transaction.get("total_amount", 0),
        "items": formatted_items,
        "split_strategies": [
            {"id": "equal", "name": "Equal Split", "description": "Split bill equally among N people"},
            {"id": "by_item", "name": "By Item", "description": "Assign items to specific people"},
            {"id": "percentage", "name": "By Percentage", "description": "Split by custom percentages"},
            {"id": "custom", "name": "Custom Amount", "description": "Enter custom amounts for each person"},
        ],
        "payment_methods": ["cash", "card", "mobile", "room_charge"],
    }


# ── POST /pos/room-charge-restrictions ──
@router.post("/pos/room-charge-restrictions")
async def set_room_charge_restrictions(
    max_daily_charge: float | None = None,
    require_supervisor_approval: bool = False,
    allowed_categories: list[str] | None = None,
    restricted_hours: dict[str, str] | None = None,  # {"start": "02:00", "end": "06:00"}
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """
    Room charge restrictions
    - Max daily charge limit
    - Supervisor approval required
    - Category restrictions (e.g., no alcohol)
    - Time restrictions (e.g., no charges 2am-6am)
    """
    restrictions = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "max_daily_charge": max_daily_charge,
        "require_supervisor_approval": require_supervisor_approval,
        "allowed_categories": allowed_categories or ["food", "beverage", "minibar"],
        "restricted_hours": restricted_hours,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }

    # Store or update restrictions
    existing = await db.pos_room_charge_restrictions.find_one({"tenant_id": current_user.tenant_id})

    if existing:
        await db.pos_room_charge_restrictions.update_one({"tenant_id": current_user.tenant_id}, {"$set": restrictions})
    else:
        await db.pos_room_charge_restrictions.insert_one(restrictions)

    return {"success": True, "message": "Room charge restrictions updated", "restrictions": restrictions}


# ── POST /pos/validate-room-charge ──
@router.post("/pos/validate-room-charge")
async def validate_room_charge(
    booking_id: str,
    amount: float,
    category: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """
    Validate if room charge is allowed
    - Check against restrictions
    - Return validation result
    """
    # Get restrictions
    restrictions = await db.pos_room_charge_restrictions.find_one({"tenant_id": current_user.tenant_id})

    validation_result = {"allowed": True, "reason": None, "requires_approval": False}

    if restrictions:
        # Check max daily charge
        if restrictions.get("max_daily_charge"):
            # Get today's charges
            today = datetime.now().date().isoformat()
            daily_total = 0
            async for charge in db.folio_charges.find({"booking_id": booking_id, "date": {"$gte": today}}):
                daily_total += charge.get("total", 0)

            if daily_total + amount > restrictions["max_daily_charge"]:
                validation_result["allowed"] = False
                validation_result["reason"] = f"Exceeds daily limit of ${restrictions['max_daily_charge']}"
                return validation_result

        # Check allowed categories
        if restrictions.get("allowed_categories"):
            if category not in restrictions["allowed_categories"]:
                validation_result["allowed"] = False
                validation_result["reason"] = f"Category '{category}' not allowed for room charge"
                return validation_result

        # Check restricted hours
        if restrictions.get("restricted_hours"):
            current_time = datetime.now().time()
            start_time = datetime.strptime(restrictions["restricted_hours"]["start"], "%H:%M").time()
            end_time = datetime.strptime(restrictions["restricted_hours"]["end"], "%H:%M").time()

            if start_time <= current_time <= end_time:
                validation_result["allowed"] = False
                validation_result["reason"] = f"Room charges restricted between {restrictions['restricted_hours']['start']}-{restrictions['restricted_hours']['end']}"
                return validation_result

        # Check if approval required
        if restrictions.get("require_supervisor_approval"):
            validation_result["requires_approval"] = True

    return validation_result


# ── POST /pos/create-order ──
@router.post("/pos/create-order")
async def create_pos_order(
    data: POSOrderCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("pos")),  # v92 DW
):
    """Create a POS order with detailed items.

    Atomic + idempotent + race-safe folio posting (Task #360):
    - `idempotency_key` (per genuine attempt) → retry/double-tap/network replay
      returns the original order + single charge set, never a duplicate.
    - order insert + folio_charge inserts + balance recalc run in ONE Mongo
      transaction → no half-posted charges.
    - concurrent posts to the SAME folio serialize on a folio lock → the final
      balance (recalculated from the ledger, never $inc) is correct.
    """
    current_user = await get_current_user(credentials)
    tenant_id = current_user.tenant_id

    if not data.order_items:
        raise HTTPException(status_code=400, detail="Order items required")

    # Normalize idempotency key (bounded so it can't be abused as storage).
    idem_raw = data.idempotency_key
    idempotency_key = idem_raw.strip() if isinstance(idem_raw, str) and idem_raw.strip() else None
    if idempotency_key and len(idempotency_key) > 128:
        raise HTTPException(status_code=400, detail="idempotency_key too long (max 128)")

    # Idempotency pre-check — a genuine retry/double-tap must NOT consume a fresh
    # adisyon number, re-create the KDS ticket, or re-print the KOT. The atomic
    # persist below still defends the rare concurrent-first-submit race.
    if idempotency_key:
        prior = await db.pos_orders.find_one({"tenant_id": tenant_id, "idempotency_key": idempotency_key}, {"_id": 0})
        if prior:
            return {
                "success": True,
                "message": "POS order created",
                "idempotent_replay": True,
                "charge_status": "queued" if prior.get("folio_id") else "none",
                "order_id": prior.get("id"),
                "order": prior,
            }

    folio_id = data.folio_id

    # Resolve booking + guest. When posting to a folio we need its booking_id
    # (FolioCharge requires it) and we validate the folio exists for the tenant
    # so charges can't be orphaned onto a non-existent / cross-tenant folio.
    guest_id = None
    booking_id = data.booking_id
    if data.booking_id:
        booking = await db.bookings.find_one({"id": data.booking_id, "tenant_id": tenant_id})
        if booking:
            guest_id = booking["guest_id"]

    # Waiter-terminal room charge: the touch terminal only knows the in-house
    # booking_id (folio ids are behind a finance-gated endpoint). When the check
    # is charged to the room we resolve the booking's OPEN folio here so the
    # charges actually post — instead of silently creating an unposted order.
    if not folio_id and booking_id and (data.payment_method or "").lower() == "room_charge":
        open_folio = await db.folios.find_one(
            {
                "booking_id": booking_id,
                "tenant_id": tenant_id,
                "status": FolioStatus.OPEN.value,
            },
            {"_id": 0, "id": 1},
        )
        if not open_folio:
            raise HTTPException(
                status_code=404,
                detail="Bu rezervasyon için açık folyo bulunamadı (odaya yazılamaz)",
            )
        folio_id = open_folio["id"]

    folio_booking_id = booking_id
    if folio_id:
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id})
        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")
        # Closed-folio guard (parity with the other folio-charge endpoints,
        # e.g. folio_service.post_charge / finance refund-void): a charge must
        # never be posted to a folio that is no longer open (closed /
        # checked-out / transferred / voided). Posting to a non-open folio
        # creates financial inconsistency.
        folio_status = folio.get("status") or FolioStatus.OPEN.value
        if folio_status != FolioStatus.OPEN.value:
            raise HTTPException(
                status_code=400,
                detail="Kapalı/çıkışı yapılmış folyoya POS hesabı kesilemez",
            )
        folio_booking_id = folio.get("booking_id") or booking_id or ""
        if guest_id is None and folio.get("guest_id"):
            guest_id = folio.get("guest_id")

    # Build order items
    order_items_list = []
    subtotal = 0.0

    for item_data in data.order_items:
        # Get menu item
        menu_item = await db.pos_menu_items.find_one({"id": item_data.item_id, "tenant_id": tenant_id})

        if not menu_item:
            continue

        quantity = item_data.quantity
        total_price = menu_item["unit_price"] * quantity
        subtotal += total_price

        order_items_list.append(
            POSOrderItem(
                item_id=menu_item["id"], item_name=menu_item["item_name"], category=POSCategory(menu_item["category"]), quantity=quantity, unit_price=menu_item["unit_price"], total_price=total_price
            )
        )

    # Calculate tax (18% VAT for Turkey)
    tax_amount = subtotal * 0.18
    total_amount = subtotal + tax_amount

    # Adisyon (check) numbering — sequential per outlet, resets each business day.
    business_date = await _get_pos_business_date(tenant_id)
    adisyon_number = await _next_adisyon_number(tenant_id, data.outlet_id, business_date)

    # Create order
    order = POSOrder(
        tenant_id=tenant_id,
        booking_id=booking_id,
        guest_id=guest_id,
        folio_id=folio_id,
        outlet_id=data.outlet_id,
        table_number=data.table_number,
        adisyon_number=adisyon_number,
        business_date=business_date,
        payment_method=data.payment_method,
        guest_signature=data.guest_signature,
        notes=data.notes,
        order_items=order_items_list,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        status="completed",
        idempotency_key=idempotency_key,
    )
    order_doc = order.model_dump()

    # Build folio charge docs, each stamped with (source_pos_order_id, line_no)
    # so the unique partial index can dedup any partial-failure re-post. These
    # source fields are NOT on the FolioCharge schema (extra="ignore") so we add
    # them to the dict after model_dump.
    charge_docs: list[dict] = []
    if folio_id:
        for line_no, order_item in enumerate(order_items_list):
            charge = FolioCharge(
                tenant_id=tenant_id,
                folio_id=folio_id,
                booking_id=folio_booking_id,
                charge_category=ChargeCategory.FOOD if order_item.category in ["food", "dessert", "appetizer"] else ChargeCategory.BEVERAGE,
                description=f"POS: {order_item.item_name} x {order_item.quantity}",
                quantity=order_item.quantity,
                unit_price=order_item.unit_price,
                amount=order_item.total_price,
                tax_amount=order_item.total_price * 0.18,
                total=order_item.total_price * 1.18,
                voided=False,
            )
            cdoc = charge.model_dump()
            cdoc["source_pos_order_id"] = order.id
            cdoc["line_no"] = line_no
            charge_docs.append(cdoc)

    # Ensure the unique partial indexes exist (fail-closed). Without them the
    # idempotency / dedup guarantees this endpoint promises cannot hold, so we
    # refuse rather than silently fall back to a racy, non-idempotent write.
    try:
        await _ensure_pos_atomicity_indexes(folio_post=bool(folio_id))
    except Exception:
        logger.exception("POS atomicity index ensure failed")
        raise HTTPException(
            status_code=503,
            detail="POS idempotency koruması geçici olarak kullanılamıyor — biraz sonra tekrar deneyin",
        )

    # Task #389 — durable intent payload for the IC outbox event. The async
    # consumer (core.pos_folio_consumer) applies these exact charge docs to the
    # folio idempotently and recalculates the balance from the ledger.
    outbox_payload: dict | None = None
    if folio_id and charge_docs:
        outbox_payload = {
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "source_pos_order_id": order.id,
            "booking_id": folio_booking_id,
            "charges": charge_docs,
        }

    effective_order, replay = await _persist_pos_order_atomic(
        order_doc=order_doc,
        charge_docs=charge_docs,
        folio_id=folio_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        outbox_payload=outbox_payload,
    )

    # Auto-create the kitchen display ticket + enqueue the KOT print job(s) only
    # for a genuinely new order (never on an idempotent replay).
    if not replay:
        await _auto_kds_and_kot(order, tenant_id, current_user.name)

    return {
        "success": True,
        "message": "POS order created",
        "idempotent_replay": replay,
        # Folyoya yazılan POS hesabı artık async (outbox) postlanır; sipariş
        # kaydı + niyet durable, charge'lar consumer tarafından idempotent uygulanır.
        "charge_status": "queued" if (folio_id and charge_docs) else "none",
        "order_id": effective_order.get("id"),
        "order": effective_order,
    }


# ── GET /pos/menu-engineering ──
@router.get("/pos/menu-engineering")
async def get_menu_engineering(
    start_date: str | None = None,
    end_date: str | None = None,
    outlet_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Menü mühendisliği matrisi (Stars / Plowhorses / Puzzles / Dogs).

    Kasavana-Smith metodu — gerçek `pos_orders` satışlarını `pos_menu_items`
    katalog maliyetleriyle birleştirir. Eşikler hardcoded değil; popülerlik
    eşiği (1/N)×%70, karlılık eşiği ağırlıklı ortalama katkı payı.
    """
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    return await _build_menu_engineering(
        current_user.tenant_id,
        start.isoformat(),
        end.isoformat(),
        outlet_id,
    )
