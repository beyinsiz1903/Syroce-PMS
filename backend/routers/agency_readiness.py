"""Why is an agency not selling? The hotel's sales-readiness view.

For every agency the hotel has (had) a contract with, one checklist: agency
account, portal user and invitation, contract and pending amendment,
credit, the agency's searches at this hotel in the last 30 days and why
they came back empty (recorded by the search itself), and bookings. Each
problem carries the screen that fixes it. On demand, the next 30 nights are
checked with the same pricing engine as search and booking.

Hotel (PMS JWT):   /api/marketplace/hotel/agency-readiness
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from core.tenant_db import get_system_db, tenant_context
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin

hotel_router = APIRouter(prefix="/api/marketplace/hotel/agency-readiness", tags=["Marketplace / Agency readiness (hotel)"])

SEARCH_WINDOW_DAYS = 30
PROBE_ADULTS = 2  # the night check asks what a 2-adult search would find
RATE_PAGE = "/unified-rate-manager"
CONTRACTS_PAGE = "/app/incoming-agency-contracts"
STATEMENTS_PAGE = "/app/agency-statements"
REASONS = {
    "no_rate": ("Fiyat paylaşılmamış", "Fiyat paylaş", RATE_PAGE),
    "no_price": ("Fiyat tanımı satışa uygun değil (sıfır fiyat, para birimi, kişi fiyatı kuralı)", "Fiyatları kontrol et", RATE_PAGE),
    "restricted": ("Satış kısıtı (min/max konaklama, varış/çıkış kapalı)", "Kısıtları kontrol et", RATE_PAGE),
    "no_availability": ("Müsaitlik / kontenjan yok", "Kontenjan aç", RATE_PAGE),
    "no_room": ("Uygun oda tipi yok (kişi sayısı veya sözleşmedeki oda tipleri)", "Sözleşmeyi incele", CONTRACTS_PAGE),
    "closed": ("Tarih satışa kapalı", "Kapalı tarihleri kontrol et", RATE_PAGE),
    "filters": ("Acentenin filtreleri (özellik, pansiyon, fiyat üst sınırı)", None, None),
    "no_contract": ("Bu tarihlerde geçerli sözleşme yok", "Sözleşmeyi incele", CONTRACTS_PAGE),
}


def _check(key: str, level: str, message: str, action: tuple[str, str] | None = None) -> dict:
    return {"key": key, "level": level, "message": message,
            "action": {"label": action[0], "path": action[1]} if action and action[0] else None}


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


async def _credit(tenant_id: str, agency_id: str, contract: dict, sysdb) -> dict | None:
    from core.agency_credit import credit_usage
    from core.database import db

    try:
        with tenant_context(tenant_id):
            return await credit_usage(db, tenant_id=tenant_id, agency_id=agency_id, contract=contract, statements_db=sysdb)
    except HTTPException as exc:
        return {"error": exc.detail}


async def agency_readiness(sysdb, tenant_id: str, today: date, *, credit=None) -> list[dict]:
    credit = credit or _credit
    contracts: dict[str, dict] = {}
    async for contract in sysdb.agency_contracts.find(
        {"tenant_id": tenant_id, "contract_code": {"$type": "string"},
         "status": {"$in": ["approved", "pending", "expired", "terminated"]}},
        {"_id": 0},
    ).sort("created_at", -1):
        current = contracts.get(contract["agency_id"])
        # An approved contract wins; otherwise the newest one.
        if current is None or (contract.get("status") == "approved" and current.get("status") != "approved"):
            contracts[contract["agency_id"]] = contract
    since = (today - timedelta(days=SEARCH_WINDOW_DAYS)).isoformat()
    rows = []
    for agency_id, contract in contracts.items():
        agency = await sysdb.marketplace_agencies.find_one({"id": agency_id}, {"_id": 0, "name": 1, "status": 1}) or {}
        users = await sysdb.users.find({"agency_id": agency_id, "role": "marketplace_agent"},
                                       {"_id": 0, "is_active": 1, "onboarding_status": 1, "agency_invite_expires": 1, "last_login": 1}).to_list(200)
        active_users = [u for u in users if u.get("is_active") is not False and u.get("onboarding_status") != "invited"]
        invited = [u for u in users if u.get("onboarding_status") == "invited"]
        last_login = max((str(u["last_login"]) for u in active_users if u.get("last_login")), default=None)
        searches = await sysdb.marketplace_search_log.find(
            {"agency_id": agency_id, "at": {"$gte": since}}, {"_id": 0, "at": 1, "outcomes": 1}).to_list(5000)
        here = [s["outcomes"][tenant_id] for s in searches if tenant_id in (s.get("outcomes") or {})]
        reasons = Counter(here)
        bookings = await sysdb.marketplace_bookings.find(
            {"tenant_id": tenant_id, "agency_id": agency_id}, {"_id": 0, "created_at": 1, "status": 1}).to_list(5000)
        last_booking = max((str(b.get("created_at") or "") for b in bookings), default=None)

        checks = []
        if agency.get("status") == "active":
            checks.append(_check("agency", "ok", "Acente hesabı aktif"))
        else:
            checks.append(_check("agency", "error", "Acente hesabı aktif değil; acente satış yapamaz. Syroce desteğiyle görüşün."))
        if active_users:
            checks.append(_check("portal_user", "ok", f"{len(active_users)} aktif portal kullanıcısı"))
        elif invited:
            expired = all((_as_date(u.get("agency_invite_expires")) or today) < today for u in invited)
            checks.append(_check("portal_user", "error", "Davet " + ("süresi dolmuş, yenilenmeli" if expired else "henüz kabul edilmemiş")
                                 + "; acente portala giremiyor. Syroce desteği daveti yeniden gönderebilir."))
        else:
            checks.append(_check("portal_user", "error", "Acentenin portal kullanıcısı yok; Syroce desteği davet göndermeli."))
        if active_users:
            login_day = _as_date(last_login)
            if not login_day:
                checks.append(_check("login", "warn", "Acente portala hiç giriş yapmadı."))
            elif (today - login_day).days > SEARCH_WINDOW_DAYS:
                checks.append(_check("login", "warn", f"Son giriş {login_day.isoformat()}; acente uzun süredir portala girmiyor."))
            else:
                checks.append(_check("login", "ok", f"Son giriş {login_day.isoformat()}"))

        status = contract.get("status")
        valid_to = _as_date(contract.get("valid_to"))
        valid_from = _as_date(contract.get("valid_from"))
        if status == "pending":
            checks.append(_check("contract", "error", "Sözleşme teklifi onayınızı bekliyor.", ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        elif status != "approved":
            checks.append(_check("contract", "error", f"Sözleşme {'süresi dolmuş' if status == 'expired' else 'feshedilmiş'}; satış kapalı.",
                                 ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        elif valid_to and valid_to < today:
            checks.append(_check("contract", "error", f"Sözleşmenin süresi {valid_to.isoformat()} tarihinde doldu; satış kapalı. Uzatmak için değişiklik önerin.",
                                 ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        elif valid_from and valid_from > today:
            checks.append(_check("contract", "warn", f"Sözleşme {valid_from.isoformat()} tarihinde başlıyor.", ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        elif valid_to and (valid_to - today).days <= 30:
            checks.append(_check("contract", "warn", f"Sözleşme {valid_to.isoformat()} tarihinde bitiyor; uzatmak için değişiklik önerin.",
                                 ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        else:
            checks.append(_check("contract", "ok", f"Sözleşme geçerli ({contract.get('valid_from')} – {contract.get('valid_to')})"))
        if contract.get("pending_amendment"):
            side = "Acentenin" if contract["pending_amendment"].get("proposed_by_side") == "agency" else "Sizin"
            checks.append(_check("amendment", "warn", f"{side} yanıt bekleyen sözleşme değişikliği teklifi var.", ("Sözleşmeyi incele", CONTRACTS_PAGE)))

        usage = await credit(tenant_id, agency_id, contract, sysdb) if status == "approved" else None
        if usage and usage.get("error"):
            checks.append(_check("credit", "error", str(usage["error"]), ("Ekstre ve ödemeler", STATEMENTS_PAGE)))
        elif usage:
            if usage["available"] <= 0:
                checks.append(_check("credit", "error", f"Kredi limiti dolu ({usage['used']:.2f}/{usage['limit']:.2f} {usage['currency']}); yeni satış reddedilir.",
                                     ("Ekstre ve ödemeler", STATEMENTS_PAGE)))
            elif usage["available"] < usage["limit"] * 0.2:
                checks.append(_check("credit", "warn", f"Kredinin %80'inden fazlası kullanılmış; kalan {usage['available']:.2f} {usage['currency']}.",
                                     ("Ekstre ve ödemeler", STATEMENTS_PAGE)))
            else:
                checks.append(_check("credit", "ok", f"Kalan kredi {usage['available']:.2f} {usage['currency']}"))

        ok_count = reasons.get("ok", 0)
        if not searches:
            checks.append(_check("searches", "warn", f"Acente son {SEARCH_WINDOW_DAYS} günde hiç arama yapmadı."))
        elif not here:
            checks.append(_check("searches", "warn", f"Acente {len(searches)} arama yaptı ama otel hiçbirinde değerlendirilmedi "
                                 "(arama tarihlerinde sözleşme yok veya şehir/otel filtresi dışında).", ("Sözleşmeyi incele", CONTRACTS_PAGE)))
        elif ok_count == 0:
            top, count = next((item for item in reasons.most_common() if item[0] != "ok"), ("filters", 0))
            label, action, path = REASONS.get(top, (top, None, None))
            checks.append(_check("searches", "error", f"{len(here)} aramanın hiçbirinde oteliniz sonuç vermedi; en sık neden: {label} ({count}).",
                                 (action, path) if action else None))
        else:
            empty = len(here) - ok_count
            level = "warn" if empty > ok_count else "ok"
            checks.append(_check("searches", level, f"{len(here)} aramanın {ok_count} tanesinde oteliniz sonuç verdi."))

        stays = [b for b in bookings if b.get("status") not in ("cancelled", "no_show")]
        if not bookings:
            checks.append(_check("bookings", "warn", "Henüz rezervasyon yok."))
        else:
            checks.append(_check("bookings", "ok", f"{len(stays)} rezervasyon ({len(bookings) - len(stays)} iptal/no-show); son {str(last_booking)[:10]}"))

        worst = "error" if any(c["level"] == "error" for c in checks) else "warn" if any(c["level"] == "warn" for c in checks) else "ok"
        rows.append({
            "agency_id": agency_id, "agency_name": agency.get("name") or contract.get("agency_name"), "status": worst,
            "contract": {"code": contract.get("contract_code"), "status": status, "valid_from": contract.get("valid_from"),
                         "valid_to": contract.get("valid_to"), "payment_terms": contract.get("payment_terms")},
            "credit": usage, "search_reasons": dict(reasons), "searches_total": len(searches), "searches_here": len(here),
            "bookings": len(stays), "last_booking": last_booking, "last_login": last_login, "checks": checks,
        })
    order = {"error": 0, "warn": 1, "ok": 2}
    return sorted(rows, key=lambda row: (order[row["status"]], str(row["agency_name"])))


async def sellable_nights(tenant_id: str, agency_id: str, start: date, days: int) -> list[dict]:
    """Each night: can the agency sell one night here? Same engine as search."""
    from core.agency_hotel_directory import hotel_profiles
    from core.database import db
    from core.sellable_rooms import PHYSICAL_ROOM_FILTER
    from routers.agency_contracts import list_active_contracts
    from routers.marketplace_b2b import (
        _agency_rate_plans,
        _marketplace_occupancy_price,
        _marketplace_stay_price,
        _occupied_room_count,
        _room_type_offered,
        best_outcome,
        pricing_rejection_category,
    )

    sysdb = get_system_db()
    profiles = await hotel_profiles(sysdb, [tenant_id])
    listing = profiles[0] if profiles else {}
    with tenant_context(tenant_id):
        rooms = await db.rooms.find({"tenant_id": tenant_id, **PHYSICAL_ROOM_FILTER}, {"_id": 0}).to_list(500)
    nights = []
    for offset in range(days):
        night = start + timedelta(days=offset)
        check_in, check_out = night.isoformat(), (night + timedelta(days=1)).isoformat()
        contract = (await list_active_contracts(agency_id, on_date=check_in, through_date=check_in)).get(tenant_id)
        if not contract:
            nights.append({"date": check_in, "status": "no_contract"})
            continue
        if check_in in (listing.get("blocked_dates") or []):
            nights.append({"date": check_in, "status": "closed"})
            continue
        by_type: dict[str, list] = {}
        for room in rooms:
            if room.get("is_active") is False or room.get("status") in {"maintenance", "out_of_order", "blocked"}:
                continue
            room_type = room.get("room_type", "Standard")
            # Same capacity filter as the search, for the probe's 2 adults.
            if int(room.get("capacity", 2) or 0) < PROBE_ADULTS:
                continue
            if _room_type_offered(room_type, listing, contract):
                by_type.setdefault(room_type, []).append(room)
        categories, offers = [], []
        with tenant_context(tenant_id):
            for room_type, typed in by_type.items():
                plans = await _agency_rate_plans(tenant_id, agency_id, room_type, check_in, check_out,
                                                 allow_base_rate_fallback=bool(contract.get("allow_base_rate_fallback")), contract=contract)
                if not plans:
                    categories.append("no_rate")
                for plan in plans:
                    pricing = await _marketplace_stay_price(
                        tenant_id=tenant_id, agency_id=agency_id, room_type=room_type, check_in=check_in, check_out=check_out,
                        fallback_rate=float(typed[0].get("base_price") or 0), rate_plan_code=plan,
                        allow_base_rate_fallback=bool(contract.get("allow_base_rate_fallback")), contract=contract)
                    # The search's own occupancy validation (2 adults, the
                    # readiness probe): a product it refuses is not sellable.
                    pricing = await _marketplace_occupancy_price(tenant_id=tenant_id, room=typed[0], pricing=pricing, adults=PROBE_ADULTS, child_ages=[])
                    free = len(typed) - await _occupied_room_count(tenant_id, [r.get("id") for r in typed], check_in, check_out)
                    if pricing.get("shared_availability") is not None:
                        free = min(free, pricing["shared_availability"])
                    category = pricing_rejection_category(pricing, free)
                    categories.append(category)
                    if category == "ok":
                        offers.append({"room_type": room_type, "rate_plan_code": plan, "price": pricing.get("total_price"), "available": free})
        status = best_outcome(categories) if by_type else "no_room"
        nights.append({"date": check_in, "status": status, "offers": offers})
    return nights


@hotel_router.get("")
async def hotel_agency_readiness(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    today = datetime.now(UTC).date()
    return {"as_of": today.isoformat(), "search_window_days": SEARCH_WINDOW_DAYS, "reasons": {k: v[0] for k, v in REASONS.items()},
            "agencies": await agency_readiness(get_system_db(), tenant_id, today)}


@hotel_router.get("/{agency_id}/nights")
async def hotel_agency_nights(agency_id: str, days: int = Query(30, ge=1, le=31), current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    contract = await get_system_db().agency_contracts.find_one({"tenant_id": tenant_id, "agency_id": agency_id, "contract_code": {"$type": "string"}})
    if not contract:
        raise HTTPException(404, "Bu acenteyle sözleşme bulunamadı")
    start = datetime.now(UTC).date()
    nights = await sellable_nights(tenant_id, agency_id, start, days)
    counts = Counter(night["status"] for night in nights)
    return {"start": start.isoformat(), "days": days, "nights": nights, "counts": dict(counts),
            "reasons": {k: v[0] for k, v in REASONS.items()},
            "actions": {k: {"label": v[1], "path": v[2]} for k, v in REASONS.items() if v[1]}}
