"""
Stress Tenant Seed/Cleanup endpoints — F5

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

This round (F5) caps room_count at 25; the 500-room run lives in F6.

References:
  docs/E2E_STRESS_TENANT_SETUP_PLAN.md
  docs/drill_reports/20260513_stress_tenant_f1_f3_setup.md
  docs/drill_reports/20260513_stress_f4_tenant_leak_audit.md
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

MAX_ROOMS_THIS_ROUND = 25
DEFAULT_ROOMS = 10

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


@router.post("/admin/stress/seed", tags=["Stress E2E"])
async def stress_seed(
    payload: StressSeedRequest,
    current_user: User = Depends(require_super_admin),
):
    """Seed an isolated stress tenant with a small smoke dataset.
    All rows tagged `stress_seed=true` and `stress_prefix=<prefix>`."""
    gates = _gates(payload.target_tenant_id)
    stress_tid = _stress_tid()

    rc = payload.room_count
    prefix = payload.data_prefix or f"E2E_STRESS_{int(time.time())}_"
    now = datetime.now(UTC)
    today_iso = now.date().isoformat()
    day_after_iso = (now + timedelta(days=2)).date().isoformat()

    counts = {c: 0 for c in STRESS_COLLECTIONS}

    rooms_docs, guests_docs, bookings_docs = [], [], []
    folios_docs, folio_charges_docs = [], []
    rnl_docs, hk_docs = [], []

    for i in range(rc):
        rid = str(uuid.uuid4())
        gid = str(uuid.uuid4())
        bid = str(uuid.uuid4())
        fid = str(uuid.uuid4())

        rooms_docs.append({
            "id": rid, "tenant_id": stress_tid,
            "room_number": f"{prefix}R{i+1:04d}",
            "room_type": "standard", "floor": (i % 5) + 1,
            "capacity": 2, "base_price": 1000.0, "price_per_night": 1000.0,
            "status": "occupied", "amenities": [],
            "is_active": True, "is_virtual": False,
            "current_booking_id": bid,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })
        guests_docs.append({
            "id": gid, "tenant_id": stress_tid,
            "name": f"{prefix}Guest_{i+1:04d}",
            "email": f"{prefix.lower()}g{i+1}@e2e-stress.example.com",
            "phone": f"+90555{i+1:07d}",
            "id_number": f"E2E{i+1:08d}",
            "vip_status": False, "loyalty_points": 0,
            "total_stays": 0, "total_spend": 0.0,
            "blacklisted": False,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })
        bookings_docs.append({
            "id": bid, "tenant_id": stress_tid,
            "guest_id": gid, "room_id": rid,
            "check_in": today_iso, "check_out": day_after_iso,
            "adults": 2, "children": 0, "guests_count": 2,
            "total_amount": 2000.0, "base_rate": 1000.0,
            "paid_amount": 0.0, "status": "checked_in",
            "channel": "direct", "rate_plan": "Standard",
            "source_channel": "direct", "origin": "stress_seed",
            "hold_status": "none", "allocation_source": "manual",
            "children_ages": [],
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })
        folios_docs.append({
            "id": fid, "tenant_id": stress_tid,
            "booking_id": bid, "guest_id": gid,
            "folio_number": f"{prefix}F{i+1:04d}",
            "folio_type": "guest", "status": "open",
            "balance": 0.0,
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })
        for j in range(2):
            folio_charges_docs.append({
                "id": str(uuid.uuid4()), "tenant_id": stress_tid,
                "folio_id": fid, "booking_id": bid,
                "charge_category": "room",
                "description": f"{prefix}Charge_{i+1}_{j+1}",
                "unit_price": 500.0, "quantity": 1.0,
                "amount": 500.0, "subtotal": 500.0,
                "discount_amount": 0.0, "vat_rate": 0.0,
                "vat_amount": 0.0, "tax_amount": 0.0,
                "total": 500.0, "voided": False,
                "date": now,
                "stress_seed": True, "stress_prefix": prefix,
            })
        rnl_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "room_id": rid, "booking_id": bid,
            "stay_date": today_iso, "lock_type": "occupied",
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })
        hk_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "room_id": rid, "task_type": "cleaning",
            "status": "pending", "priority": "normal",
            "created_at": now,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # All inserts inside tenant_context — proxy double-enforces tenant_id
    with tenant_context(stress_tid):
        from core.database import db
        if rooms_docs:
            await db.rooms.insert_many(rooms_docs); counts["rooms"] = len(rooms_docs)
        if guests_docs:
            await db.guests.insert_many(guests_docs); counts["guests"] = len(guests_docs)
        if bookings_docs:
            await db.bookings.insert_many(bookings_docs); counts["bookings"] = len(bookings_docs)
        if folios_docs:
            await db.folios.insert_many(folios_docs); counts["folios"] = len(folios_docs)
        if folio_charges_docs:
            await db.folio_charges.insert_many(folio_charges_docs); counts["folio_charges"] = len(folio_charges_docs)
        if rnl_docs:
            await db.room_night_locks.insert_many(rnl_docs); counts["room_night_locks"] = len(rnl_docs)
        if hk_docs:
            await db.housekeeping_tasks.insert_many(hk_docs); counts["housekeeping_tasks"] = len(hk_docs)

    return {
        "success": True,
        "target_tenant_id": stress_tid,
        "data_prefix": prefix,
        "room_count": rc,
        "max_allowed_this_round": MAX_ROOMS_THIS_ROUND,
        "seeded_counts": counts,
        "gates": gates,
        "external_calls_made": [],
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
    with tenant_context(stress_tid):
        from core.database import db
        for col_name in STRESS_COLLECTIONS:
            col = getattr(db, col_name)
            res = await col.delete_many(flt)
            deleted_counts[col_name] = res.deleted_count

    return {
        "success": True,
        "target_tenant_id": stress_tid,
        "data_prefix": payload.data_prefix,
        "deleted_counts": deleted_counts,
        "audit_logs_retained": True,
        "gates": gates,
        "full_wipe": payload.confirm_full_wipe and not payload.data_prefix,
        "idempotent": True,
        "tenant_context_used": True,
    }
