"""
Stress Tenant Seed/Cleanup endpoints — F5 + F6

Pre-flight tooling for the 500-room operational stress E2E suite.
This module deliberately constrains itself with multiple fail-closed
gates so the endpoints can never act on the pilot/production tenant.

Hard rules (enforced by `_gates`):
- super_admin role required
- env `E2E_STRESS_TENANT_ID` must be configured
- request `target_tenant_id` must equal `E2E_STRESS_TENANT_ID`
- env `PILOT_TENANT_ID` (if set) is explicitly blocked
- env `E2E_ALLOW_DESTRUCTIVE_STRESS` must be "true"
- all DB ops execute inside `tenant_context(stress_tid)` so the
  TenantAwareDBProxy auto-enforces isolation even without
  STRICT_TENANT_MODE
- NO external service calls (payment, OTA, SMS, email, KVKK)
- audit_logs are NEVER deleted by cleanup

F5 (10-25 oda smoke):  PASS — pilot mutation = 0
F6 (25→100→250→500):   capacity bump + chunked batch insert + variety
                       (20 room_types × 10 floors × 5 blocks, VIP/late
                       checkout/allergy/accessibility flags, 1-4 night
                       stays → multi-night RNLs).

References:
  docs/E2E_STRESS_TENANT_SETUP_PLAN.md
  docs/drill_reports/20260513_stress_tenant_f1_f3_setup.md
  docs/drill_reports/20260513_stress_f4_tenant_leak_audit.md
  docs/drill_reports/20260513_stress_f5_seed_cleanup_smoke.md
"""
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.helpers import require_super_admin_guard
from core.tenant_db import tenant_context
from models.schemas import User

router = APIRouter(prefix="/api", tags=["Stress E2E"])
require_super_admin = require_super_admin_guard()

# F6: 500 oda kapasitesi. Basamaklı çıkış 25 → 100 → 250 → 500.
MAX_ROOMS_THIS_ROUND = 500
DEFAULT_ROOMS = 10
# Chunked insert_many — Atlas + motor: ~100 doc / batch optimum (memory
# vs round-trip dengesi). Batch boyutu çok büyürse Atlas tarafında
# `BSONObjTooLarge` riski; çok küçükse round-trip overhead artar.
INSERT_CHUNK_SIZE = 100

# 20 oda tipi × 10 kat × 5 blok variety axis'leri
ROOM_TYPES = [
    "standard", "deluxe", "junior_suite", "executive_suite",
    "presidential_suite", "family_room", "twin", "double",
    "single", "triple", "quad", "studio",
    "duplex", "loft", "penthouse", "garden_view",
    "sea_view", "mountain_view", "city_view", "accessible",
]
BLOCKS = ["A", "B", "C", "D", "E"]
FLOORS = list(range(1, 11))  # 1..10

# Order matters for cleanup (children before parents). Tagged rows only.
STRESS_COLLECTIONS = [
    "folio_charges",
    "payments",
    "folios",
    "room_night_locks",
    "housekeeping_tasks",
    "bookings",
    "guests",
    "rooms",
]


def _stress_tid() -> str:
    tid = os.environ.get("E2E_STRESS_TENANT_ID", "").strip()
    if not tid:
        raise HTTPException(
            status_code=412,
            detail="E2E_STRESS_TENANT_ID env var not configured",
        )
    return tid


def _gates(target_tenant_id: str) -> dict[str, Any]:
    """Fail-closed gate stack. Returns gate-report dict on success;
    raises HTTPException on any failure."""
    gates: dict[str, Any] = {}

    stress_tid = _stress_tid()
    gates["env_stress_tid_present"] = True

    if target_tenant_id != stress_tid:
        raise HTTPException(
            status_code=403,
            detail=(
                f"target_tenant_id does not match E2E_STRESS_TENANT_ID. "
                f"Stress endpoints refuse to act on any other tenant."
            ),
        )
    gates["target_matches_stress_tid"] = True

    pilot_tid = os.environ.get("PILOT_TENANT_ID", "").strip()
    if pilot_tid and target_tenant_id == pilot_tid:
        raise HTTPException(
            status_code=403,
            detail="Pilot tenant_id explicitly blocked from stress endpoints",
        )
    gates["pilot_tid_not_targeted"] = True

    if os.environ.get("E2E_ALLOW_DESTRUCTIVE_STRESS", "false").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail=(
                "E2E_ALLOW_DESTRUCTIVE_STRESS != 'true' (fail-closed). "
                "Set this env var to enable stress seed/cleanup."
            ),
        )
    gates["destructive_stress_allowed"] = True

    gates["external_dry_run"] = (
        os.environ.get("E2E_EXTERNAL_DRY_RUN", "false").lower() == "true"
    )

    return gates


class StressSeedRequest(BaseModel):
    target_tenant_id: str
    room_count: int = Field(default=DEFAULT_ROOMS, ge=1, le=MAX_ROOMS_THIS_ROUND)
    data_prefix: str | None = None


class StressCleanupRequest(BaseModel):
    target_tenant_id: str
    data_prefix: str | None = None
    # Defense-in-depth: by default cleanup MUST be prefix-scoped so it
    # can only nuke a single round's data. To wipe ALL stress-seeded rows
    # for the tenant (across rounds), caller must explicitly pass
    # `confirm_full_wipe=True` AND omit `data_prefix`. Fail-closed.
    confirm_full_wipe: bool = False


def _build_factory_docs(rc: int, stress_tid: str, prefix: str, now: datetime):
    """Pure factory: synthesises every document tuple for a round.
    Variety axes (F6):
      - room_type: 20 cycles
      - block: 5 cycles
      - floor: 10 cycles
      - VIP every 7th, late_checkout every 11th, allergy every 13th,
        accessibility every 17th
      - stay_length: 1..4 nights → matching RNL fan-out
    Returns (rooms, guests, bookings, folios, charges, rnls, hk_tasks).
    """
    rooms_docs, guests_docs, bookings_docs = [], [], []
    folios_docs, folio_charges_docs = [], []
    rnl_docs, hk_docs = [], []

    for i in range(rc):
        rid = str(uuid.uuid4())
        gid = str(uuid.uuid4())
        bid = str(uuid.uuid4())
        fid = str(uuid.uuid4())

        room_type = ROOM_TYPES[i % len(ROOM_TYPES)]
        block = BLOCKS[i % len(BLOCKS)]
        floor = FLOORS[i % len(FLOORS)]
        stay_nights = (i % 4) + 1  # 1..4 nights
        is_vip = (i % 7 == 0)
        late_checkout = (i % 11 == 0)
        has_allergy = (i % 13 == 0)
        accessibility_needed = (i % 17 == 0) or (room_type == "accessible")

        check_in = now.date()
        check_out = (now + timedelta(days=stay_nights)).date()

        # Pricing varies a bit so analytics surface non-trivial distributions
        base_price = 800.0 + (i % 20) * 50.0  # 800..1750
        total_amount = base_price * stay_nights

        # Architect tur-6 (round 2) fix: 03-room-move setup'ının vacant pool
        # garantilemek için 30+ force-checkout yapması 108s sandbox timeout'unu
        # aşıyordu. Her 8. booking'i (i % 8 == 0 → ~62 oda) baştan checked_out
        # + room vacant olarak seed et → setup loop'u zaten yeterli eligible
        # görür ve hiç force-checkout etmez (instant PASS).
        pre_vacant = (i % 8 == 0)
        room_status = "available" if pre_vacant else "occupied"
        room_current_bid = None if pre_vacant else bid
        booking_status = "checked_out" if pre_vacant else "checked_in"

        rooms_docs.append({
            "id": rid, "tenant_id": stress_tid,
            "room_number": f"{prefix}{block}{floor:02d}{(i + 1):03d}",
            "room_type": room_type,
            "block": block, "floor": floor,
            "capacity": 2 + (i % 3),  # 2..4
            "base_price": base_price, "price_per_night": base_price,
            "status": room_status,
            "amenities": ["wifi", "tv"] + (["jacuzzi"] if is_vip else []),
            "is_active": True, "is_virtual": False,
            "accessible": accessibility_needed,
            "current_booking_id": room_current_bid,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        guest_flags = []
        if has_allergy: guest_flags.append("allergy")
        if accessibility_needed: guest_flags.append("accessibility")

        guests_docs.append({
            "id": gid, "tenant_id": stress_tid,
            "name": f"{prefix}Guest_{i + 1:04d}",
            "email": f"{prefix.lower()}g{i + 1}@e2e-stress.example.com",
            "phone": f"+90555{i + 1:07d}",
            "id_number": f"E2E{i + 1:08d}",
            "vip_status": is_vip, "loyalty_points": 100 if is_vip else 0,
            "total_stays": (i % 5), "total_spend": float((i % 5) * 1500),
            "blacklisted": False,
            "preferences": {
                "late_checkout": late_checkout,
                "allergy_notes": "nuts" if has_allergy else None,
                "accessibility_needs": accessibility_needed,
                "flags": guest_flags,
            },
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        bookings_docs.append({
            "id": bid, "tenant_id": stress_tid,
            "guest_id": gid, "room_id": rid,
            # F8A #163 fix (run #20 NO-GO): 03-room-move setup'ı bookings.room_type
            # üzerinden _computeDemand çağırıyor; seed bookings'inde alan yoktu →
            # tüm demand `__unknown__` bucket'ına düşüyor, rooms gerçek tipte
            # gruplanıyor → eligible=0 (target_total=50 required_min=30). Booking
            # listesi enrichment'i (pms_bookings.py:440-441) yalnız cache-warm
            # branch'inde çalışıyor; fallback path room_type doldurmuyor. Seed'de
            # direkt yazmak deterministik fix.
            "room_type": room_type,
            # F8A #161: bookings list responses must carry folio_id so stress
            # specs that fall back through `/api/pms/bookings` can target the
            # real folio. Without this, tests sent `folio_id=booking.id` and
            # FolioHardeningService.post_charge returned `{success:false,
            # error:"Folio not found"}` → 100% s400 (drill_reports/20260514_*).
            "folio_id": fid,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "nights": stay_nights,
            "adults": 2, "children": (i % 3), "guests_count": 2 + (i % 3),
            "total_amount": total_amount, "base_rate": base_price,
            "paid_amount": 0.0, "status": booking_status,
            "channel": "direct", "rate_plan": "Standard",
            "source_channel": "direct", "origin": "stress_seed",
            "hold_status": "none", "allocation_source": "manual",
            "vip": is_vip, "late_checkout_requested": late_checkout,
            "children_ages": [],
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        # Architect tur-6 (round 2) fix: 04-folio-mass C2 (sum(charges)==total)
        # reconciliation testi `folio.total`'ı 0 olarak okuyup mismatch raporluyordu.
        # Seed'de gerçek charges toplamını folio'ya da yaz (room*nights + tax*nights).
        folio_total = (base_price * stay_nights) + (7.50 * stay_nights)
        folios_docs.append({
            "id": fid, "tenant_id": stress_tid,
            "booking_id": bid, "guest_id": gid,
            "folio_number": f"{prefix}F{i + 1:04d}",
            "folio_type": "guest",
            "status": "open",
            "balance": folio_total,
            "total": folio_total,
            "total_amount": folio_total,
            "balance_total": folio_total,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        # 2+ charges per folio: room (per-night) + service tax
        for night in range(stay_nights):
            folio_charges_docs.append({
                "id": str(uuid.uuid4()), "tenant_id": stress_tid,
                "folio_id": fid, "booking_id": bid,
                "charge_category": "room",
                "description": f"{prefix}Room_{i + 1}_Night{night + 1}",
                "unit_price": base_price, "quantity": 1.0,
                "amount": base_price, "subtotal": base_price,
                "discount_amount": 0.0, "vat_rate": 0.0,
                "vat_amount": 0.0, "tax_amount": 0.0,
                "total": base_price, "voided": False,
                "date": now,
                "stress_seed": True, "stress_prefix": prefix,
            })
        # service tax (always at least one extra → ≥2 charges per folio)
        folio_charges_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "folio_id": fid, "booking_id": bid,
            "charge_category": "tax",
            "description": f"{prefix}AccTax_{i + 1}",
            "unit_price": 7.50, "quantity": float(stay_nights),
            "amount": 7.50 * stay_nights, "subtotal": 7.50 * stay_nights,
            "discount_amount": 0.0, "vat_rate": 0.0,
            "vat_amount": 0.0, "tax_amount": 7.50 * stay_nights,
            "total": 7.50 * stay_nights, "voided": False,
            "date": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        # RNL fan-out per stay night.
        # Atlas index: ux_room_night UNIQUE on (tenant_id, room_id, night_date).
        # Secondary index idx_rnl_tenant_date_room reads `date`. Set both.
        for night in range(stay_nights):
            night_date = (now + timedelta(days=night)).date().isoformat()
            rnl_docs.append({
                "id": str(uuid.uuid4()), "tenant_id": stress_tid,
                "room_id": rid, "booking_id": bid,
                "night_date": night_date,
                "date": night_date,
                "stay_date": night_date,  # legacy field for any reader
                "lock_type": "occupied",
                "created_at": now,
                "stress_seed": True, "stress_prefix": prefix,
            })

        hk_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "room_id": rid, "task_type": "cleaning",
            "status": "pending",
            "priority": "high" if is_vip else "normal",
            "accessibility_required": accessibility_needed,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # F8A tur-10 fix (run #22 NO-GO): 03-room-move setup eligible<30 root cause
    # iki katmanlı: (1) fetchAllByPrefix offset bug → rooms snapshot ilk 200'e
    # sınırlı (helper'da düzeltildi), (2) snapshot tam 500 olsa bile demand
    # profili (ilk 50 checked_in booking, ROOM_TYPES[i%20] dağılımı) ile vacant
    # supply (i%8==0 → ~62 pre_vacant, ROOM_TYPES'a uniform serpilmiş) tam
    # eşleşmeyebilir → eligible target_total'ın altına düşer. Deterministik fix:
    # her ROOM_TYPE için 3 ek vacant target oda yarat (3 × 20 = 60 ek). Bu havuz:
    #   - status="available", booking yok (saf vacant)
    #   - room_move_target=True işareti (cleanup ve raporlama için)
    #   - stress_seed=True + stress_prefix=<prefix> → cleanup pass'i tarafından
    #     prefix-scoped silinir (ekstra cleanup kodu gerekmez)
    # Sonuç: A testinin demand profili max 50 olduğu için (POSITIVE_MOVE_N=50),
    # her tipte en az 3 ekstra hedef garantili → eligible ≥ min(demand, supply)
    # toplamı ≥ 50 (her tip için demand ≤ 3 supply ≥ 3 ya da fazla).
    EXTRA_VACANT_PER_TYPE = 3
    base_rooms_count = len(rooms_docs)
    for type_idx, rtype in enumerate(ROOM_TYPES):
        for k in range(EXTRA_VACANT_PER_TYPE):
            extra_rid = str(uuid.uuid4())
            extra_idx = base_rooms_count + type_idx * EXTRA_VACANT_PER_TYPE + k
            block = BLOCKS[extra_idx % len(BLOCKS)]
            floor = FLOORS[extra_idx % len(FLOORS)]
            rooms_docs.append({
                "id": extra_rid, "tenant_id": stress_tid,
                "room_number": f"{prefix}MV{block}{floor:02d}{(extra_idx + 1):03d}",
                "room_type": rtype,
                "block": block, "floor": floor,
                "capacity": 2,
                "base_price": 900.0, "price_per_night": 900.0,
                "status": "available",
                "amenities": ["wifi", "tv"],
                "is_active": True, "is_virtual": False,
                "accessible": (rtype == "accessible"),
                "current_booking_id": None,
                "created_at": now,
                "stress_seed": True, "stress_prefix": prefix,
                # Marker: explicit vacant target for room-move setup (Kapsam B).
                "room_move_target": True,
            })

    return (rooms_docs, guests_docs, bookings_docs,
            folios_docs, folio_charges_docs, rnl_docs, hk_docs)


async def _chunked_insert(collection, docs: list[dict], chunk_size: int) -> int:
    """Insert docs in chunks of `chunk_size`. Returns total insert count."""
    if not docs:
        return 0
    total = 0
    for start in range(0, len(docs), chunk_size):
        batch = docs[start:start + chunk_size]
        await collection.insert_many(batch, ordered=False)
        total += len(batch)
    return total


@router.post("/admin/stress/seed", tags=["Stress E2E"])
async def stress_seed(
    payload: StressSeedRequest,
    current_user: User = Depends(require_super_admin),
):
    """Seed an isolated stress tenant with a parameterised dataset.
    All rows tagged `stress_seed=true` and `stress_prefix=<prefix>`.
    Chunked insert_many keeps memory + Atlas wire frame bounded."""
    gates = _gates(payload.target_tenant_id)
    stress_tid = _stress_tid()

    rc = payload.room_count
    prefix = payload.data_prefix or f"E2E_STRESS_{int(time.time())}_"
    now = datetime.now(UTC)

    t_factory_start = time.perf_counter()
    (rooms_docs, guests_docs, bookings_docs,
     folios_docs, folio_charges_docs, rnl_docs, hk_docs) = _build_factory_docs(
        rc, stress_tid, prefix, now,
    )
    factory_ms = round((time.perf_counter() - t_factory_start) * 1000, 1)

    counts = dict.fromkeys(STRESS_COLLECTIONS, 0)

    # F8A tur-11 (CI run #24 NO-GO follow-up): contract split BEFORE insert so
    # `counts["rooms"]` reports BASE rooms (500), with extras tracked separately.
    # Previous tur-10b shape put TOTAL (560) in counts["rooms"] → bulk-seed-500 spec
    # assertion `expect(c.rooms).toBe(500)` failed. User-mandated contract:
    #   seeded_counts.rooms = base (500)
    #   seeded_counts.extra_room_move_targets = extras (60)
    #   seeded_counts.total_rooms = base + extras (560)
    extras_count = sum(1 for r in rooms_docs if r.get("room_move_target") is True)
    base_count = len(rooms_docs) - extras_count

    t_insert_start = time.perf_counter()
    with tenant_context(stress_tid):
        from core.database import db
        total_rooms_inserted = await _chunked_insert(db.rooms, rooms_docs, INSERT_CHUNK_SIZE)
        # Authoritative split — `counts["rooms"]` MUST equal base (500) for
        # tenant-isolation contract testing; extras are an internal stress-only
        # pool that doesn't represent real PMS inventory.
        counts["rooms"] = base_count
        counts["extra_room_move_targets"] = extras_count
        counts["total_rooms"] = total_rooms_inserted
        counts["guests"] = await _chunked_insert(db.guests, guests_docs, INSERT_CHUNK_SIZE)
        counts["bookings"] = await _chunked_insert(db.bookings, bookings_docs, INSERT_CHUNK_SIZE)
        counts["folios"] = await _chunked_insert(db.folios, folios_docs, INSERT_CHUNK_SIZE)
        counts["folio_charges"] = await _chunked_insert(db.folio_charges, folio_charges_docs, INSERT_CHUNK_SIZE)
        counts["room_night_locks"] = await _chunked_insert(db.room_night_locks, rnl_docs, INSERT_CHUNK_SIZE)
        counts["housekeeping_tasks"] = await _chunked_insert(db.housekeeping_tasks, hk_docs, INSERT_CHUNK_SIZE)
    insert_ms = round((time.perf_counter() - t_insert_start) * 1000, 1)

    # Cache bust (architect tur-6 fix): rooms endpoint Redis cache'i seed öncesi
    # döküman setiyle (eski projection, eksik stress_prefix) doluysa fetchAllByPrefix
    # filter'ı 0 döner → room-move setup FAIL. Stress tenant'ın rooms cache'lerini
    # invalidate ederek temiz başla. cache_warmer pre-warm pattern'i de aynı prefix.
    try:
        from redis_cache import redis_cache
        if redis_cache:
            redis_cache.clear_pattern(f"rooms:{stress_tid}:*")
    except Exception:
        pass
    try:
        from cache_warmer import cache_warmer
        if cache_warmer:
            for k in [f"rooms:{stress_tid}", f"bookings:{stress_tid}", f"frontdesk:{stress_tid}"]:
                cache_warmer.cache.pop(k, None)
    except Exception:
        pass

    # F8A tur-11: rooms_breakdown is a denormalized convenience view; same data
    # lives in seeded_counts.{rooms, extra_room_move_targets, total_rooms}.
    # Also expose per-type distribution of extras so 03-room-move spec setup
    # can verify the pool covers demand (room_type-by-room_type).
    extra_per_type: dict = {}
    for r in rooms_docs:
        if r.get("room_move_target") is True:
            t = r.get("room_type") or "__unknown__"
            extra_per_type[t] = extra_per_type.get(t, 0) + 1
    rooms_breakdown = {
        "base_rooms": counts["rooms"],
        "extra_room_move_targets": counts.get("extra_room_move_targets", 0),
        "total_rooms": counts.get("total_rooms", counts["rooms"]),
        "room_move_target_by_type": extra_per_type,
    }

    return {
        "success": True,
        "target_tenant_id": stress_tid,
        "data_prefix": prefix,
        "room_count": rc,
        "max_allowed_this_round": MAX_ROOMS_THIS_ROUND,
        "insert_chunk_size": INSERT_CHUNK_SIZE,
        "seeded_counts": counts,
        "rooms_breakdown": rooms_breakdown,
        "timing_ms": {
            "factory": factory_ms,
            "insert": insert_ms,
            "total": round(factory_ms + insert_ms, 1),
        },
        "variety": {
            "room_types": len(ROOM_TYPES),
            "blocks": len(BLOCKS),
            "floors": len(FLOORS),
            "vip_modulo": 7,
            "late_checkout_modulo": 11,
            "allergy_modulo": 13,
            "accessibility_modulo": 17,
            "stay_nights_cycle": "1..4",
        },
        "gates": gates,
        "external_calls_made": [],
        "tenant_context_used": True,
    }


@router.get("/admin/stress/external-calls", tags=["Stress E2E"])
async def stress_external_calls_status(
    current_user: User = Depends(require_super_admin),
):
    """Runtime read-only invariant check: queries the actual outbox collections
    (`outbox_events` SXI bus + `integration_afsadakat_outbox`) for any rows scoped
    to the stress tenant. Under `E2E_EXTERNAL_DRY_RUN=true`, dispatcher writes
    nothing → an empty list is the expected post-batch invariant.

    F8A § post-batch invariant (architect tur-3/tur-4 feedback): destructive
    batch'lerden SONRA bu endpoint çağrılır; eğer dispatcher DRY_RUN bayrağını
    bypass eder ve outbox'a yazarsa, runtime burada görünür. Tüm match'ler
    identifier+target+status ile döner (payload exclude — log volume kontrolü).

    Two-layer contract:
      (a) `dry_run_enforced`: backend dispatcher env doğrulaması (env yoksa false),
      (b) `external_calls_made`: stress_tid-scoped outbox satırları (gerçek runtime).
    """
    import logging as _logging
    _log = _logging.getLogger("stress.external_calls")
    calls: list[dict] = []
    query_errors: list[str] = []
    stress_tid = ""
    gates: dict[str, Any] = {}

    # Top-level guard (architect tur-6 fix): bu endpoint asla 500 dönmemeli.
    # CI'da gizli traceback'leri yakalamak için her hata `query_errors`'a yazılır
    # ve Sentry'ye logger.exception ile gönderilir. Helper status=200 + boş calls
    # gördüğünde PASS verir; non-empty calls FAIL → gerçek invariant ihlali.
    try:
        from core.database import db
        from core.tenant_db import get_system_db
        sysdb = get_system_db()

        stress_tid = _stress_tid()
        gates = _gates(stress_tid)

        # 1) SXI bus outbox (sysdb-scoped)
        # Architect tur-6 (round 2) fix: outbox `status="pending"` + `attempts=0`
        # satırları normal queue durumudur — checkin/checkout her zaman bir
        # outbox event yazar. "External call MADE" = dispatcher worker'ın
        # gerçekten dispatch denediği row (attempts>0 veya non-pending status).
        # Pending+attempts=0 = sıraya yazıldı ama henüz dispatch edilmedi → DRY_RUN
        # ortamında worker'lar bunları dispatch etmediği için sayılmamalı.
        # F8A run #20 fix: previous filter included `status NOT IN [pending, None]`
        # as an OR branch — but worker'lar event'i noop olarak işaretlerken
        # (no active connectors / dry_run) status="processed" yazıp attempts=0
        # bırakıyor. Bu satırlar GERÇEK external HTTP dispatch DEĞİL, sadece
        # worker bookkeeping. "External call MADE" tanımı: dispatcher gerçekten
        # bir HTTP attempt yaptı → attempts/attempt_count/retry_count > 0.
        # Inert message filter (aşağıda) zaten safety-net; ama bazı worker'lar
        # delivery_message yazmadan status update'liyor → message-only filter
        # yetmiyor. Bu yüzden status branch'ini kaldırıyoruz; attempt counter'lı
        # row'lar zaten "tried to dispatch" semantiğini taşıyor.
        dispatched_filter = {
            "tenant_id": stress_tid,
            "$or": [
                {"attempts": {"$gt": 0}},
                {"attempt_count": {"$gt": 0}},
                {"retry_count": {"$gt": 0}},
            ],
        }
        try:
            cursor = sysdb.outbox_events.find(
                dispatched_filter,
                projection={"_id": 0, "event_type": 1, "target": 1, "status": 1, "created_at": 1, "attempts": 1, "attempt_count": 1, "retry_count": 1, "delivery_message": 1, "last_error": 1},
            ).sort("created_at", -1).limit(50)
            async for doc in cursor:
                # Architect tur-7 fix: outbox worker stress tenant'ında CM connector
                # olmadığı için EventSyncService "No active connectors" döner ve
                # worker event'i status=processed işaretler. Bu inert sonuç GERÇEK
                # external HTTP çağrısı DEĞİL — sadece dispatcher worker'ın boş
                # çalışmasıdır. Aynı şekilde DRY_RUN bayrağıyla short-circuit eden
                # delivery_message'ler de external call sayılmaz.
                msg = (doc.get("delivery_message") or "") + " " + (doc.get("last_error") or "")
                msg_lower = msg.lower()
                inert_patterns = ("no active connectors", "dry_run", "dry run", "unsupported event_type")
                if any(p in msg_lower for p in inert_patterns):
                    continue
                doc["source"] = "outbox_events"
                if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
                    doc["created_at"] = doc["created_at"].isoformat()
                calls.append(doc)
        except Exception as e:  # noqa: BLE001
            _log.exception("outbox_events query failed for stress_tid=%s", stress_tid)
            query_errors.append(f"outbox_events:{type(e).__name__}:{str(e)[:200]}")

        # 2) Afsadakat outbox (tenant-scoped db) — aynı dispatched-only filter.
        # F8A run #20 fix: aynı gerekçe ile status branch kaldırıldı (yukarıdaki
        # outbox_events dispatched_filter yorumuna bkz.).
        afsadakat_filter = {
            "$or": [
                {"attempts": {"$gt": 0}},
                {"attempt_count": {"$gt": 0}},
                {"retry_count": {"$gt": 0}},
            ],
        }
        try:
            with tenant_context(stress_tid):
                cursor = db.integration_afsadakat_outbox.find(
                    afsadakat_filter,
                    projection={"_id": 0, "event_type": 1, "status": 1, "created_at": 1, "attempts": 1, "attempt_count": 1, "retry_count": 1, "delivery_message": 1, "last_error": 1},
                ).sort("created_at", -1).limit(50)
                async for doc in cursor:
                    msg = (doc.get("delivery_message") or "") + " " + (doc.get("last_error") or "")
                    if any(p in msg.lower() for p in ("no active connectors", "dry_run", "dry run", "unsupported event_type")):
                        continue
                    doc["source"] = "integration_afsadakat_outbox"
                    if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
                        doc["created_at"] = doc["created_at"].isoformat()
                    calls.append(doc)
        except Exception as e:  # noqa: BLE001
            _log.exception("afsadakat_outbox query failed for stress_tid=%s", stress_tid)
            query_errors.append(f"afsadakat_outbox:{type(e).__name__}:{str(e)[:200]}")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _log.exception("stress_external_calls_status top-level failure")
        query_errors.append(f"top_level:{type(e).__name__}:{str(e)[:200]}")

    # F8A run #20 NO-GO root-cause #1 fix (tur-8): `dry_run_enforced` was a pure
    # self-report on `E2E_EXTERNAL_DRY_RUN` env. The CI workflow sets that env on
    # the *runner* process (stress.yml:66), but the backend we hit lives on a
    # *separate Replit deployment* (`STRESS_E2E_BASE_URL` secret) whose process
    # env is configured via Replit Secrets — not propagated from the runner. So
    # the flag was ~always false in CI even when no calls were actually made,
    # forcing the helper to FAIL despite an empty outbox.
    #
    # E2E_EXTERNAL_DRY_RUN never actually gated dispatch anywhere in this
    # codebase (rg shows only these two read sites). The *real* protection
    # against dispatch is the stress tenant having NO active CM connectors:
    # EventSyncService returns "No active connectors" → worker noop. That's a
    # structural fact we can read directly from the DB, so we treat it as
    # equivalent to env-enforced dry-run. The empty-outbox invariant
    # (`external_calls_made==[]` + `query_errors==[]`) is the ground truth and
    # remains untouched.
    structural_dry = False
    active_connectors_count = None
    try:
        from core.database import db as _db
        active_connectors_count = await _db.channel_connections.count_documents({
            "tenant_id": stress_tid, "status": "active",
        })
        structural_dry = active_connectors_count == 0
    except Exception as e:  # noqa: BLE001
        _log.exception("active connectors lookup failed for stress_tid=%s", stress_tid)
        query_errors.append(f"active_connectors:{type(e).__name__}:{str(e)[:200]}")

    env_dry = os.environ.get("E2E_EXTERNAL_DRY_RUN", "").lower() == "true"

    return {
        "external_calls_made": calls,  # boş = invariant tutuyor; non-empty = dispatcher bypass
        "external_calls_count": len(calls),
        "dry_run_enforced": env_dry or structural_dry,
        "dry_run_source": (
            "env_and_structural" if env_dry and structural_dry
            else "env" if env_dry
            else "structural_no_active_connectors" if structural_dry
            else "none"
        ),
        "dry_run_env_flag": env_dry,
        "dry_run_structural": structural_dry,
        "active_connectors_count": active_connectors_count,
        "query_errors": query_errors,  # collection erişilemezse REVIEW olarak değerlendir
        "sources_checked": ["outbox_events", "integration_afsadakat_outbox"],
        "gates": gates,
        "tenant_context_used": True,
    }


@router.post("/admin/stress/cleanup", tags=["Stress E2E"])
async def stress_cleanup(
    payload: StressCleanupRequest,
    current_user: User = Depends(require_super_admin),
):
    """Idempotent cleanup of stress-seeded data.
    Filters by `stress_seed=true` (+ optional `stress_prefix`).
    audit_logs are NEVER deleted (KVKK retention)."""
    gates = _gates(payload.target_tenant_id)
    stress_tid = _stress_tid()

    # Prefix-scope gate: require either an explicit prefix OR an explicit
    # full-wipe confirmation. Refuse to do an unbounded delete by accident.
    if not payload.data_prefix and not payload.confirm_full_wipe:
        raise HTTPException(
            status_code=400,
            detail=(
                "cleanup requires either `data_prefix` (recommended, "
                "round-scoped) or `confirm_full_wipe=true` (deletes ALL "
                "stress-seeded rows for the tenant across all rounds)."
            ),
        )

    flt: dict = {"stress_seed": True, "tenant_id": stress_tid}
    if payload.data_prefix:
        flt["stress_prefix"] = payload.data_prefix

    deleted_counts: dict[str, int] = {}
    t_start = time.perf_counter()
    with tenant_context(stress_tid):
        from core.database import db
        for col_name in STRESS_COLLECTIONS:
            col = getattr(db, col_name)
            res = await col.delete_many(flt)
            deleted_counts[col_name] = res.deleted_count
    cleanup_ms = round((time.perf_counter() - t_start) * 1000, 1)

    return {
        "success": True,
        "target_tenant_id": stress_tid,
        "data_prefix": payload.data_prefix,
        "deleted_counts": deleted_counts,
        "audit_logs_retained": True,
        "gates": gates,
        "full_wipe": payload.confirm_full_wipe and not payload.data_prefix,
        "timing_ms": {"cleanup": cleanup_ms},
        "idempotent": True,
        "tenant_context_used": True,
    }
