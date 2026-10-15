"""Move hotel-bound (legacy portal) agencies onto the multi-hotel marketplace.

Super admin only. ``preview`` reports, per active legacy agency of a hotel, what
would move and any conflict; ``execute`` applies the chosen mapping (or only
plans it with ``dry_run``). For each legacy agency:

* target marketplace agency: an existing one chosen by the operator, or a new
  one created from the legacy agency card;
* contract: the legacy contract terms (commission or net-rate seasons, credit
  limit, dates) become an approved marketplace contract, unless the target
  already has a pending/approved contract with this hotel;
* users: legacy portal users become marketplace users of the target agency
  with the same e-mail and password (same login screen, now multi-hotel);
  e-mails already used by another marketplace agency are skipped and reported;
* future active bookings are re-pointed to the target agency and written to
  the marketplace ledger so they appear in statements; history is untouched;
* the legacy agency is marked ``migrated`` (legacy login then falls through
  to the marketplace login).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.tenant_db import get_system_db
from routers.marketplace_b2b import _require_system_admin

logger = logging.getLogger("routers.agency_migration")
router = APIRouter(prefix="/api/marketplace/v1/admin/legacy-migration", tags=["Marketplace v1 / Legacy migration"])

ACTIVE_BOOKING_STATUSES = ["confirmed", "guaranteed", "checked_in", "pending"]
LEGACY_ROLES = ["agency_admin", "agency_agent"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _norm(value) -> str:
    return str(value or "").strip().casefold()


class MigrationItem(BaseModel):
    legacy_agency_id: str = Field(..., min_length=1)
    # None: create a new marketplace agency from the legacy card.
    marketplace_agency_id: str | None = None


class MigrationRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    items: list[MigrationItem] = Field(..., min_length=1, max_length=200)
    dry_run: bool = True


async def _legacy_snapshot(sysdb, tenant_id: str, agency: dict) -> dict:
    agency_id = agency["id"]
    today = _today()
    contract = await sysdb.agency_contracts.find_one(
        {"tenant_id": tenant_id, "agency_id": agency_id, "is_active": True, "end_date": {"$gte": today}},
        {"_id": 0}, sort=[("start_date", -1)],
    )
    users = await sysdb.users.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "role": {"$in": LEGACY_ROLES}},
        {"_id": 0, "id": 1, "email": 1, "_hash_email": 1, "name": 1},
    ).to_list(200)
    future = await sysdb.bookings.count_documents({
        "tenant_id": tenant_id, "agency_id": agency_id, "status": {"$in": ACTIVE_BOOKING_STATUSES},
        "check_out": {"$gte": today},
    })
    allotments = await sysdb.agency_allotments.count_documents(
        {"tenant_id": tenant_id, "agency_id": agency_id, "end_date": {"$gte": today}}
    )
    return {"contract": contract, "users": users, "future_bookings": future, "allotments": allotments}


async def _suggest_target(sysdb, agency: dict) -> dict | None:
    email = _norm(agency.get("contact_email"))
    name = _norm(agency.get("name"))
    async for candidate in sysdb.marketplace_agencies.find({"status": "active"}, {"_id": 0, "id": 1, "name": 1, "contact_email": 1}):
        if (email and _norm(candidate.get("contact_email")) == email) or (name and _norm(candidate.get("name")) == name):
            return candidate
    return None


@router.get("/preview")
async def migration_preview(tenant_id: str = Query(..., min_length=1), _: bool = Depends(_require_system_admin)):
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0, "is_listed": 1})
    agencies = await sysdb.agencies.find({"tenant_id": tenant_id, "status": {"$in": ["active", "migrating"]}}, {"_id": 0}).to_list(500)
    rows = []
    for agency in agencies:
        snapshot = await _legacy_snapshot(sysdb, tenant_id, agency)
        contract = snapshot["contract"]
        warnings = []
        if agency.get("status") == "migrating":
            warnings.append("Önceki taşıma yarıda kaldı: tekrar çalıştırınca aynı hedef acenteyle kaldığı yerden tamamlanır.")
        if not contract:
            warnings.append("Aktif eski sözleşme yok: acentenin varsayılan komisyonuyla 1 yıllık komisyon sözleşmesi açılır.")
        if snapshot["allotments"]:
            warnings.append(f"{snapshot['allotments']} kontenjan tanımı taşınmaz; fiyat yöneticisinden acenteye kontenjan girin.")
        if not snapshot["users"]:
            warnings.append("Portal kullanıcısı yok; taşıma sonrası acenteye davet gönderin.")
        rows.append({
            "legacy_agency": {k: agency.get(k) for k in ("id", "name", "contact_email", "contact_phone", "commission_rate")},
            "contract": contract and {k: contract.get(k) for k in ("contract_type", "commission_rate", "start_date", "end_date", "credit_limit", "credit_currency")},
            "season_rate_count": len((contract or {}).get("season_rates") or []),
            "user_count": len(snapshot["users"]),
            "future_bookings": snapshot["future_bookings"],
            "suggested_target": await _suggest_target(sysdb, agency),
            "warnings": warnings,
        })
    return {
        "tenant_id": tenant_id,
        "marketplace_listed": (listing or {}).get("is_listed") is not False,
        "notes": ["Tesis acente listesinden gizlenmiş: yeni teklif almaz, taşınan sözleşmeler çalışmaya devam eder."]
        if (listing or {}).get("is_listed") is False else [],
        "agencies": rows,
    }


def migration_target_id(tenant_id: str, legacy_agency_id: str) -> str:
    """Stable marketplace agency id for a legacy agency (retry-safe)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"syroce:legacy-agency:{tenant_id}:{legacy_agency_id}"))


def _contract_terms(legacy_contract: dict | None, agency: dict) -> dict:
    today = datetime.now(UTC).date()
    if not legacy_contract:
        return {
            "contract_type": "commission", "commission_pct": float(agency.get("commission_rate") or 0), "season_rates": [],
            "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=365)).isoformat(),
            "credit_limit": None, "credit_currency": None, "allow_base_rate_fallback": False,
        }
    is_net = legacy_contract.get("contract_type") == "net_rate"
    commission = 0.0 if is_net else float(
        legacy_contract.get("commission_rate") if legacy_contract.get("commission_rate") is not None else agency.get("commission_rate") or 0
    )
    valid_from = max(str(legacy_contract.get("start_date")), today.isoformat())
    valid_to = min(str(legacy_contract.get("end_date")), (today + timedelta(days=730)).isoformat())
    return {
        "contract_type": "net_rate" if is_net else "commission",
        "commission_pct": commission,
        "season_rates": [
            {k: season.get(k) for k in ("room_type_id", "season_start", "season_end", "price")}
            for season in legacy_contract.get("season_rates") or []
        ],
        "valid_from": valid_from, "valid_to": valid_to,
        "credit_limit": legacy_contract.get("credit_limit"), "credit_currency": legacy_contract.get("credit_currency"),
        "allow_base_rate_fallback": bool(legacy_contract.get("allow_base_rate_fallback")),
    }


async def _migrate_one(sysdb, tenant_id: str, hotel_name: str, item: MigrationItem, *, dry_run: bool, actor: str) -> dict:
    from routers.agency_contracts import _ensure_indexes, _next_contract_code

    agency = await sysdb.agencies.find_one({"id": item.legacy_agency_id, "tenant_id": tenant_id}, {"_id": 0})
    # "migrating" = an earlier run stopped part-way: resume it, same target.
    if not agency or agency.get("status") not in ("active", "migrating"):
        return {"legacy_agency_id": item.legacy_agency_id, "error": "Aktif eski acente bulunamadı"}
    snapshot = await _legacy_snapshot(sysdb, tenant_id, agency)
    plan: dict = {"legacy_agency_id": agency["id"], "legacy_agency_name": agency.get("name"), "actions": [], "skipped": []}
    resumed_target = agency.get("migration_target_id")
    if resumed_target:
        plan["actions"].append("Yarıda kalan taşıma aynı hedef acenteyle tamamlanır")

    # 1. Target marketplace agency. The id is fixed per legacy agency (or the
    # one an interrupted run recorded), so a retry never creates a second one.
    requested = item.marketplace_agency_id or resumed_target
    if resumed_target and item.marketplace_agency_id and item.marketplace_agency_id != resumed_target:
        return {**plan, "error": "Yarıda kalan taşıma başka bir hedef acenteye başlamıştı; aynı hedefle tekrar deneyin"}
    if requested:
        target = await sysdb.marketplace_agencies.find_one({"id": requested, "status": "active"}, {"_id": 0})
        if not target:
            return {**plan, "error": "Hedef marketplace acentesi bulunamadı veya aktif değil"}
        plan["actions"].append(f"Mevcut marketplace acentesine bağlanır: {target.get('name')}")
    else:
        target = {
            "id": migration_target_id(tenant_id, agency["id"]), "name": agency.get("name"), "contact_email": agency.get("contact_email", ""),
            "contact_phone": agency.get("contact_phone", ""), "country": "TR",
            "default_commission_pct": float(agency.get("commission_rate") or 0), "status": "active", "created_at": _now(),
            "migrated_from": {"tenant_id": tenant_id, "legacy_agency_id": agency["id"]},
        }
        plan["actions"].append(f"Yeni marketplace acentesi oluşturulur: {target['name']}")
        if not dry_run:
            await sysdb.marketplace_agencies.update_one({"id": target["id"]}, {"$setOnInsert": dict(target)}, upsert=True)
    plan["marketplace_agency_id"] = target["id"]
    if not dry_run:
        # Record the target before moving anything; the legacy portal stops
        # selling for this agency while its users and bookings move.
        await sysdb.agencies.update_one({"id": agency["id"], "tenant_id": tenant_id}, {"$set": {
            "status": "migrating", "migration_target_id": target["id"], "migration_started_at": _now(), "updated_at": _now(),
        }})

    # 2. Contract
    existing = await sysdb.agency_contracts.find_one(
        {"tenant_id": tenant_id, "agency_id": target["id"], "status": {"$in": ["pending", "approved"]}},
        {"_id": 0, "contract_code": 1, "status": 1},
    )
    if existing:
        plan["skipped"].append(f"Sözleşme açılmadı: {existing['contract_code']} zaten {existing['status']}")
    else:
        terms = _contract_terms(snapshot["contract"], agency)
        plan["actions"].append(
            f"Onaylı {terms['contract_type']} sözleşmesi: {terms['valid_from']} – {terms['valid_to']}"
            + (f", {len(terms['season_rates'])} sezon" if terms["season_rates"] else f", komisyon %{terms['commission_pct']:g}")
        )
        if not dry_run:
            await _ensure_indexes()
            await sysdb.agency_contracts.insert_one({
                "id": str(uuid.uuid4()), "contract_code": await _next_contract_code(sysdb),
                "agency_id": target["id"], "agency_name": target.get("name", ""), "agency_email": target.get("contact_email", ""),
                "tenant_id": tenant_id, "hotel_name": hotel_name, "status": "approved",
                **terms, "agency_proposed_commission_pct": terms["commission_pct"],
                "hotel_approved_commission_pct": terms["commission_pct"],
                "cancellation_policy": {"free_until_days_before": 7, "penalty_pct": 50.0, "no_show_penalty_pct": 100.0},
                "payment_terms": "on_arrival", "currency": terms.get("credit_currency") or "TRY",
                "allowed_room_types": [], "special_terms": "Otele bağlı acente portalından taşındı",
                "webhook_url": None, "is_migration": True, "migrated_from_legacy_agency_id": agency["id"],
                "proposed_at": _now(), "decided_at": _now(), "decided_by": actor, "decision_notes": "Eski portal taşıması",
                "created_at": _now(), "updated_at": _now(),
            })

    # 3. Users
    for user in snapshot["users"]:
        clash = await sysdb.users.find_one(
            {"id": {"$ne": user["id"]}, "role": "marketplace_agent",
             **({"_hash_email": user["_hash_email"]} if user.get("_hash_email") else {"email": user.get("email")})},
            {"_id": 0, "agency_id": 1},
        )
        if clash and clash.get("agency_id") != target["id"]:
            plan["skipped"].append(f"Kullanıcı {user.get('name') or user['id']}: e-posta başka bir marketplace acentesinde kayıtlı")
            continue
        plan["actions"].append(f"Kullanıcı marketplace girişine taşınır: {user.get('name') or user['id']}")
        if not dry_run:
            full = await sysdb.users.find_one({"id": user["id"]}, {"_id": 0, "hashed_password": 1, "password_hash": 1, "password": 1}) or {}
            update = {
                "role": "marketplace_agent", "roles": ["marketplace_agent"], "agency_id": target["id"], "tenant_id": None,
                "legacy_agency_id": agency["id"], "migrated_from_tenant_id": tenant_id, "is_active": True,
                "updated_at": _now(),
            }
            # The marketplace login reads hashed_password only; legacy rows may
            # keep the same bcrypt hash under an older field name.
            if not full.get("hashed_password") and (full.get("password_hash") or full.get("password")):
                update["hashed_password"] = full.get("password_hash") or full.get("password")
            await sysdb.users.update_one({"id": user["id"]}, {"$set": update})

    # 4. Future bookings
    today = _today()
    bookings = await sysdb.bookings.find({
        "tenant_id": tenant_id, "status": {"$in": ACTIVE_BOOKING_STATUSES}, "check_out": {"$gte": today},
        # Bookings an interrupted run already re-pointed still need their ledger row.
        "$or": [{"agency_id": agency["id"]}, {"legacy_agency_id": agency["id"], "agency_id": target["id"]}],
    }, {"_id": 0}).to_list(5000)
    if bookings:
        plan["actions"].append(f"{len(bookings)} gelecek rezervasyon marketplace acentesine bağlanır ve deftere işlenir")
    if not dry_run:
        for booking in bookings:
            total = float(booking.get("total_amount") or 0)
            commission = float(booking.get("agency_commission_amount") or 0)
            await sysdb.bookings.update_one({"id": booking["id"], "tenant_id": tenant_id}, {"$set": {
                "agency_id": target["id"], "agency_name": target.get("name"), "legacy_agency_id": agency["id"], "updated_at": _now(),
            }})
            await sysdb.marketplace_bookings.update_one({"id": booking["id"]}, {"$setOnInsert": {
                "id": booking["id"], "agency_id": target["id"], "agency_name": target.get("name"), "tenant_id": tenant_id,
                "hotel_name": hotel_name, "confirmation_code": booking.get("confirmation_code"), "guest_name": booking.get("guest_name"),
                "room_type": booking.get("room_type"), "room_number": booking.get("room_number"),
                "check_in": str(booking.get("check_in") or "")[:10], "check_out": str(booking.get("check_out") or "")[:10],
                "total_amount": total, "currency": booking.get("currency") or "TRY",
                "commission_pct": float(booking.get("agency_commission_rate") or 0), "commission_amount": commission,
                "syroce_b2b_fee_pct": 0.0, "syroce_b2b_fee_amount": 0.0, "net_to_hotel": round(total - commission, 2),
                "status": booking.get("status"), "payment_status": booking.get("payment_status"),
                "payment_terms": "on_arrival", "cancellation_policy": {}, "migrated_from_legacy": True,
                "created_at": booking.get("created_at") or _now(),
            }}, upsert=True)

    # 5. Legacy agency
    plan["actions"].append("Eski acente kaydı 'taşındı' olarak işaretlenir")
    if not dry_run:
        await sysdb.agencies.update_one({"id": agency["id"], "tenant_id": tenant_id}, {"$set": {
            "status": "migrated", "migrated_to_marketplace_agency_id": target["id"], "migrated_at": _now(), "updated_at": _now(),
        }, "$unset": {"migration_target_id": "", "migration_started_at": ""}})
    return plan


@router.post("/execute")
async def migration_execute(data: MigrationRequest, _: bool = Depends(_require_system_admin)):
    sysdb = get_system_db()
    tenant = await sysdb.tenants.find_one({"id": data.tenant_id}, {"_id": 0, "property_name": 1, "name": 1})
    if not tenant:
        raise HTTPException(404, "Otel bulunamadı")
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": data.tenant_id}, {"_id": 0, "hotel_name": 1})
    hotel_name = (listing or {}).get("hotel_name") or tenant.get("property_name") or tenant.get("name") or ""
    actor = "superadmin:legacy-migration"
    results = []
    for item in data.items:
        try:
            results.append(await _migrate_one(sysdb, data.tenant_id, hotel_name, item, dry_run=data.dry_run, actor=actor))
        except Exception as exc:  # noqa: BLE001 - one agency must not block the rest
            logger.error("Legacy migration failed agency=%s error=%s", item.legacy_agency_id, type(exc).__name__)
            results.append({"legacy_agency_id": item.legacy_agency_id, "error": f"Beklenmeyen hata: {type(exc).__name__}"})
    if not data.dry_run:
        await sysdb.agency_migrations.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": data.tenant_id, "items": [i.model_dump() for i in data.items],
            "results": results, "created_at": _now(),
        })
    return {"dry_run": data.dry_run, "results": results}
