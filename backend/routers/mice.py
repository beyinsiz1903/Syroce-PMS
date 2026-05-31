"""MICE — Meetings, Incentives, Conferences & Events / Banquet.

Mirrors the Opera/Protel banquet management spine:
* Function spaces (rooms/halls) with capacities per setup style
* Events with proper sales lifecycle (lead → tentative → definite →
  confirmed → cancelled / completed) and conflict-checked space holds
* Resource lines (F&B menus, AV equipment, decor) per event
* Auto-computed quote totals
* Function diary (calendar)
* BEO (Banquet Event Order) summary endpoint
* Charge-to-master integration emitting Xchange POSTING_CHARGE
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from cache_manager import cache as _cache
from cache_manager import cached as _cached
from core.audit import log_audit_event
from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
    with_resource_locks,
)
from core.security import get_current_user
from core.spa_mice_authz import require_catalog, require_finance, require_mice_ops
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v94 DW
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

router = APIRouter(prefix="/api/mice", tags=["mice"])

_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_system_db()
    try:
        await db.mice_events.create_index(
            [("tenant_id", 1), ("status", 1), ("start_date", 1)],
            name="mice_evt_status_date")
        await db.mice_events.create_index(
            [("tenant_id", 1), ("start_date", 1), ("end_date", 1)],
            name="mice_evt_date_range")
        await db.mice_events.create_index(
            [("tenant_id", 1), ("space_bookings.space_id", 1),
             ("status", 1)],
            name="mice_evt_space_status")
        await db.mice_spaces.create_index([("tenant_id", 1), ("active", 1)])
        await db.mice_menus.create_index([("tenant_id", 1), ("type", 1)])
        await db.mice_locks.create_index(
            [("tenant_id", 1), ("kind", 1), ("resource_id", 1)],
            unique=True, name="uniq_mice_lock")
        # Sprint 24 banquet collections
        await db.mice_accounts.create_index(
            [("tenant_id", 1), ("name", 1)], name="mice_acc_name")
        await db.mice_accounts.create_index(
            [("tenant_id", 1), ("tax_no", 1)], name="mice_acc_taxno")
        # Task #205: DB-level partial unique indexes close the read-then-insert
        # race in `_assert_account_unique`. Two near-simultaneous creates with
        # the same tax_no/email can both pass the app-level find_one; the unique
        # index makes the losing insert fail with DuplicateKeyError (→ 409).
        # The partial filter scopes uniqueness to *client* rows with a populated
        # string value so (a) piggybacked banquet-competitor rows never collide,
        # (b) blank ("")/missing identifiers are ignored exactly like the app
        # guard, and (c) legacy rows without account_type stay out of the build.
        # Each build is wrapped on its own so a pre-existing duplicate only
        # disables this backstop, not the rest of the index batch.
        for _uniq_field, _uniq_name in (
            ("tax_no", "uniq_mice_acc_client_taxno"),
            ("email", "uniq_mice_acc_client_email"),
        ):
            try:
                await db.mice_accounts.create_index(
                    [("tenant_id", 1), (_uniq_field, 1)],
                    unique=True,
                    partialFilterExpression={
                        "account_type": "client",
                        _uniq_field: {"$gt": "", "$type": "string"},
                    },
                    name=_uniq_name)
            except Exception as _uniq_exc:  # noqa: BLE001
                import logging
                logging.getLogger("mice").warning(
                    "mice_accounts unique index %s deferred (existing "
                    "duplicate/data?) → race backstop NOT enforced: %s",
                    _uniq_name, _uniq_exc)
        await db.mice_contacts.create_index(
            [("tenant_id", 1), ("account_id", 1)], name="mice_ctc_acc")
        await db.mice_resources.create_index(
            [("tenant_id", 1), ("type", 1), ("active", 1)],
            name="mice_res_type")
        await db.mice_events.create_index(
            [("tenant_id", 1), ("resources.inventory_id", 1), ("status", 1)],
            name="mice_evt_inv_status")
        # F&B kitchen production orders (BEO → kitchen send surface)
        await db.mice_fnb_orders.create_index(
            [("tenant_id", 1), ("event_id", 1), ("sent_at", -1)],
            name="mice_fnb_order_event")
        _indexes_ready = True
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("mice").warning("Index creation deferred: %s", exc)

# ── Function spaces ──────────────────────────────────────────────
class FunctionSpaceIn(BaseModel):
    name: str
    location: str | None = None  # floor / wing
    area_m2: float = Field(0, ge=0)
    capacity_theatre: int = Field(0, ge=0)
    capacity_classroom: int = Field(0, ge=0)
    capacity_banquet: int = Field(0, ge=0)
    capacity_cocktail: int = Field(0, ge=0)
    capacity_u_shape: int = Field(0, ge=0)
    capacity_boardroom: int = Field(0, ge=0)
    hourly_rate: float = Field(0, ge=0)
    daily_rate: float = Field(0, ge=0)
    currency: str = "TRY"
    amenities: list[str] = Field(default_factory=list)  # ["projector","stage",...]
    active: bool = True


def _invalidate_mice_spaces_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "mice_spaces")


def _invalidate_mice_menus_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "mice_menus")


def _invalidate_mice_accounts_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "mice_accounts")


def _invalidate_mice_resources_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "mice_resources")


def _invalidate_mice_events_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "mice_events")


# rbac-allow: cache-rbac — toplantı salonları operasyonel listesi tüm rolelere açık
# v97 perf — TTL 30s → 300s. Function space envanteri günde birkaç
# kez değişir; 5 dk cache UX'i akıcılaştırır (1.9s → <50ms cache hit).
@router.get("/spaces")
@_cached(ttl=300, key_prefix="mice_spaces")
async def list_spaces(current_user: User = Depends(get_current_user)) -> dict:
    await _ensure_indexes()
    db = get_system_db()
    cur = db.mice_spaces.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("name", 1)
    items = [doc async for doc in cur]
    if not items:
        try:
            require_catalog(current_user)
        except HTTPException:
            return {"spaces": []}
        items = await _seed_spaces(current_user.tenant_id)
    return {"spaces": items}


async def _seed_spaces(tenant_id: str) -> list[dict]:
    db = get_system_db()
    seeds = [
        ("Grand Balo Salonu", "Bodrum kat", 480, 500, 280, 320, 450, 0, 0, 8000, 35000),
        ("Bosphorus Toplantı Salonu", "1. kat", 120, 120, 70, 80, 100, 50, 40, 2500, 12000),
        ("Boardroom", "1. kat", 35, 0, 0, 0, 0, 0, 14, 1500, 6000),
        ("Teras Etkinlik Alanı", "Çatı", 220, 0, 0, 150, 250, 0, 0, 3500, 18000),
    ]
    docs = []
    for s in seeds:
        n, loc, area, th, cl, bq, ck, us, br, hr, dr = s
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": n, "location": loc, "area_m2": area,
            "capacity_theatre": th, "capacity_classroom": cl,
            "capacity_banquet": bq, "capacity_cocktail": ck,
            "capacity_u_shape": us, "capacity_boardroom": br,
            "hourly_rate": hr, "daily_rate": dr, "currency": "TRY",
            "amenities": ["wifi", "projector", "ses-sistemi"],
            "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    await db.mice_spaces.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/spaces")
async def create_space(body: FunctionSpaceIn,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_spaces.insert_one(doc)
    doc.pop("_id", None)
    _invalidate_mice_spaces_cache(current_user.tenant_id)
    return doc


@router.put("/spaces/{space_id}")
async def update_space(space_id: str, body: FunctionSpaceIn,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.mice_spaces.update_one(
        {"id": space_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Mekan bulunamadı")
    _invalidate_mice_spaces_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/spaces/{space_id}")
async def delete_space(space_id: str,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.mice_spaces.delete_one(
        {"id": space_id, "tenant_id": current_user.tenant_id})
    _invalidate_mice_spaces_cache(current_user.tenant_id)
    return {"ok": True}


# ── Catalog: F&B menus and AV/decor packages ────────────────────
class MenuCourseIn(BaseModel):
    course_type: str  # appetizer / soup / main / side / dessert / beverage / canapé / break
    name: str
    description: str | None = None


class MenuPackageIn(BaseModel):
    name: str
    type: str = "fb"  # fb / av / decor / ddr  (DDR = Daily Delegate Rate bundle)
    price_per_person: float = Field(0, ge=0)
    flat_price: float = Field(0, ge=0)
    currency: str = "TRY"
    description: str | None = None
    active: bool = True
    # Banquet-grade enrichment (all optional → backwards compatible)
    courses: list[MenuCourseIn] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)  # nuts/gluten/dairy/egg/soy/...
    dietary_tags: list[str] = Field(default_factory=list)  # vegan/vegetarian/halal/kosher/gluten_free
    min_guests: int = Field(0, ge=0)
    prep_lead_minutes: int = Field(30, ge=0)  # kitchen lead-time


@_cached(ttl=30, key_prefix="mice_menus")
async def _list_menus_cached(current_user: User) -> dict:
    """Pure DB read (tenant-scoped). Wrapped by `list_menus` so that the
    seed-on-empty branch (role-dependent) stays OUT of the cache —
    otherwise a non-catalog user could pin an empty payload that a catalog
    user would later see (would block the seed bootstrap for TTL window)."""
    db = get_system_db()
    cur = db.mice_menus.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("type", 1)
    return {"menus": [doc async for doc in cur]}


@router.get("/menus")
async def list_menus(current_user: User = Depends(get_current_user)) -> dict:
    result = await _list_menus_cached(current_user=current_user)
    if result["menus"]:
        return result
    # Empty: only catalog admins may bootstrap the seed; everyone else
    # gets the empty list (NOT cached, see helper above).
    try:
        require_catalog(current_user)
    except HTTPException:
        return {"menus": []}
    items = await _seed_menus(current_user.tenant_id)
    _invalidate_mice_menus_cache(current_user.tenant_id)
    return {"menus": items}


async def _seed_menus(tenant_id: str) -> list[dict]:
    db = get_system_db()
    seeds = [
        ("Coffee Break (Standart)", "fb", 250, 0),
        ("Açık Büfe Öğle Yemeği", "fb", 950, 0),
        ("Gala Akşam Yemeği (4 Kap)", "fb", 1850, 0),
        ("AV Paketi (projeksiyon+ses)", "av", 0, 4500),
        ("Çiçek & Sahne Dekorasyonu", "decor", 0, 12000),
    ]
    docs = []
    for n, t, pp, fp in seeds:
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": n, "type": t,
            "price_per_person": pp, "flat_price": fp,
            "currency": "TRY", "description": None, "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    await db.mice_menus.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/menus")
async def create_menu(body: MenuPackageIn,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_menus.insert_one(doc)
    doc.pop("_id", None)
    _invalidate_mice_menus_cache(current_user.tenant_id)
    return doc


@router.put("/menus/{menu_id}")
async def update_menu(menu_id: str, body: MenuPackageIn,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.mice_menus.update_one(
        {"id": menu_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Menü bulunamadı")
    _invalidate_mice_menus_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/menus/{menu_id}")
async def delete_menu(menu_id: str,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.mice_menus.delete_one(
        {"id": menu_id, "tenant_id": current_user.tenant_id})
    _invalidate_mice_menus_cache(current_user.tenant_id)
    return {"ok": True}


# ── Sales & Catering CRM: Accounts (corporate clients) ──────────
class AccountIn(BaseModel):
    name: str
    legal_name: str | None = None
    tax_no: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = "TR"
    industry: str | None = None  # corporate / wedding-planner / agency / govt
    credit_limit: float = Field(0, ge=0)
    payment_terms_days: int = Field(0, ge=0)
    notes: str | None = None
    active: bool = True


async def _assert_account_unique(
    db: Any, tenant_id: str, body: AccountIn, exclude_id: str | None = None
) -> None:
    """Tenant-scoped duplicate guard for CRM client accounts.

    Rejects (409) a create/update whose ``tax_no`` or ``email`` collides with
    another *client* account in the same tenant. Scoped via ``_CLIENT_ACCT_FILTER``
    so piggybacked rows (e.g. banquet competitors) never produce false positives.
    Blank values are ignored — uniqueness only applies to populated identifiers.
    """
    checks: list[tuple[str, str]] = []
    if body.tax_no and body.tax_no.strip():
        checks.append(("tax_no", body.tax_no.strip()))
    if body.email and body.email.strip():
        checks.append(("email", body.email.strip()))
    for field, value in checks:
        flt: dict[str, Any] = {
            "tenant_id": tenant_id,
            field: value,
            **_CLIENT_ACCT_FILTER,
        }
        if exclude_id:
            flt["id"] = {"$ne": exclude_id}
        dup = await db.mice_accounts.find_one(flt, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(
                409, f"Bu {field} ile kayıtlı müşteri zaten var")


@router.get("/accounts")
@_cached(ttl=30, key_prefix="mice_accounts")
async def list_accounts(
    q: str | None = Query(None, description="Free-text search on name/tax_no"),
    current_user: User = Depends(get_current_user),
) -> dict:
    await _ensure_indexes()
    db = get_system_db()
    # Exclude alternate account_type rows (e.g. banquet_competitor records
    # piggybacking on this collection) so the CRM client list stays clean.
    flt: dict[str, Any] = {
        "tenant_id": current_user.tenant_id,
        "$or": [{"account_type": {"$exists": False}},
                {"account_type": "client"}],
    }
    if q:
        from security.query_safety import safe_search_term
        if (_s := safe_search_term(q)):
            rx = {"$regex": _s, "$options": "i"}
            # Compose with the existing $or above using $and so both filters
            # are honoured.
            flt = {
                "tenant_id": current_user.tenant_id,
                "$and": [
                    {"$or": [{"account_type": {"$exists": False}},
                             {"account_type": "client"}]},
                    {"$or": [{"name": rx}, {"legal_name": rx},
                             {"tax_no": rx}]},
                ],
            }
    cur = db.mice_accounts.find(flt, {"_id": 0}).sort("name", 1).limit(500)
    return {"accounts": [d async for d in cur]}


_CLIENT_ACCT_FILTER = {
    "$or": [{"account_type": {"$exists": False}},
             {"account_type": "client"}],
}


@router.post("/accounts")
async def create_account(body: AccountIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    await _assert_account_unique(db, current_user.tenant_id, body)
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           "account_type": "client",  # discriminator; isolates piggybacked rows
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat(),
           "created_by": current_user.username}
    try:
        await db.mice_accounts.insert_one(doc)
    except DuplicateKeyError as exc:
        # Lost the read-then-insert race: a concurrent request inserted the same
        # tax_no/email first. Surface the identical field-specific 409 the
        # app-level guard would have raised.
        field = "tax_no" if "taxno" in str(exc) else "email"
        raise HTTPException(409, f"Bu {field} ile kayıtlı müşteri zaten var")
    doc.pop("_id", None)
    _invalidate_mice_accounts_cache(current_user.tenant_id)
    return doc


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, body: AccountIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    await _assert_account_unique(
        db, current_user.tenant_id, body, exclude_id=account_id)
    # Discriminator guard: never mutate non-client docs (e.g. banquet
    # competitors stored in the same collection) via the CRM endpoint.
    try:
        res = await db.mice_accounts.update_one(
            {"id": account_id, "tenant_id": current_user.tenant_id,
             **_CLIENT_ACCT_FILTER},
            {"$set": {**body.model_dump(),
                      "account_type": "client",
                      "updated_at": datetime.now(UTC).isoformat()}})
    except DuplicateKeyError as exc:
        # Concurrent update raced us to the same tax_no/email — same 409.
        field = "tax_no" if "taxno" in str(exc) else "email"
        raise HTTPException(409, f"Bu {field} ile kayıtlı müşteri zaten var")
    if not res.matched_count:
        raise HTTPException(404, "Hesap bulunamadı")
    _invalidate_mice_accounts_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    # Refuse if any active event uses this account
    in_use = await db.mice_events.find_one({
        "tenant_id": current_user.tenant_id,
        "client_account_id": account_id,
        "status": {"$nin": ["cancelled"]},
    })
    if in_use:
        raise HTTPException(409, "Bu hesap aktif etkinliklere bağlı, silinemez.")
    # Discriminator guard mirrors update_account above.
    res = await db.mice_accounts.delete_one(
        {"id": account_id, "tenant_id": current_user.tenant_id,
         **_CLIENT_ACCT_FILTER})
    if not res.deleted_count:
        raise HTTPException(404, "Hesap bulunamadı")
    await db.mice_contacts.delete_many(
        {"tenant_id": current_user.tenant_id, "account_id": account_id})
    _invalidate_mice_accounts_cache(current_user.tenant_id)
    return {"ok": True}


# ── Sales & Catering CRM: Contacts (people inside an account) ──
class ContactIn(BaseModel):
    account_id: str
    name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False
    notes: str | None = None


@router.get("/accounts/{account_id}/contacts")
async def list_contacts(account_id: str,
                        current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.mice_contacts.find(
        {"tenant_id": current_user.tenant_id, "account_id": account_id},
        {"_id": 0},
    ).sort("name", 1)
    return {"contacts": [d async for d in cur]}


@router.post("/accounts/{account_id}/contacts")
async def create_contact(account_id: str, body: ContactIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    if body.account_id != account_id:
        raise HTTPException(400, "account_id eşleşmiyor")
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_contacts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    res = await db.mice_contacts.update_one(
        {"id": contact_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Kişi bulunamadı")
    return {"ok": True}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    await db.mice_contacts.delete_one(
        {"id": contact_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Resource Inventory (AV equipment, decor, linens, etc.) ──────
class ResourceInventoryIn(BaseModel):
    name: str
    type: str = "av"  # av / decor / linen / furniture / other
    total_stock: float = Field(0, ge=0)
    unit: str = "unit"  # unit / set / pcs
    unit_price: float = Field(0, ge=0)
    currency: str = "TRY"
    notes: str | None = None
    active: bool = True


@router.get("/resources")
@_cached(ttl=30, key_prefix="mice_resources")
async def list_resources(current_user: User = Depends(get_current_user)) -> dict:
    await _ensure_indexes()
    db = get_system_db()
    cur = db.mice_resources.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("type", 1)
    return {"resources": [d async for d in cur]}


@router.post("/resources")
async def create_resource(body: ResourceInventoryIn,
                          current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_resources.insert_one(doc)
    doc.pop("_id", None)
    _invalidate_mice_resources_cache(current_user.tenant_id)
    return doc


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: str, body: ResourceInventoryIn,
                          current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.mice_resources.update_one(
        {"id": resource_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Kaynak bulunamadı")
    _invalidate_mice_resources_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/resources/{resource_id}")
async def delete_resource(resource_id: str,
                          current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.mice_resources.delete_one(
        {"id": resource_id, "tenant_id": current_user.tenant_id})
    _invalidate_mice_resources_cache(current_user.tenant_id)
    return {"ok": True}


# ── Events ──────────────────────────────────────────────────────
EVENT_STATUSES = {"lead", "tentative", "definite",
                  "confirmed", "completed", "cancelled"}


class SpaceBookingIn(BaseModel):
    space_id: str
    starts_at: datetime
    ends_at: datetime
    setup_style: str = "theatre"  # theatre/classroom/banquet/cocktail/u_shape/boardroom
    expected_pax: int = Field(0, ge=0)


class ResourceLineIn(BaseModel):
    menu_id: str | None = None  # link to mice_menus catalog item
    inventory_id: str | None = None  # link to mice_resources stocked inventory
    name: str
    type: str = "fb"  # fb / av / decor / other
    quantity: float = 1
    unit: str = "pax"  # pax / unit / hour
    unit_price: float = 0
    notes: str | None = None


class AgendaItemIn(BaseModel):
    """Minute-level function-sheet line (Opera 'Function Sheet' equivalent)."""
    starts_at: datetime
    ends_at: datetime
    title: str
    location: str | None = None  # space name or external venue
    owner: str | None = None  # responsible person/department
    kind: str = "session"  # session/meal/break/setup/teardown/transfer/av_check
    notes: str | None = None


class PaymentScheduleItemIn(BaseModel):
    """Deposit & milestone payments (Opera deposit ledger equivalent)."""
    due_date: date
    label: str  # "Depozito %30" / "1. Taksit" / "Bakiye"
    amount: float = Field(0, ge=0)
    paid: bool = False
    paid_at: datetime | None = None
    reference: str | None = None  # bank ref / invoice no


class TechnicalRequirementsIn(BaseModel):
    """Structured technical/AV checklist for a banquet event.

    Free-text notes still live on the event itself; this struct lets the
    banquet ops team plan setup, hand-overs and printable BEO/ops sheets
    without parsing prose.
    """
    projector: bool = False
    screen: bool = False
    microphone_wired: int = Field(0, ge=0)
    microphone_wireless: int = Field(0, ge=0)
    sound_system: bool = False
    stage: bool = False
    lighting: bool = False
    livestream: bool = False
    internet_mbps: int = Field(0, ge=0)
    translation_booths: int = Field(0, ge=0)
    notes: str | None = None


class StaffAssignmentIn(BaseModel):
    """A single staff member assigned to an event."""
    role: str  # chef / server / technician / host / security / other
    name: str
    user_id: str | None = None  # link to internal user when known
    start_at: datetime | None = None
    end_at: datetime | None = None
    notes: str | None = None


class EntertainmentIn(BaseModel):
    """Music / entertainment booking attached to an event."""
    type: str = "none"  # dj / live_band / solo_artist / show / none
    name: str | None = None
    contact: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    requirements: str | None = None  # rider / technical asks
    fee: float = Field(0, ge=0)


class EventIn(BaseModel):
    name: str
    client_name: str
    client_email: str | None = None
    client_phone: str | None = None
    client_account_id: str | None = None  # link to mice_accounts
    client_contact_id: str | None = None  # link to mice_contacts
    organizer_user: str | None = None  # sales rep
    event_type: str = "meeting"  # meeting/conference/wedding/gala/training/other
    status: str = "lead"
    expected_pax: int = Field(0, ge=0)
    start_date: date
    end_date: date
    space_bookings: list[SpaceBookingIn] = Field(default_factory=list)
    resources: list[ResourceLineIn] = Field(default_factory=list)
    agenda: list[AgendaItemIn] = Field(default_factory=list)
    payment_schedule: list[PaymentScheduleItemIn] = Field(default_factory=list)
    notes: str | None = None
    reservation_id: str | None = None  # link to room block / master folio
    lost_reason: str | None = None  # populated when status=lost/cancelled
    # Banquet ops enrichment (all optional → backwards compatible)
    technical_requirements: TechnicalRequirementsIn | None = None
    staff_assignments: list[StaffAssignmentIn] = Field(default_factory=list)
    entertainment: EntertainmentIn | None = None


def _line_total(r: dict) -> float:
    return float(r.get("unit_price", 0)) * float(r.get("quantity", 1))


def _compute_totals(event: dict, spaces_by_id: dict[str, dict]) -> dict:
    space_total = 0.0
    for sb in event.get("space_bookings", []):
        sp = spaces_by_id.get(sb["space_id"])
        if not sp:
            continue
        # Use daily_rate when ≥6h, hourly_rate otherwise
        s = datetime.fromisoformat(sb["starts_at"])
        e = datetime.fromisoformat(sb["ends_at"])
        hours = max(1.0, (e - s).total_seconds() / 3600.0)
        space_total += sp["daily_rate"] if hours >= 6 else sp["hourly_rate"] * hours
    resources_total = sum(_line_total(r) for r in event.get("resources", []))
    return {
        "space_total": round(space_total, 2),
        "resources_total": round(resources_total, 2),
        "grand_total": round(space_total + resources_total, 2),
    }


# ── Setup-style capacity validation ─────────────────────────────
_SETUP_TO_CAP = {
    "theatre": "capacity_theatre",
    "classroom": "capacity_classroom",
    "banquet": "capacity_banquet",
    "cocktail": "capacity_cocktail",
    "u_shape": "capacity_u_shape",
    "boardroom": "capacity_boardroom",
}


async def _validate_setup_capacity(tenant_id: str,
                                   bookings: list[dict]) -> None:
    """Reject any space booking where expected_pax exceeds the capacity
    of the chosen setup style. Mirrors Opera S&C's setup-style guard."""
    db = get_system_db()
    space_ids = {sb["space_id"] for sb in bookings if sb.get("space_id")}
    if not space_ids:
        return
    spaces = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": tenant_id, "id": {"$in": list(space_ids)}})}
    for sb in bookings:
        sp = spaces.get(sb["space_id"])
        if not sp:
            continue
        pax = int(sb.get("expected_pax") or 0)
        style = sb.get("setup_style") or "theatre"
        cap_field = _SETUP_TO_CAP.get(style)
        if not cap_field:
            continue
        cap = int(sp.get(cap_field) or 0)
        if pax and cap and pax > cap:
            raise HTTPException(
                422,
                f"{sp['name']} mekanı '{style}' düzeninde en fazla {cap} "
                f"kişi alır (talep: {pax}). Düzeni değiştirin veya başka "
                f"mekan seçin.",
            )


# ── Resource inventory cross-event aggregation ──────────────────
async def _check_resource_inventory_conflict(
    tenant_id: str,
    resources: list[dict],
    bookings: list[dict],
    exclude_event_id: str | None = None,
    session=None,
) -> str | None:
    """For every resource line that points to a stocked inventory item
    (`inventory_id`), sum existing usage across active events whose time
    window overlaps any of *bookings*. If the running total + requested
    quantity exceeds `total_stock`, return a Turkish error message.
    """
    if not bookings or not resources:
        return None
    db = get_system_db()
    inv_ids = {r["inventory_id"] for r in resources if r.get("inventory_id")}
    if not inv_ids:
        return None

    # Time envelope of this event = (min start, max end) across bookings.
    starts = [sb["starts_at"] if isinstance(sb["starts_at"], str)
              else sb["starts_at"].isoformat() for sb in bookings]
    ends = [sb["ends_at"] if isinstance(sb["ends_at"], str)
            else sb["ends_at"].isoformat() for sb in bookings]
    env_start, env_end = min(starts), max(ends)

    inventories = {i["id"]: i async for i in db.mice_resources.find(
        {"tenant_id": tenant_id, "id": {"$in": list(inv_ids)}}, session=session)}

    # Build a per-inventory requested quantity map for this event.
    requested: dict[str, float] = {}
    for r in resources:
        iid = r.get("inventory_id")
        if iid:
            requested[iid] = requested.get(iid, 0) + float(r.get("quantity") or 0)

    # Aggregate currently-committed usage from other active events whose
    # bookings overlap this event's envelope.
    q = {
        "tenant_id": tenant_id,
        "status": {"$in": ["tentative", "definite", "confirmed"]},
        "resources.inventory_id": {"$in": list(inv_ids)},
    }
    if exclude_event_id:
        q["id"] = {"$ne": exclude_event_id}

    committed: dict[str, float] = dict.fromkeys(inv_ids, 0.0)
    async for ev in db.mice_events.find(q, session=session):
        # Does any of *its* bookings overlap our envelope?
        overlaps = False
        for sb in ev.get("space_bookings", []):
            if sb.get("starts_at", "") < env_end and env_start < sb.get("ends_at", ""):
                overlaps = True
                break
        if not overlaps:
            continue
        for r in ev.get("resources", []):
            iid = r.get("inventory_id")
            if iid in committed:
                committed[iid] += float(r.get("quantity") or 0)

    for iid, want in requested.items():
        inv = inventories.get(iid)
        if not inv:
            continue
        stock = float(inv.get("total_stock") or 0)
        if stock <= 0:
            continue
        used = committed.get(iid, 0.0)
        if used + want > stock:
            return (f"{inv['name']} envanteri yetersiz: stok {stock:g}, "
                    f"bu zaman aralığında zaten {used:g} ayrılmış, "
                    f"talep {want:g}.")
    return None


async def _check_space_conflict(tenant_id: str, bookings: list[dict],
                                exclude_event_id: str | None = None,
                                session=None) -> str | None:
    db = get_system_db()
    for sb in bookings:
        s_iso = sb["starts_at"] if isinstance(sb["starts_at"], str) else sb["starts_at"].isoformat()
        e_iso = sb["ends_at"] if isinstance(sb["ends_at"], str) else sb["ends_at"].isoformat()
        q = {
            "tenant_id": tenant_id,
            "status": {"$in": ["tentative", "definite", "confirmed"]},
            "space_bookings.space_id": sb["space_id"],
        }
        if exclude_event_id:
            q["id"] = {"$ne": exclude_event_id}
        async for ev in db.mice_events.find(q, session=session):
            for other in ev.get("space_bookings", []):
                if other.get("space_id") != sb["space_id"]:
                    continue
                if other["starts_at"] < e_iso and s_iso < other["ends_at"]:
                    return f"Mekan çakışması: {ev.get('name')} ({other['starts_at'][:16]})"
    return None


@router.get("/events")
@_cached(ttl=30, key_prefix="mice_events")
async def list_events(
    status: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if date_from:
        q["end_date"] = {"$gte": date_from}
    if date_to:
        q.setdefault("start_date", {})["$lte"] = date_to
    # v97 perf — events list, status aggregate ve 4 sibling count
    # sequential idi (1.1 sn). Tek asyncio.gather ile tüm reads
    # paralel; 4×count_documents N+1 kapatıldı.
    import asyncio as _asyncio
    pipe = [
        {"$match": {"tenant_id": current_user.tenant_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1},
                    "total": {"$sum": "$totals.grand_total"}}},
    ]
    tid = current_user.tenant_id
    (
        items,
        summary_rows,
        cnt_accounts,
        cnt_spaces,
        cnt_menus,
        cnt_resources,
    ) = await _asyncio.gather(
        db.mice_events.find(q, {"_id": 0}).sort("start_date", 1).limit(500).to_list(500),
        db.mice_events.aggregate(pipe).to_list(20),
        db.mice_accounts.count_documents({"tenant_id": tid, **_CLIENT_ACCT_FILTER}),
        db.mice_spaces.count_documents({"tenant_id": tid}),
        db.mice_menus.count_documents({"tenant_id": tid}),
        db.mice_resources.count_documents({"tenant_id": tid}),
    )
    summary: dict[str, dict] = {}
    for r in summary_rows:
        summary[r["_id"]] = {"count": r["n"],
                             "total_value": round(r.get("total", 0) or 0, 2)}
    counts = {
        "accounts": cnt_accounts,
        "spaces": cnt_spaces,
        "menus": cnt_menus,
        "resources": cnt_resources,
    }
    return {"events": items, "summary": summary, "counts": counts}


async def _expand_resource_prices(tenant_id: str, resources: list[dict],
                                  pax: int) -> list[dict]:
    db = get_system_db()
    out = []
    for r in resources:
        line = dict(r)
        if r.get("menu_id"):
            menu = await db.mice_menus.find_one(
                {"id": r["menu_id"], "tenant_id": tenant_id})
            if menu:
                if menu.get("price_per_person"):
                    line["unit_price"] = menu["price_per_person"]
                    line["unit"] = "pax"
                    if not line.get("quantity") or line["quantity"] in (0, 1):
                        line["quantity"] = pax
                elif menu.get("flat_price"):
                    line["unit_price"] = menu["flat_price"]
                    line["unit"] = "unit"
                    line["quantity"] = max(1, line.get("quantity", 1))
                line["name"] = line.get("name") or menu["name"]
                line["type"] = menu.get("type", line.get("type", "fb"))
        out.append(line)
    return out


@router.post("/events")
async def create_event(body: EventIn,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    await _ensure_indexes()
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id

    bookings = [b.model_dump() for b in body.space_bookings]
    for b in bookings:
        b["starts_at"] = b["starts_at"].isoformat() if isinstance(b["starts_at"], datetime) else b["starts_at"]
        b["ends_at"] = b["ends_at"].isoformat() if isinstance(b["ends_at"], datetime) else b["ends_at"]

    # Setup-style capacity guard (422 with friendly TR message)
    await _validate_setup_capacity(tenant_id, bookings)

    resources = await _expand_resource_prices(
        tenant_id, [r.model_dump() for r in body.resources], body.expected_pax,
    )

    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": tenant_id})}
    # mode="json" ⇒ pydantic, tüm date/datetime'leri ISO string'e serileştirir;
    # bu şekilde agenda[].starts_at ve payment_schedule[].due_date BSON için
    # geçerli kalır (PyMongo native `datetime.date`'i kabul etmez).
    event_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        **body.model_dump(mode="json", exclude={"space_bookings", "resources"}),
        "space_bookings": bookings,
        "resources": resources,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    event_doc["totals"] = _compute_totals(event_doc, spaces_by_id)

    holds_active = body.status in {"tentative", "definite", "confirmed"}
    space_ids = [b["space_id"] for b in bookings if b.get("space_id")]

    async def _do_insert(session) -> dict:
        if holds_active:
            conflict = await _check_space_conflict(
                tenant_id, bookings, session=session)
            if conflict:
                raise HTTPException(409, conflict)
            # Cross-event inventory aggregation INSIDE the tx so two
            # concurrent inserts cannot both pass the check and
            # over-subscribe a shared resource (architect: CRITICAL).
            inv_err = await _check_resource_inventory_conflict(
                tenant_id, resources, bookings, session=session)
            if inv_err:
                raise HTTPException(409, inv_err)
        await db.mice_events.insert_one(event_doc, session=session)
        return event_doc

    try:
        await with_resource_locks(
            client=db.client, db=db,
            tenant_id=tenant_id,
            locks_collection="mice_locks",
            resources=[("space", sid) for sid in space_ids] if holds_active else [],
            callback=_do_insert,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if not is_replica_set_unavailable(exc):
            raise
        if not standalone_fallback_allowed():
            raise HTTPException(
                status_code=503,
                detail=("Etkinlik servisi şu anda atomik garanti "
                        "sağlayamıyor (Mongo replica set gerekli)."),
            )
        # Dev opt-in: best-effort non-tx fallback.
        if holds_active:
            conflict = await _check_space_conflict(tenant_id, bookings)
            if conflict:
                raise HTTPException(409, conflict)
        await db.mice_events.insert_one(event_doc)

    event_doc.pop("_id", None)
    await log_audit_event(
        tenant_id=tenant_id, user_id=current_user.username,
        action="create", entity_type="mice_event",
        entity_id=event_doc["id"],
        details=f"Etkinlik oluşturuldu: {event_doc.get('name')} "
                f"({event_doc.get('start_date')})",
        before_value=None, after_value=event_doc, db=db)
    _invalidate_mice_events_cache(tenant_id)
    return event_doc


@router.get("/events/{event_id}")
async def get_event(event_id: str,
                    current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    doc = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Etkinlik bulunamadı")
    return doc


@router.put("/events/{event_id}")
async def update_event(event_id: str, body: EventIn,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id
    bookings = [b.model_dump() for b in body.space_bookings]
    for b in bookings:
        b["starts_at"] = b["starts_at"].isoformat() if isinstance(b["starts_at"], datetime) else b["starts_at"]
        b["ends_at"] = b["ends_at"].isoformat() if isinstance(b["ends_at"], datetime) else b["ends_at"]
    await _validate_setup_capacity(tenant_id, bookings)
    if body.status in {"tentative", "definite", "confirmed"}:
        conflict = await _check_space_conflict(tenant_id, bookings, exclude_event_id=event_id)
        if conflict:
            raise HTTPException(409, conflict)
    resources = await _expand_resource_prices(
        tenant_id, [r.model_dump() for r in body.resources], body.expected_pax)
    if body.status in {"tentative", "definite", "confirmed"}:
        inv_err = await _check_resource_inventory_conflict(
            tenant_id, resources, bookings, exclude_event_id=event_id)
        if inv_err:
            raise HTTPException(409, inv_err)
    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": tenant_id})}
    update = {
        **body.model_dump(mode="json", exclude={"space_bookings", "resources"}),
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "space_bookings": bookings,
        "resources": resources,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    update["totals"] = _compute_totals(update, spaces_by_id)
    before = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id}, {"_id": 0})
    res = await db.mice_events.update_one(
        {"id": event_id, "tenant_id": tenant_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    after = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=tenant_id, user_id=current_user.username,
        action="update", entity_type="mice_event", entity_id=event_id,
        details=f"Etkinlik güncellendi: {after.get('name')}",
        before_value=before, after_value=after, db=db)
    _invalidate_mice_events_cache(tenant_id)
    return {"ok": True, "totals": update["totals"]}


class StatusUpdate(BaseModel):
    status: str
    reason: str | None = None  # required for cancelled (lost-business)


@router.post("/events/{event_id}/status")
async def change_status(event_id: str, body: StatusUpdate,
                        current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    if body.status == "completed":
        require_finance(current_user)  # folio-impacting transition
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    cur_status = event.get("status", "lead")
    if body.status not in _MICE_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(
            409, f"Geçersiz geçiş: {cur_status} → {body.status}")
    if body.status in {"definite", "confirmed"} and cur_status not in {"definite", "confirmed"}:
        conflict = await _check_space_conflict(
            tenant_id, event.get("space_bookings", []), exclude_event_id=event_id)
        if conflict:
            raise HTTPException(409, conflict)
    # Lost-business / cancellation requires a reason (≥10 chars) for KPI
    # tracking — mirrors Opera S&C's "lost business" reason code.
    if body.status == "cancelled":
        reason = (body.reason or "").strip()
        if len(reason) < 10:
            raise HTTPException(
                422,
                "İptal/lost-business için en az 10 karakter sebep girilmelidir.",
            )
    update = {"status": body.status,
              "updated_at": datetime.now(UTC).isoformat()}
    if body.status == "cancelled":
        update["lost_reason"] = body.reason.strip()
        update["lost_at"] = datetime.now(UTC).isoformat()
    if body.status == "completed":
        update["completed_at"] = datetime.now(UTC).isoformat()
        await _post_event_to_folio(tenant_id, event)
    # IMPORTANT: tenant_id in write filter (cross-tenant safety).
    await db.mice_events.update_one(
        {"id": event_id, "tenant_id": tenant_id}, {"$set": update})
    after = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id}, {"_id": 0})
    before_clean = {k: v for k, v in event.items() if k != "_id"}
    await log_audit_event(
        tenant_id=tenant_id, user_id=current_user.username,
        action=f"status:{body.status}", entity_type="mice_event",
        entity_id=event_id,
        details=(f"{event.get('name')}: {cur_status} → {body.status}"
                 + (f" — {body.reason}" if body.reason else "")),
        before_value=before_clean, after_value=after, db=db)
    _invalidate_mice_events_cache(tenant_id)
    return {"ok": True, "status": body.status}


_MICE_TRANSITIONS: dict[str, set[str]] = {
    "lead": {"tentative", "cancelled"},
    "tentative": {"definite", "cancelled", "lead"},
    "definite": {"confirmed", "tentative", "cancelled"},
    "confirmed": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": {"lead"},  # allow re-opening a cancelled lead
}


async def _post_event_to_folio(tenant_id: str, event: dict) -> None:
    db = get_system_db()
    total = float((event.get("totals") or {}).get("grand_total", 0))
    if total <= 0 or not event.get("reservation_id"):
        return
    posting = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reservation_id": event["reservation_id"],
        "folio_id": event["reservation_id"],
        "transaction_code": "MICE",
        "description": f"Etkinlik: {event.get('name')}",
        "amount": total,
        "currency": "TRY",
        "posting_type": "CHARGE",
        "posted_at": datetime.now(UTC).isoformat(),
        "source": "mice_module",
        "reference": event["id"],
    }
    await db.folio_postings.insert_one(posting)
    try:
        from integrations.xchange.bus import bus
        from integrations.xchange.schemas import MessageType
        await bus.publish(
            tenant_id=tenant_id,
            message_type=MessageType.POSTING_CHARGE,
            payload={
                "posting_id": posting["id"],
                "reservation_id": posting["reservation_id"],
                "folio_id": posting["folio_id"],
                "posting_type": "CHARGE",
                "transaction_code": "MICE",
                "description": posting["description"],
                "amount": total,
                "currency": "TRY",
                "posted_at": posting["posted_at"],
            },
            message_id=f"mice-{event['id']}",
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("mice").warning(
            "Xchange POSTING_CHARGE publish failed (best-effort): %s", exc)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    before = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    res = await db.mice_events.delete_one(
        {"id": event_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    await log_audit_event(
        tenant_id=current_user.tenant_id, user_id=current_user.username,
        action="delete", entity_type="mice_event", entity_id=event_id,
        details=f"Etkinlik silindi: {(before or {}).get('name')}",
        before_value=before, after_value=None, db=db)
    _invalidate_mice_events_cache(current_user.tenant_id)
    return {"ok": True}


# ── Function diary (calendar feed) ─────────────────────────────
@router.get("/diary")
async def diary(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Etkinlik takvimi. Varsayılan: bugünden +30 gün."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    today = _dt.now(_UTC).date()
    if not date_from:
        date_from = today.isoformat()
    if not date_to:
        date_to = (today + _td(days=30)).isoformat()
    db = get_system_db()
    cur = db.mice_events.find({
        "tenant_id": current_user.tenant_id,
        "start_date": {"$lte": date_to},
        "end_date": {"$gte": date_from},
    }, {"_id": 0, "name": 1, "status": 1, "client_name": 1,
        "expected_pax": 1, "start_date": 1, "end_date": 1,
        "space_bookings": 1, "id": 1, "totals": 1})
    return {"events": [d async for d in cur]}


# ── BEO (Banquet Event Order) ──────────────────────────────────
@router.get("/events/{event_id}/beo")
async def beo(event_id: str,
              current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": current_user.tenant_id})}
    space_lines = []
    for sb in event.get("space_bookings", []):
        sp = spaces_by_id.get(sb["space_id"], {})
        space_lines.append({
            "space_name": sp.get("name", "—"),
            "starts_at": sb["starts_at"], "ends_at": sb["ends_at"],
            "setup_style": sb.get("setup_style"),
            "expected_pax": sb.get("expected_pax"),
        })
    return {
        "event": {k: event[k] for k in (
            "id", "name", "client_name", "client_email", "client_phone",
            "client_account_id", "client_contact_id",
            "organizer_user", "event_type", "status", "expected_pax",
            "start_date", "end_date", "notes", "totals",
            "lost_reason") if k in event},
        "spaces": space_lines,
        "resources": event.get("resources", []),
        "agenda": event.get("agenda", []),
        "payment_schedule": event.get("payment_schedule", []),
        # Banquet ops enrichment — included only when populated so legacy
        # consumers see the same shape as before for older events.
        "technical_requirements": event.get("technical_requirements") or None,
        "staff_assignments": event.get("staff_assignments") or [],
        "entertainment": event.get("entertainment") or None,
    }


def _beo_html(payload: dict) -> str:
    """Render the BEO summary dict as a printable HTML document.

    Same shape as the JSON endpoint above so kitchen/AV/floor teams
    receive every section they already see in the modal.
    """
    from html import escape as _e

    ev = payload.get("event") or {}
    spaces = payload.get("spaces") or []
    resources = payload.get("resources") or []
    agenda = payload.get("agenda") or []
    schedule = payload.get("payment_schedule") or []
    tech = payload.get("technical_requirements") or {}
    staff = payload.get("staff_assignments") or []
    entertainment = payload.get("entertainment") or {}
    totals = ev.get("totals") or {}

    def _money(v: Any) -> str:
        try:
            return f"₺{float(v or 0):,.2f}"
        except Exception:
            return "₺0.00"

    def _row(label: str, value: Any) -> str:
        return (f"<tr><td class='k'>{_e(str(label))}</td>"
                f"<td>{_e('' if value is None else str(value))}</td></tr>")

    spaces_html = "".join(
        f"<tr><td>{_e(s.get('space_name') or '—')}</td>"
        f"<td>{_e(s.get('setup_style') or '—')}</td>"
        f"<td class='r'>{_e(str(s.get('expected_pax') or '—'))}</td>"
        f"<td class='mono'>{_e((s.get('starts_at') or '')[:16])}</td>"
        f"<td class='mono'>{_e((s.get('ends_at') or '')[:16])}</td></tr>"
        for s in spaces
    ) or "<tr><td colspan='5' class='muted'>Mekan tanımlı değil.</td></tr>"

    agenda_html = "".join(
        f"<tr><td class='mono'>{_e((a.get('starts_at') or '')[11:16])}–"
        f"{_e((a.get('ends_at') or '')[11:16])}</td>"
        f"<td>{_e(a.get('title') or '')}</td>"
        f"<td>{_e(a.get('kind') or '')}</td>"
        f"<td>{_e(a.get('owner') or '—')}</td></tr>"
        for a in agenda
    ) or "<tr><td colspan='4' class='muted'>Ajanda boş.</td></tr>"

    resources_html = "".join(
        f"<tr><td>{_e(r.get('name') or '—')}</td>"
        f"<td>{_e(r.get('type') or '—')}</td>"
        f"<td class='r'>{_e(str(r.get('quantity') or 0))}</td>"
        f"<td class='r'>{_money(r.get('unit_price'))}</td>"
        f"<td class='r'>{_money((r.get('quantity') or 0) * (r.get('unit_price') or 0))}</td></tr>"
        for r in resources
    ) or "<tr><td colspan='5' class='muted'>Kaynak tanımlı değil.</td></tr>"

    schedule_html = "".join(
        f"<tr><td class='mono'>{_e(str(p.get('due_date') or ''))}</td>"
        f"<td>{_e(p.get('label') or '')}</td>"
        f"<td class='r'>{_money(p.get('amount'))}</td>"
        f"<td>{'Ödendi' if p.get('paid') else 'Bekliyor'}"
        f"{(' • Ref: ' + _e(str(p.get('reference')))) if p.get('reference') else ''}</td></tr>"
        for p in schedule
    ) or "<tr><td colspan='4' class='muted'>Ödeme takvimi tanımlı değil.</td></tr>"

    staff_html = "".join(
        f"<tr><td>{_e(s.get('role') or '—')}</td>"
        f"<td>{_e(s.get('name') or s.get('user') or '—')}</td>"
        f"<td>{_e(s.get('notes') or '')}</td></tr>"
        for s in staff
    ) or "<tr><td colspan='3' class='muted'>Personel ataması yok.</td></tr>"

    # Field mapping mirrors `TechnicalRequirementsIn` (backend/routers/mice.py
    # line 642) so every checklist item the ops team captured is printed on
    # the hand sheet. Booleans render Var/Yok (incl. explicit Yok) and ints
    # render the requested count (0 → Yok, otherwise the count + unit).
    def _bool(v: Any) -> str:
        return "Var" if bool(v) else "Yok"

    if tech:
        tech_rows = [
            _row("Projeksiyon", _bool(tech.get("projector"))),
            _row("Perde / Ekran", _bool(tech.get("screen"))),
            _row("Kablolu Mikrofon",
                 f"{int(tech.get('microphone_wired') or 0)} adet"),
            _row("Kablosuz Mikrofon",
                 f"{int(tech.get('microphone_wireless') or 0)} adet"),
            _row("Ses Sistemi", _bool(tech.get("sound_system"))),
            _row("Sahne", _bool(tech.get("stage"))),
            _row("Aydınlatma", _bool(tech.get("lighting"))),
            _row("Canlı Yayın", _bool(tech.get("livestream"))),
            _row("İnternet (Mbps)",
                 f"{int(tech.get('internet_mbps') or 0)} Mbps"),
            _row("Çeviri Kabini",
                 f"{int(tech.get('translation_booths') or 0)} adet"),
        ]
        if tech.get("notes"):
            tech_rows.append(_row("Notlar", tech.get("notes")))
        tech_html = "<table>" + "".join(tech_rows) + "</table>"
    else:
        tech_html = "<p class='muted'>Teknik gereksinim girilmemiş.</p>"

    ent_html = ""
    if entertainment:
        ent_html = "<table>"
        for key, val in entertainment.items():
            ent_html += _row(key, val)
        ent_html += "</table>"

    generated_at = datetime.now(UTC).isoformat()[:19]

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"/>
<title>BEO — {_e(ev.get('name') or '')}</title>
<style>
  @page {{ size: A4; margin: 18mm 14mm; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #1f2937; font-size: 11px; }}
  h1 {{ font-size: 18px; margin: 0 0 4px 0; color: #111827; }}
  h2 {{ font-size: 13px; margin: 14px 0 6px 0; color: #1f2937;
        border-bottom: 1px solid #d1d5db; padding-bottom: 2px; }}
  .meta {{ color: #6b7280; font-size: 10px; margin-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 4px; }}
  th, td {{ border: 1px solid #d1d5db; padding: 4px 6px; vertical-align: top; }}
  th {{ background: #f3f4f6; text-align: left; font-weight: 600; }}
  td.k {{ background: #f9fafb; width: 35%; font-weight: 600; }}
  td.r, th.r {{ text-align: right; }}
  td.mono {{ font-family: 'Courier New', monospace; }}
  .muted {{ color: #9ca3af; font-style: italic; text-align: center; }}
  .totals td {{ font-weight: 600; }}
  .totals .grand {{ background: #eef2ff; color: #3730a3; font-size: 13px; }}
  .footer {{ margin-top: 18px; color: #9ca3af; font-size: 9px; text-align: center; }}
</style>
</head><body>
  <h1>Banquet Event Order — {_e(ev.get('name') or '—')}</h1>
  <div class="meta">Üretildi: {_e(generated_at)} UTC · Durum: {_e(ev.get('status') or '—')}</div>

  <h2>Etkinlik Bilgileri</h2>
  <table>
    {_row('Müşteri', ev.get('client_name'))}
    {_row('E-posta', ev.get('client_email'))}
    {_row('Telefon', ev.get('client_phone'))}
    {_row('Etkinlik Tipi', ev.get('event_type'))}
    {_row('Beklenen Pax', ev.get('expected_pax'))}
    {_row('Tarih', f"{ev.get('start_date') or ''} → {ev.get('end_date') or ''}")}
    {_row('Organizatör', ev.get('organizer_user'))}
    {_row('Notlar', ev.get('notes'))}
  </table>

  <h2>Mekanlar</h2>
  <table>
    <thead><tr><th>Mekan</th><th>Düzen</th><th class='r'>Pax</th>
      <th>Başla</th><th>Bitir</th></tr></thead>
    <tbody>{spaces_html}</tbody>
  </table>

  <h2>Ajanda / Fonksiyon Sheet</h2>
  <table>
    <thead><tr><th>Saat</th><th>Başlık</th><th>Tip</th><th>Sorumlu</th></tr></thead>
    <tbody>{agenda_html}</tbody>
  </table>

  <h2>Kaynaklar (F&amp;B + AV)</h2>
  <table>
    <thead><tr><th>Hat</th><th>Tip</th><th class='r'>Adet</th>
      <th class='r'>Birim</th><th class='r'>Toplam</th></tr></thead>
    <tbody>{resources_html}</tbody>
  </table>

  <h2>Ödeme Takvimi</h2>
  <table>
    <thead><tr><th>Vade</th><th>Etiket</th><th class='r'>Tutar</th>
      <th>Durum</th></tr></thead>
    <tbody>{schedule_html}</tbody>
  </table>

  <h2>Teknik Gereksinimler</h2>
  {tech_html}

  <h2>Personel Ataması</h2>
  <table>
    <thead><tr><th>Rol</th><th>Kişi</th><th>Not</th></tr></thead>
    <tbody>{staff_html}</tbody>
  </table>

  {('<h2>Eğlence / Program</h2>' + ent_html) if ent_html else ''}

  <h2>Toplamlar</h2>
  <table class="totals">
    <tr><td class='k'>Mekan Toplamı</td><td class='r'>{_money(totals.get('space_total'))}</td></tr>
    <tr><td class='k'>Kaynak Toplamı</td><td class='r'>{_money(totals.get('resources_total'))}</td></tr>
    <tr class='grand'><td class='k'>GRAND TOTAL</td><td class='r'>{_money(totals.get('grand_total'))}</td></tr>
  </table>

  <div class="footer">
    Syroce PMS · Banquet Event Order · Etkinlik ID: {_e(ev.get('id') or '')}
  </div>
</body></html>"""


def _beo_pdf_bytes(payload: dict) -> bytes:
    """Render BEO HTML → PDF via weasyprint (lazy import).

    Fails loudly when weasyprint is unavailable so the caller surfaces a
    clear error instead of returning an empty/silent response.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            500, f"PDF üretimi için weasyprint yüklü değil: {exc}",
        ) from exc
    return HTML(string=_beo_html(payload)).write_pdf()


@router.get("/events/{event_id}/beo.pdf")
async def beo_pdf(event_id: str,
                  current_user: User = Depends(get_current_user)):
    """Printable BEO sheet — same payload as JSON endpoint, rendered as PDF."""
    from fastapi.responses import Response
    payload = await beo(event_id, current_user)  # tenant-scoped 404 inside
    pdf = _beo_pdf_bytes(payload)
    filename = f"beo-{event_id}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class BeoEmailRequest(BaseModel):
    recipients: list[str] = Field(default_factory=list)
    note: str | None = None


@router.post("/events/{event_id}/beo/email")
async def beo_email(
    event_id: str,
    body: BeoEmailRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict[str, Any]:
    """E-mail the BEO PDF to one or more recipients.

    Mirrors the konaklama_vergisi `email_declaration` pattern: reuse the
    existing weasyprint render + per-recipient `send_email` send so each
    delivery gets its own provider trace. Tenant scope comes from the
    `beo()` helper which 404s when the event belongs to another tenant.
    """
    from core.email import _is_valid_email, send_email
    from core.mailing_safe import safe_html_value

    payload = await beo(event_id, current_user)  # tenant-scoped 404 inside
    ev = payload.get("event") or {}

    seen: set[str] = set()
    targets: list[str] = []
    for r in body.recipients or []:
        if not isinstance(r, str):
            continue
        rs = r.strip()
        if not rs or not _is_valid_email(rs):
            continue
        k = rs.lower()
        if k in seen:
            continue
        seen.add(k)
        targets.append(rs)
    if not targets:
        raise HTTPException(
            400, "Alıcı bulunamadı — en az bir geçerli e-posta adresi girin.")

    pdf_bytes = _beo_pdf_bytes(payload)
    event_name = ev.get("name") or "Etkinlik"
    safe_filename = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (event_name or "beo")
    ).strip("_") or "beo"
    filename = f"{safe_filename}-{event_id}.pdf"
    subject = f"Banquet Event Order — {event_name}"

    note_html = ""
    if body.note:
        note_html = (
            f"<p style='margin:0 0 12px;color:#0f172a;'>"
            f"{safe_html_value(body.note)}</p>"
        )
    html = (
        "<div style='font-family:Helvetica,Arial,sans-serif;max-width:600px;"
        "margin:0 auto;padding:18px;color:#0f172a;'>"
        f"<h2 style='margin:0 0 8px;'>Banquet Event Order — "
        f"{safe_html_value(event_name)}</h2>"
        f"<p style='color:#64748b;margin:0 0 16px;'>"
        f"Tarih: <b>{safe_html_value(str(ev.get('start_date') or '-'))}</b> → "
        f"<b>{safe_html_value(str(ev.get('end_date') or '-'))}</b> &middot; "
        f"Pax: <b>{safe_html_value(str(ev.get('expected_pax') or '-'))}</b>"
        "</p>"
        f"{note_html}"
        "<p style='margin:0 0 8px;'>BEO detayları PDF olarak ekte yer "
        "almaktadır.</p>"
        "<p style='font-size:11px;color:#94a3b8;margin-top:18px;'>"
        "Syroce PMS · Otomatik üretilmiş bildirim"
        "</p></div>"
    )
    attachments = [{
        "filename": filename,
        "content": pdf_bytes,
        "content_type": "application/pdf",
    }]

    sent_ok = 0
    failures: list[dict] = []
    for to in targets:
        res = await send_email(
            to=to, subject=subject, html=html, attachments=attachments,
        )
        if res.get("sent"):
            sent_ok += 1
        else:
            failures.append(
                {"to": to, "error": res.get("error") or res.get("provider")})

    db = get_system_db()
    await log_audit_event(
        tenant_id=current_user.tenant_id, user_id=current_user.username,
        action="email", entity_type="mice_event_beo",
        entity_id=event_id,
        details=(f"BEO PDF gönderildi: {sent_ok}/{len(targets)} "
                 f"({', '.join(targets)})"),
        before_value=None,
        after_value={"recipients": targets, "ok": sent_ok,
                     "failures": failures,
                     "note": body.note or None},
        db=db)
    return {
        "sent": sent_ok,
        "total": len(targets),
        "recipients": targets,
        "failures": failures,
    }


# ── Payment schedule (deposit + milestones) ─────────────────────
class PaymentScheduleReplace(BaseModel):
    items: list[PaymentScheduleItemIn]


@router.post("/events/{event_id}/payment-schedule")
async def replace_payment_schedule(
    event_id: str, body: PaymentScheduleReplace,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    items = []
    for it in body.items:
        d = it.model_dump()
        d["due_date"] = d["due_date"].isoformat() if hasattr(d["due_date"], "isoformat") else d["due_date"]
        if d.get("paid_at") and hasattr(d["paid_at"], "isoformat"):
            d["paid_at"] = d["paid_at"].isoformat()
        items.append(d)
    res = await db.mice_events.update_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
        {"$set": {"payment_schedule": items,
                  "updated_at": datetime.now(UTC).isoformat()}})
    if not res.matched_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    _invalidate_mice_events_cache(current_user.tenant_id)
    return {"ok": True, "count": len(items)}


@router.post("/events/{event_id}/payment-schedule/{idx}/mark-paid")
async def mark_payment_paid(
    event_id: str, idx: int,
    reference: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
) -> dict:
    require_finance(current_user)  # marking payment touches AR
    db = get_system_db()
    # Bound-check first.
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
        {"payment_schedule": 1})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    sched_len = len(event.get("payment_schedule") or [])
    if idx < 0 or idx >= sched_len:
        raise HTTPException(404, "Ödeme satırı bulunamadı")
    # Atomic positional $set — yarış güvenli, başka bir taksitin
    # işaretlenmesini overwrite etmez.
    paid_at = datetime.now(UTC).isoformat()
    set_ops = {
        f"payment_schedule.{idx}.paid": True,
        f"payment_schedule.{idx}.paid_at": paid_at,
    }
    if reference:
        set_ops[f"payment_schedule.{idx}.reference"] = reference
    res = await db.mice_events.update_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
        {"$set": set_ops})
    if not res.matched_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    # Tek satırı oku ve döndür.
    fresh = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
        {"payment_schedule": 1})
    _invalidate_mice_events_cache(current_user.tenant_id)
    return {"ok": True, "item": (fresh.get("payment_schedule") or [None])[idx]}


# ── Kitchen ticket (per-event, per-meal production sheet) ──────
@router.get("/events/{event_id}/kitchen-ticket")
async def kitchen_ticket(event_id: str,
                         current_user: User = Depends(get_current_user)) -> dict:
    """Generate a kitchen production sheet for the event:
    every F&B menu line × pax, with course breakdown, allergen/dietary
    aggregation, and prep-by time = (earliest meal in agenda) − lead time.
    """
    db = get_system_db()
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")

    pax = int(event.get("expected_pax") or 0)
    menu_ids = [r["menu_id"] for r in event.get("resources", [])
                if r.get("menu_id")]
    menus = {m["id"]: m async for m in db.mice_menus.find(
        {"tenant_id": current_user.tenant_id, "id": {"$in": menu_ids}})}

    # Earliest meal/break in the agenda → kitchen prep deadline.
    meals = [a for a in event.get("agenda", [])
             if a.get("kind") in {"meal", "break"}]
    earliest = min((a["starts_at"] for a in meals), default=None)

    tickets = []
    allergen_set: set[str] = set()
    dietary_set: set[str] = set()
    for r in event.get("resources", []):
        if r.get("type") != "fb" or not r.get("menu_id"):
            continue
        m = menus.get(r["menu_id"])
        if not m:
            continue
        qty = float(r.get("quantity") or 0) or pax
        prep = m.get("prep_lead_minutes", 30)
        prep_by = None
        if earliest:
            try:
                start_dt = datetime.fromisoformat(earliest)
                prep_by = (start_dt - timedelta(minutes=prep)).isoformat()
            except Exception:
                prep_by = None
        for a in m.get("allergens") or []:
            allergen_set.add(a)
        for d in m.get("dietary_tags") or []:
            dietary_set.add(d)
        tickets.append({
            "menu_name": m["name"],
            "qty_pax": qty,
            "courses": m.get("courses") or [],
            "allergens": m.get("allergens") or [],
            "dietary_tags": m.get("dietary_tags") or [],
            "prep_lead_minutes": prep,
            "prep_by": prep_by,
            "notes": r.get("notes"),
        })
    return {
        "event_id": event_id,
        "event_name": event.get("name"),
        "expected_pax": pax,
        "first_service_at": earliest,
        "tickets": tickets,
        "all_allergens": sorted(allergen_set),
        "all_dietary_tags": sorted(dietary_set),
    }


# ── F&B order send (BEO → kitchen production order) ─────────────
class FnbOrderSendRequest(BaseModel):
    """Send the event's F&B lines to the kitchen as a production order.

    `target` lets the banquet team route the order to a specific outlet /
    kitchen; `note` is a free-text production instruction.
    """
    target: str = "kitchen"  # kitchen / restaurant / outlet code
    note: str | None = None


def _build_fnb_lines(event: dict) -> list[dict]:
    """Snapshot the event's F&B (type == 'fb') resource lines into an
    immutable order payload. Quantity falls back to the event pax when a
    line has no explicit quantity (mirrors kitchen-ticket behaviour)."""
    pax = int(event.get("expected_pax") or 0)
    lines: list[dict] = []
    for r in event.get("resources", []):
        if r.get("type") != "fb":
            continue
        qty = float(r.get("quantity") or 0) or pax
        lines.append({
            "menu_id": r.get("menu_id"),
            "name": r.get("name"),
            "quantity": qty,
            "unit": r.get("unit") or "pax",
            "unit_price": float(r.get("unit_price") or 0),
            "notes": r.get("notes"),
        })
    return lines


@router.post("/events/{event_id}/fnb-order/send")
async def send_fnb_order(
    event_id: str,
    body: FnbOrderSendRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # DW
) -> dict:
    """Send the event's F&B order lines to the kitchen as a production order.

    Builds an immutable snapshot from the event's F&B resource lines
    (type == "fb"), persists it to `mice_fnb_orders` (tenant-scoped) with
    status="sent", and returns it. This is an internal production-order
    record consumed by the kitchen-ticket / ops-sheet views — it makes NO
    external HTTP call.

    Guards:
      - Tenant-scoped 404 when the event belongs to another tenant.
      - RBAC: MICE ops roles only (`require_mice_ops`).
      - Status guard: only tentative/definite/confirmed/completed events may
        push a kitchen order; a `lead` (still pure inquiry) is rejected 409,
        a `cancelled` event 409.
      - Requires at least one F&B line, else 422.
      - Idempotent on Idempotency-Key (scoped per event) so a double-tap on
        the BEO "send order" button cannot create duplicate kitchen orders.
    """
    require_mice_ops(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")

    status = event.get("status", "lead")
    if status not in {"tentative", "definite", "confirmed", "completed"}:
        raise HTTPException(
            409,
            f"F&B siparişi yalnızca en az 'tentative' durumundaki etkinlikler "
            f"için gönderilebilir (mevcut durum: {status}).",
        )

    lines = _build_fnb_lines(event)
    if not lines:
        raise HTTPException(
            422, "Etkinlikte gönderilecek F&B (yiyecek-içecek) satırı yok.")

    # Idempotency-Key replay protection (scoped per event).
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db, tenant_id=tenant_id,
            scope=f"mice_fnb_order_send:{event_id}",
            idempotency_key=idem_key)
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                409, "Aynı Idempotency-Key ile başka bir istek işleniyor.")
        idem_lock_id = claim["lock_id"]

    try:
        order = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_id": event_id,
            "event_name": event.get("name"),
            "target": body.target,
            "status": "sent",
            "expected_pax": int(event.get("expected_pax") or 0),
            "lines": lines,
            "total": round(
                sum(line_["unit_price"] * line_["quantity"]
                    for line_ in lines), 2),
            "note": body.note,
            "sent_at": datetime.now(UTC).isoformat(),
            "sent_by": current_user.username,
        }
        await db.mice_fnb_orders.insert_one(order)
        order.pop("_id", None)
        await log_audit_event(
            tenant_id=tenant_id, user_id=current_user.username,
            action="fnb_order_send", entity_type="mice_event",
            entity_id=event_id,
            details=(f"F&B siparişi gönderildi: {event.get('name')} "
                     f"→ {body.target} ({len(lines)} satır)"),
            before_value=None, after_value=order, db=db)
        if idem_lock_id:
            await complete_idempotency(
                db, lock_id=idem_lock_id, response_body=order)
            idem_lock_id = None
        return order
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:  # noqa: BLE001
        if idem_lock_id:
            await release_idempotency(
                db, lock_id=idem_lock_id, error=str(exc))
        raise


@router.get("/events/{event_id}/fnb-orders")
async def list_fnb_orders(
    event_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """List the F&B production orders sent for an event (tenant-scoped).

    404s when the event belongs to another tenant so a cross-tenant id can't
    confirm/deny the existence of another hotel's event."""
    db = get_system_db()
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 1})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    cur = db.mice_fnb_orders.find(
        {"tenant_id": current_user.tenant_id, "event_id": event_id},
        {"_id": 0}).sort("sent_at", -1)
    return {"orders": [d async for d in cur]}


# ── Daily operations sheet (banquet team daily ops) ─────────────
@router.get("/ops-sheet")
async def ops_sheet(
    date: str | None = Query(None, description="YYYY-MM-DD (default: today)"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """All events whose date range covers *date*, with each space booking,
    setup style, pax, owner, and condensed agenda — printable per-day
    banquet team operations sheet."""
    # Tur 3: default — today when omitted
    if not date:
        from datetime import date as _d
        date = _d.today().isoformat()
    db = get_system_db()
    q = {
        "tenant_id": current_user.tenant_id,
        "status": {"$in": ["definite", "confirmed", "completed"]},
        "start_date": {"$lte": date},
        "end_date": {"$gte": date},
    }
    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": current_user.tenant_id})}
    rows = []
    async for ev in db.mice_events.find(q, {"_id": 0}):
        for sb in ev.get("space_bookings", []):
            sp = spaces_by_id.get(sb["space_id"], {})
            rows.append({
                "event_id": ev["id"],
                "event_name": ev.get("name"),
                "client_name": ev.get("client_name"),
                "organizer_user": ev.get("organizer_user"),
                "space_name": sp.get("name", "—"),
                "starts_at": sb["starts_at"],
                "ends_at": sb["ends_at"],
                "setup_style": sb.get("setup_style"),
                "expected_pax": sb.get("expected_pax"),
                "agenda_summary": [
                    {"starts_at": a["starts_at"], "title": a["title"],
                     "kind": a.get("kind")}
                    for a in (ev.get("agenda") or [])
                    if str(a.get("starts_at", "")).startswith(date)
                ],
            })
    rows.sort(key=lambda r: (r["starts_at"], r["space_name"]))
    return {"date": date, "rows": rows, "count": len(rows)}
