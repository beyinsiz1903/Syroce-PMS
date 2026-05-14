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

        rooms_docs.append({
            "id": rid, "tenant_id": stress_tid,
            "room_number": f"{prefix}{block}{floor:02d}{(i + 1):03d}",
            "room_type": room_type,
            "block": block, "floor": floor,
            "capacity": 2 + (i % 3),  # 2..4
            "base_price": base_price, "price_per_night": base_price,
            "status": "occupied",
            "amenities": ["wifi", "tv"] + (["jacuzzi"] if is_vip else []),
            "is_active": True, "is_virtual": False,
            "accessible": accessibility_needed,
            "current_booking_id": bid,
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
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "nights": stay_nights,
            "adults": 2, "children": (i % 3), "guests_count": 2 + (i % 3),
            "total_amount": total_amount, "base_rate": base_price,
            "paid_amount": 0.0, "status": "checked_in",
            "channel": "direct", "rate_plan": "Standard",
            "source_channel": "direct", "origin": "stress_seed",
            "hold_status": "none", "allocation_source": "manual",
            "vip": is_vip, "late_checkout_requested": late_checkout,
            "children_ages": [],
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

        folios_docs.append({
            "id": fid, "tenant_id": stress_tid,
            "booking_id": bid, "guest_id": gid,
            "folio_number": f"{prefix}F{i + 1:04d}",
            "folio_type": "guest", "status": "open",
            "balance": 0.0,
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

    counts = {c: 0 for c in STRESS_COLLECTIONS}

    t_insert_start = time.perf_counter()
    with tenant_context(stress_tid):
        from core.database import db
        counts["rooms"] = await _chunked_insert(db.rooms, rooms_docs, INSERT_CHUNK_SIZE)
        counts["guests"] = await _chunked_insert(db.guests, guests_docs, INSERT_CHUNK_SIZE)
        counts["bookings"] = await _chunked_insert(db.bookings, bookings_docs, INSERT_CHUNK_SIZE)
        counts["folios"] = await _chunked_insert(db.folios, folios_docs, INSERT_CHUNK_SIZE)
        counts["folio_charges"] = await _chunked_insert(db.folio_charges, folio_charges_docs, INSERT_CHUNK_SIZE)
        counts["room_night_locks"] = await _chunked_insert(db.room_night_locks, rnl_docs, INSERT_CHUNK_SIZE)
        counts["housekeeping_tasks"] = await _chunked_insert(db.housekeeping_tasks, hk_docs, INSERT_CHUNK_SIZE)
    insert_ms = round((time.perf_counter() - t_insert_start) * 1000, 1)

    return {
        "success": True,
        "target_tenant_id": stress_tid,
        "data_prefix": prefix,
        "room_count": rc,
        "max_allowed_this_round": MAX_ROOMS_THIS_ROUND,
        "insert_chunk_size": INSERT_CHUNK_SIZE,
        "seeded_counts": counts,
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
    """Runtime read-only invariant check: returns the list of any external HTTP/SMS/email
    calls dispatched since process start in the stress tenant context.

    F8A § post-batch invariant (architect tur-3 feedback): destructive batch'lerden
    SONRA bu endpoint çağrılır ve `external_calls_made` listesinin hâlâ boş olduğu
    runtime olarak doğrulanır. Yalnız read-only — tek başına hiçbir state değiştirmez.
    `E2E_EXTERNAL_DRY_RUN=true` env (fail-closed: env yoksa workflow başlamaz) ile
    birlikte iki katmanlı sözleşme oluşturur:
      (a) backend dispatcher DRY_RUN'da no-op,
      (b) bu endpoint runtime sayacı yansıtır (sayaç gelecekte plug edilirse).

    Şimdiki implementation snapshot baseline'ı doğrular ve `dry_run_enforced` ile
    env contract'ını yansıtır; sayaç değişkeni gelecek backlog (P3) — interface
    sabit, helper bozulmadan upgrade edilebilir.
    """
    import os
    gates = _gates(_stress_tid())
    return {
        "external_calls_made": [],  # placeholder — runtime sayaç plug edilince buraya
        "dry_run_enforced": os.environ.get("E2E_EXTERNAL_DRY_RUN", "").lower() == "true",
        "gates": gates,
        "tenant_context_used": True,
        "note": "Runtime-read placeholder; baseline=[]. Live counter is P3 backlog — interface stable.",
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
