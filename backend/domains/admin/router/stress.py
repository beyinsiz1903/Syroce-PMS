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
    # F8B (2026-05-17): Guest Experience surface — QR requests, complaints,
    # messaging dry-run buckets, notifications. All rows tagged with the same
    # `stress_seed=True` + `stress_prefix` so the unified cleanup loop already
    # handles them (no extra code needed beyond inclusion here).
    "room_qr_requests",
    "service_complaints",
    "messages",
    "notifications",
    # F8C (2026-05-17): MICE / Event / Banquet / Group Operations surface.
    # `mice_accounts` taşıyıcı: hem client account'ları (event organizatörü)
    # hem `account_type=banquet_competitor` rakipleri tek koleksiyonda; her
    # ikisi `stress_seed=True` etiketli → cleanup ikisini de doğru toplar.
    # `mice_opportunities` aynı şekilde sales_catering opportunity (_kind=
    # opportunity) + sales/router leads (_kind=lead) için ortak; cleanup
    # `stress_seed=True` filter ile her ikisini de tarar.
    "mice_spaces",
    "mice_menus",
    "mice_accounts",
    "mice_contacts",
    "mice_resources",
    "mice_events",
    "mice_opportunities",
    "mice_opportunity_activities",
    "mice_packages",
    # F8D (2026-05-18): HR / Staff / Shift / Leave / Department surface.
    # All rows tagged `stress_seed=True` + `stress_prefix` → unified cleanup
    # loop reaches them with no additional logic. No external service risk:
    # HR notifications are in-app only (`notifications` collection), payroll
    # computation is backend-only (no provider integration). Stress admin
    # is `super_admin` → `require_op` gates pass; module-blocked pattern is
    # the spec-side fallback if any endpoint enforces manual role lists.
    "staff_members",
    "hr_departments",
    "hr_positions",
    "attendance_records",
    "leave_requests",
    "leave_balances",
    "shift_schedules",
    "shift_swap_requests",
    "performance_reviews",
    "payroll_records",
    # F8E (2026-05-18): Finance / Cashier / Accounting surface.
    # All rows tagged `stress_seed=True` + `stress_prefix` → unified cleanup
    # loop reaches them. No external service risk: Iyzico is logic-embedded
    # (not router-tripped), email/SMS not invoked from these endpoints,
    # `E2E_EXTERNAL_DRY_RUN=true` is the global gate. Stress admin is
    # `super_admin` → `require_op("post_payment" | "view_finance_reports" |
    # "manage_city_ledger" | "post_charge")` all pass; module-blocked +
    # RBAC short-circuit is the spec-side fallback (F8C/D mirror).
    # Folio/folio_charges/payments already covered by F8A § 04 — F8E avoids
    # double-seeding those and instead targets cashier_shifts/_transactions,
    # expenses/suppliers/invoices, bank/inventory/stock_movement, city ledger.
    "cashier_shifts",
    "cashier_transactions",
    "expenses",
    "suppliers",
    "accounting_invoices",
    "bank_accounts",
    "inventory_items",
    "stock_movements",
    "cash_flow",
    "city_ledger_accounts",
    "city_ledger_transactions",
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


# F8B (2026-05-17): Guest Experience seed — QR requests, complaints, messages,
# notifications. Kept as a separate factory so the F6 baseline (rooms/bookings/
# folios/RNL/HK) factory stays small and any future Guest Experience drift
# (new category, new severity) lands in one place. Derives entirely from
# rooms/bookings/guests already produced by _build_factory_docs so it never
# re-implements pricing or VIP logic.
#
# Strict invariants:
# - All docs tagged stress_seed=True + stress_prefix=<prefix>
# - Complaints intentionally seeded with guest_id=None so the resolve flow's
#   `_notify_guest_resolved` short-circuits at the "no guest_id" guard. The
#   alternative path would call `core.email.send_email` → Resend HTTP call →
#   external_calls invariant violation (RESEND_API_KEY is set in the stress
#   environment). booking_id is preserved so folio compensation adjustment
#   stays local and exercises real code.
# - Messages are db.messages rows only. The /api/messaging/send-{email,sms,
#   whatsapp} endpoints write to db.messages with status='sent' but do NOT
#   invoke any provider in the current backend, so seed + write tests stay
#   purely local. (The legacy /api/whatsapp/send-confirmation path DOES call
#   whatsapp_service — F8B does not seed/test that path.)
def _build_f8b_docs(
    rooms_docs: list[dict],
    bookings_docs: list[dict],
    guests_docs: list[dict],
    stress_tid: str,
    prefix: str,
    now: datetime,
):
    qr_docs: list[dict] = []
    complaint_docs: list[dict] = []
    message_docs: list[dict] = []
    notif_docs: list[dict] = []

    QR_CATEGORIES = [
        "cleaning", "towels", "amenities", "maintenance", "wifi",
        "food_order", "minibar", "laundry", "transport",
    ]
    QR_PRIORITIES = ["low", "normal", "high", "urgent"]
    DEPT_BY_CAT = {
        "cleaning": "rooms", "towels": "rooms", "amenities": "rooms",
        "maintenance": "technical", "wifi": "technical",
        "food_order": "fnb", "minibar": "minibar",
        "laundry": "laundry", "transport": "transportation",
    }

    bookings_by_room = {b["room_id"]: b for b in bookings_docs}
    guests_by_id = {g["id"]: g for g in guests_docs}
    severities = ["low", "medium", "high", "critical"]
    channels = ["email", "sms", "whatsapp"]

    for i, room in enumerate(rooms_docs):
        # Extras (room_move_target=True) skip Guest Experience seeding — they
        # have no booking/guest, are not part of the real PMS inventory, and
        # would otherwise inflate counts in ways that break drift assertions.
        if room.get("room_move_target") is True:
            continue
        rid = room["id"]
        rnumber = room["room_number"]
        booking = bookings_by_room.get(rid)
        guest = guests_by_id.get(booking["guest_id"]) if booking else None

        # 1) ROOM QR REQUEST — 1 open request per real room.
        # 1/4 of requests aged 25h (overdue for normal/low SLA) so the
        # SLA/overdue dashboard surfaces a non-trivial distribution; rest
        # are fresh (10 min).
        cat = QR_CATEGORIES[i % len(QR_CATEGORIES)]
        prio = QR_PRIORITIES[i % len(QR_PRIORITIES)]
        age_minutes = 25 * 60 if (i % 4 == 0) else 10
        qr_created = now - timedelta(minutes=age_minutes)
        qr_docs.append({
            # router uses `_id` (string uuid) and serializes to `id` on read.
            "_id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "room_id": rid,
            "room_number": rnumber,
            "category": cat,
            "department": DEPT_BY_CAT[cat],
            "title": f"{prefix}QR_{cat}_{i + 1}",
            "description": f"{prefix}QR seed request {i + 1}",
            "priority": prio,
            "status": "new",
            "language": "tr",
            "guest_name": None,
            "guest_phone": None,
            "booking_id": booking["id"] if booking else None,
            "assigned_to": None,
            "created_at": qr_created,
            "updated_at": qr_created,
            "completed_at": None,
            "source": "qr",
            "status_history": [
                {"status": "new", "by": "guest", "at": qr_created, "note": "F8B seed"},
            ],
            "stress_seed": True,
            "stress_prefix": prefix,
        })

        # 2) SERVICE COMPLAINT — 1 per 5 rooms (100 for 500 base rooms).
        # Resolve test targets 30, escalate 10, leaves 60 for summary read.
        if i % 5 == 0:
            sev = severities[(i // 5) % len(severities)]
            age_hours = 30 if (i % 10 == 0) else 1
            c_created = (now - timedelta(hours=age_hours)).isoformat()
            complaint_docs.append({
                "id": str(uuid.uuid4()),
                "tenant_id": stress_tid,
                "source": "staff",
                "category": "service_recovery",
                "severity": sev,
                "subject": f"{prefix}Complaint_{i + 1}",
                "description": f"{prefix}F8B seeded complaint #{i + 1}",
                "guest_name": None,
                "guest_phone": None,
                # CRITICAL — keeps resolve flow's _notify_guest_resolved silent.
                "guest_id": None,
                "room_id": rid,
                "room_number": rnumber,
                "booking_id": booking["id"] if booking else None,
                "assigned_department": "front_office",
                "status": "open",
                "compensation_offered": None,
                "compensation_amount": 0,
                "created_by": None,
                "created_at": c_created,
                "updated_at": c_created,
                "history": [{
                    "action": "created", "actor_id": None,
                    "actor_name": "F8B seed", "at": c_created,
                }],
                "stress_seed": True,
                "stress_prefix": prefix,
            })

        # 3) MESSAGES — 1 inbound + 1 outbound per real room. Provides
        #    read-load surface for /api/messaging/conversations without
        #    invoking any external provider.
        ch = channels[i % len(channels)]
        contact = None
        if guest:
            contact = guest.get("email") if ch == "email" else guest.get("phone")
        if not contact:
            contact = f"{prefix.lower()}m{i}@e2e-stress.example.com"
        sent_at = now.isoformat()
        for direction in ("inbound", "outbound"):
            message_docs.append({
                "id": str(uuid.uuid4()),
                "tenant_id": stress_tid,
                "channel": ch,
                "direction": direction,
                "to": contact if direction == "outbound" else f"{prefix}INBOX",
                "from": f"{prefix}INBOX" if direction == "outbound" else contact,
                "subject": f"{prefix}Subj_{i}_{direction}" if ch == "email" else None,
                "message": f"{prefix} F8B seed {direction} #{i}",
                "booking_id": booking["id"] if booking else None,
                "status": "sent" if direction == "outbound" else "received",
                "sent_at": sent_at,
                "sent_by": None,
                "stress_seed": True,
                "stress_prefix": prefix,
            })

        # 4) NOTIFICATIONS — 1 per real room (broadcast: user_id=None). 1/7
        #    high-priority escalation type so unread-by-priority queries
        #    return a non-trivial distribution.
        is_escalation = (i % 7 == 0)
        notif_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "user_id": None,
            "type": "complaint_escalated" if is_escalation else "guest_request",
            "title": f"{prefix}Notif_{i + 1}",
            "message": f"{prefix} F8B seed notification {i + 1}",
            "priority": "high" if is_escalation else "normal",
            "read": (i % 3 == 0),
            "action_url": f"/room-requests?room={rid}",
            "context": {"room_id": rid, "seed": "f8b"},
            "created_at": sent_at,
            "stress_seed": True,
            "stress_prefix": prefix,
        })

    return qr_docs, complaint_docs, message_docs, notif_docs


# F8C — MICE / Event / Banquet / Group Operations surface factory.
#
# Dry-run safety invariants (must hold to keep external_calls=[] PASS):
#   - mice_events seed-status: ALL "lead". `_post_event_to_folio` runs only
#     when transition target is `completed` AND `reservation_id` is set;
#     F8C events have reservation_id=None so even if a spec accidentally
#     transitions to completed, posting + xchange bus.publish short-circuit
#     in `_post_event_to_folio` (total<=0 or no reservation_id → return).
#     Spec 14 explicitly skips the `completed` transition anyway.
#   - opportunities seed-stage: lead/qualified/proposal/contract — never
#     won/lost so specs can transition forward without colliding with
#     `closed_at` semantics. Pipeline aggregation read returns non-trivial
#     distribution.
#   - sales_leads (mice_opportunities + _kind=lead): all seeded status=new
#     so funnel aggregation surfaces non-trivial; specs transition forward.
#   - Banquet competitors (mice_accounts + account_type=banquet_competitor)
#     pre-seeded with 5 rates each → positioning read returns data.
#   - All collections tagged stress_seed=True + stress_prefix=<prefix> for
#     idempotent cleanup; tenant_context(stress_tid) wrap prevents leak.
#   - Spaces: each event uses a UNIQUE (space_id, date) tuple to avoid
#     conflict on transitions (lead→tentative triggers _check_space_conflict).
def _build_f8c_docs(stress_tid: str, prefix: str, now: datetime):
    spaces_docs: list[dict] = []
    menus_docs: list[dict] = []
    accounts_docs: list[dict] = []
    contacts_docs: list[dict] = []
    resources_docs: list[dict] = []
    events_docs: list[dict] = []
    opportunities_docs: list[dict] = []
    opp_activities_docs: list[dict] = []
    leads_docs: list[dict] = []
    competitors_docs: list[dict] = []
    packages_docs: list[dict] = []

    now_iso = now.isoformat()

    # 1) FUNCTION SPACES (8)
    space_seeds = [
        ("Grand Balo Salonu", "Bodrum kat", 480, 500, 280, 320, 450, 0, 0, 8000, 35000),
        ("Bosphorus Toplantı Salonu", "1. kat", 120, 120, 70, 80, 100, 50, 40, 2500, 12000),
        ("Marmara Boardroom", "1. kat", 35, 0, 0, 0, 0, 0, 14, 1500, 6000),
        ("Teras Etkinlik Alanı", "Çatı", 220, 0, 0, 150, 250, 0, 0, 3500, 18000),
        ("Anadolu Konferans", "2. kat", 200, 220, 120, 0, 180, 80, 0, 3000, 15000),
        ("Lale Düğün Salonu", "Bodrum kat", 300, 0, 0, 220, 350, 0, 0, 6000, 28000),
        ("Çırağan VIP", "3. kat", 60, 0, 30, 0, 60, 28, 20, 2000, 9500),
        ("Galata Atölye", "2. kat", 80, 60, 40, 0, 0, 30, 24, 1800, 8500),
    ]
    space_ids = []
    for i, (n, loc, area, th, cl, bq, ck, us, br, hr, dr) in enumerate(space_seeds):
        sid = str(uuid.uuid4())
        space_ids.append(sid)
        spaces_docs.append({
            "id": sid, "tenant_id": stress_tid,
            "name": f"{prefix}Space_{n}", "location": loc, "area_m2": area,
            "capacity_theatre": th, "capacity_classroom": cl,
            "capacity_banquet": bq, "capacity_cocktail": ck,
            "capacity_u_shape": us, "capacity_boardroom": br,
            "hourly_rate": hr, "daily_rate": dr, "currency": "TRY",
            "amenities": ["wifi", "projector", "ses-sistemi"],
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 2) MENUS (8) — F&B + AV/decor
    menu_seeds = [
        ("Coffee Break Klasik", "fb", 120.0, 0.0),
        ("Coffee Break Premium", "fb", 180.0, 0.0),
        ("Açık Büfe Öğle", "fb", 450.0, 0.0),
        ("Düğün Gala Menüsü", "fb", 1200.0, 0.0),
        ("Set Menü 3 Kap", "fb", 650.0, 0.0),
        ("Projeksiyon + Ses Paketi", "av", 0.0, 4500.0),
        ("Sahne + Işık Tasarım", "av", 0.0, 8500.0),
        ("Çiçek + Masa Dekoru", "decor", 0.0, 5500.0),
    ]
    menu_ids = []
    for i, (n, t, ppp, fp) in enumerate(menu_seeds):
        mid = str(uuid.uuid4())
        menu_ids.append(mid)
        menus_docs.append({
            "id": mid, "tenant_id": stress_tid,
            "name": f"{prefix}Menu_{n}", "type": t,
            "price_per_person": ppp, "flat_price": fp, "currency": "TRY",
            "description": f"{prefix} F8C seed menu",
            "active": True, "courses": [], "allergens": [],
            "dietary_tags": [], "min_guests": 0, "prep_lead_minutes": 60,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 3) ACCOUNTS (10) + CONTACTS (1 per account)
    account_ids = []
    for i in range(10):
        aid = str(uuid.uuid4())
        account_ids.append(aid)
        accounts_docs.append({
            "id": aid, "tenant_id": stress_tid,
            "name": f"{prefix}Account_Kurumsal_{i + 1:02d}",
            # `/api/mice/accounts` filters on account_type=client (or missing).
            # Use "client" to keep seeded rows visible in spec 14-A catalog read.
            "account_type": "client",
            "tax_no": f"{prefix}TAX{i + 1:08d}",
            "email": f"{prefix.lower()}acct{i + 1}@e2e-stress.example.com",
            "phone": f"+90555100{i + 1:04d}",
            "industry": "tourism" if i % 2 == 0 else "finance",
            "notes": f"{prefix} F8C seed account",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })
        cid = str(uuid.uuid4())
        contacts_docs.append({
            "id": cid, "tenant_id": stress_tid, "account_id": aid,
            "name": f"{prefix}Contact_{i + 1}",
            "title": "Etkinlik Yöneticisi",
            "email": f"{prefix.lower()}ctc{i + 1}@e2e-stress.example.com",
            "phone": f"+90555200{i + 1:04d}",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 4) RESOURCES (5) — AV/decor stocked inventory
    for i in range(5):
        rid = str(uuid.uuid4())
        resources_docs.append({
            "id": rid, "tenant_id": stress_tid,
            "name": f"{prefix}Resource_AV_{i + 1}",
            "type": "av", "unit": "unit",
            "unit_price": 1500.0 + (i * 250),
            "total_stock": 10 + (i * 5),
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 5) EVENTS (30) — UNIQUE (space, date) tuples → conflict-free transitions
    # Date offset: starts 30 days from now, each event +1 day later.
    # Each event uses spaces[i % 8] — so events 0,8,16,24 share Grand Balo
    # Salonu but with different dates (i, i+8, i+16, i+24 days apart) →
    # no date overlap on same space.
    event_ids = []
    for i in range(30):
        eid = str(uuid.uuid4())
        event_ids.append(eid)
        start_day = now.date() + timedelta(days=30 + i)
        # Single-day events; starts 10:00, ends 18:00 same day.
        starts_at = datetime(start_day.year, start_day.month, start_day.day, 10, 0, 0, tzinfo=UTC)
        ends_at = datetime(start_day.year, start_day.month, start_day.day, 18, 0, 0, tzinfo=UTC)
        events_docs.append({
            "id": eid, "tenant_id": stress_tid,
            "name": f"{prefix}Event_{i + 1:02d}",
            "client_name": f"{prefix}Client_{i + 1:02d}",
            "client_email": f"{prefix.lower()}ev{i + 1}@e2e-stress.example.com",
            "client_phone": f"+90555300{i + 1:04d}",
            "client_account_id": account_ids[i % len(account_ids)],
            "client_contact_id": None,
            "organizer_user": None,
            "event_type": ["meeting", "conference", "wedding", "gala", "training"][i % 5],
            "status": "lead",  # safe — no folio impact, no conflict checks
            "expected_pax": 50 + (i * 5),
            "start_date": start_day.isoformat(),
            "end_date": start_day.isoformat(),
            "space_bookings": [{
                "space_id": space_ids[i % len(space_ids)],
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "setup_style": "theatre",
                "expected_pax": 50 + (i * 5),
            }],
            "resources": [],
            "agenda": [],
            "payment_schedule": [],
            "notes": f"{prefix} F8C seed event",
            "reservation_id": None,  # CRITICAL — no folio posting on completed
            "lost_reason": None,
            "totals": {"grand_total": 0, "space_total": 0, "resource_total": 0},
            "created_at": now_iso,
            "created_by": "f8c-seed",
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 6) OPPORTUNITIES (30) — _kind=opportunity, stages lead/qualified/proposal/contract.
    # NEVER won/lost — keeps `closed_at` field unset so spec C can transition forward.
    open_stages = ["lead", "qualified", "proposal", "contract"]
    stage_prob = {"lead": 10, "qualified": 25, "proposal": 50, "contract": 80}
    for i in range(30):
        oid = str(uuid.uuid4())
        stage = open_stages[i % len(open_stages)]
        opportunities_docs.append({
            "_kind": "opportunity",
            "id": oid, "tenant_id": stress_tid,
            "title": f"{prefix}Opp_{i + 1:02d}",
            "account_id": account_ids[i % len(account_ids)],
            "contact_id": None,
            "event_type": ["wedding", "conference", "corporate", "social", "incentive"][i % 5],
            "pax": 80 + (i * 5),
            "estimated_value": 25000.0 + (i * 1500),
            "currency": "TRY",
            "probability": stage_prob[stage],
            "stage": stage,
            "stage_history": [{"stage": stage, "at": now_iso, "by": "f8c-seed"}],
            "source": "referral" if i % 2 == 0 else "website",
            "owner": None,
            "notes": f"{prefix} F8C seed opportunity",
            "created_at": now_iso,
            "updated_at": now_iso,
            "created_by": "f8c-seed",
            "stress_seed": True, "stress_prefix": prefix,
        })
        # 1 activity per opportunity for read surface
        opp_activities_docs.append({
            "_kind": "opportunity_activity",
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "opportunity_id": oid,
            "type": "note",
            "subject": f"{prefix}OppNote_{i + 1}",
            "body": f"{prefix} F8C seeded note #{i + 1}",
            "happened_at": now_iso, "duration_min": 15,
            "outcome": "positive" if i % 3 == 0 else "neutral",
            "created_at": now_iso, "created_by": "f8c-seed",
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 7) SALES LEADS (20) — _kind=lead, status=new (mice_opportunities collection).
    lead_status_seed = ["new", "contacted", "qualified", "proposal_sent"]
    for i in range(20):
        leads_docs.append({
            "_kind": "lead",
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "company_name": f"{prefix}LeadCo_{i + 1:02d}",
            "contact_name": f"{prefix}LeadContact_{i + 1}",
            "contact_email": f"{prefix.lower()}lead{i + 1}@e2e-stress.example.com",
            "contact_phone": f"+90555400{i + 1:04d}",
            "source": "website" if i % 2 == 0 else "referral",
            "status": lead_status_seed[i % len(lead_status_seed)],
            "priority": "medium",
            "estimated_value": 50000.0 + (i * 2000),
            "estimated_rooms": 10 + (i % 20),
            "target_checkin": (now + timedelta(days=60 + i)).date().isoformat(),
            "assigned_to": None,
            "lead_score": 50 + (i % 30),
            "notes": f"{prefix} F8C seed lead",
            "created_at": now_iso,
            "updated_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 8) BANQUET COMPETITORS (10) — mice_accounts + account_type=banquet_competitor
    # Each pre-seeded with 5 rates embedded.
    for i in range(10):
        cid = str(uuid.uuid4())
        rates_embedded = []
        for r in range(5):
            rates_embedded.append({
                "id": str(uuid.uuid4()),
                "event_type": ["meeting", "conference", "wedding", "gala", "training"][r % 5],
                "season": ["all", "high", "shoulder", "low", "high"][r % 5],
                "per_pax_price": 800.0 + (i * 100) + (r * 50),
                "currency": "TRY",
                "min_pax": 30 + (r * 10),
                "max_pax": 200 + (r * 50),
                "package_includes": ["coffee", "lunch"],
                "source": "web",
                "note": f"{prefix} F8C seed rate {r + 1}",
                "recorded_at": now_iso,
                "recorded_by": "f8c-seed",
            })
        competitors_docs.append({
            "id": cid, "tenant_id": stress_tid,
            "account_type": "banquet_competitor",
            "name": f"{prefix}Competitor_Hotel_{i + 1:02d}",
            "hotel_class": 4 + (i % 2),
            "capacity_max": 300 + (i * 50),
            "venues": [f"{prefix}Venue_{i}_{v}" for v in range(2)],
            "notes": f"{prefix} F8C seed competitor",
            "active": True,
            "competitor_rates": rates_embedded,
            "created_at": now_iso, "created_by": "f8c-seed",
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 9) PACKAGES (3)
    pkg_types = ["wedding", "conference", "corporate"]
    for i, pt in enumerate(pkg_types):
        packages_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "name": f"{prefix}Package_{pt}_{i + 1}",
            "type": pt,
            "description": f"{prefix} F8C seed package",
            "min_pax": 50, "max_pax": 300,
            "base_price": 25000.0 + (i * 5000),
            "per_pax_price": 450.0 + (i * 50),
            "currency": "TRY",
            "items": [],
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    return (spaces_docs, menus_docs, accounts_docs, contacts_docs,
            resources_docs, events_docs, opportunities_docs,
            opp_activities_docs, leads_docs, competitors_docs,
            packages_docs)


# F8D (2026-05-18) — HR / Staff / Shift / Leave / Department surface.
# Standalone factory: does not depend on rooms/bookings/guests; produces a
# self-contained org structure + attendance/leave/shift seed.
#
# Dry-run guarantees:
#   - HR notifications are in-app only (`_notify_hr_managers`/`_notify_user`
#     write to `notifications` collection; no Resend/SMS). Already covered
#     by F8B `notifications` cleanup.
#   - Payroll computation is backend-only (`_compute_payroll_for_month`);
#     no external provider. Specs MUST NOT call `/api/hr/payroll/finalize`
#     against stress tenant — it writes `payroll_records` for live workflow.
#   - Leave-balance recalc on approval is in-memory + DB update; no side
#     effects beyond the collection.
#   - Departments use unique `code` (`{prefix}DEPT_<id>`) to avoid app-level
#     uniqueness collisions on re-seed within the same prefix.
#   - Attendance records use `(staff_id, date, clock_out)` shape; all seeded
#     rows are CLOSED (clock_out set) so spec clock-in can create new OPEN
#     rows for fresh staff without collision.
#   - All rows tagged `stress_seed=True` + `stress_prefix=<prefix>` for
#     idempotent cleanup; tenant_context(stress_tid) wrap prevents leak.
def _build_f8d_docs(stress_tid: str, prefix: str, now: datetime):
    departments_docs: list[dict] = []
    positions_docs: list[dict] = []
    staff_docs: list[dict] = []
    leave_balance_docs: list[dict] = []
    attendance_docs: list[dict] = []
    shift_schedule_docs: list[dict] = []
    leave_request_docs: list[dict] = []
    shift_swap_docs: list[dict] = []
    performance_docs: list[dict] = []

    now_iso = now.isoformat()

    # 1) DEPARTMENTS (5)
    dept_seeds = [
        ("Front Office", "FO"),
        ("Housekeeping", "HK"),
        ("F&B Operations", "FNB"),
        ("Maintenance", "MAINT"),
        ("Administration", "ADMIN"),
    ]
    dept_ids: list[str] = []
    for i, (name, code) in enumerate(dept_seeds):
        did = str(uuid.uuid4())
        dept_ids.append(did)
        departments_docs.append({
            "id": did, "tenant_id": stress_tid,
            "name": f"{prefix}Dept_{name}",
            "code": f"{prefix}DEPT_{code}",
            "description": f"{prefix} F8D seed department",
            "manager_user_id": None,
            "parent_id": None,
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 2) POSITIONS (8) — bound to departments
    position_seeds = [
        ("Front Desk Agent", 0, 18000.0),
        ("Front Desk Supervisor", 0, 24000.0),
        ("Housekeeper", 1, 16000.0),
        ("HK Supervisor", 1, 22000.0),
        ("Waiter", 2, 17000.0),
        ("F&B Manager", 2, 30000.0),
        ("Maintenance Tech", 3, 19000.0),
        ("HR Officer", 4, 25000.0),
    ]
    position_ids: list[str] = []
    for i, (title, dept_idx, base) in enumerate(position_seeds):
        pid = str(uuid.uuid4())
        position_ids.append(pid)
        positions_docs.append({
            "id": pid, "tenant_id": stress_tid,
            "title": f"{prefix}Position_{title}",
            "code": f"{prefix}POS_{i + 1:02d}",
            "department_id": dept_ids[dept_idx],
            "base_salary": base,
            "currency": "TRY",
            "description": f"{prefix} F8D seed position",
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 3) STAFF MEMBERS (30) — role distribution: 10 HK, 8 FO, 6 F&B, 4 MAINT, 2 ADMIN
    role_distribution = (
        [(1, 2)] * 10 +   # HK dept, Housekeeper position
        [(0, 0)] * 8 +    # FO dept, Front Desk Agent position
        [(2, 4)] * 6 +    # F&B dept, Waiter position
        [(3, 6)] * 4 +    # MAINT dept, Maintenance Tech position
        [(4, 7)] * 2      # ADMIN dept, HR Officer position
    )
    # Router fields (active filter + name/department/position strings) — these are
    # required by GET /hr/staff (filters on `active: True`) and downstream HR endpoints.
    # Extra fields (full_name/first_name/department_id/position_id) retained for
    # forward-compat with admin/UI surfaces; ignored by HR router.
    staff_ids: list[str] = []
    dept_names = [d[0] for d in dept_seeds]   # "Front Office", "Housekeeping", ...
    pos_titles = [p[0] for p in position_seeds]  # "Front Desk Agent", ...
    for i, (dept_idx, pos_idx) in enumerate(role_distribution):
        sid = str(uuid.uuid4())
        staff_ids.append(sid)
        full = f"{prefix}Staff{i + 1:02d} Test"
        staff_docs.append({
            "id": sid, "tenant_id": stress_tid,
            "name": full,
            "first_name": f"{prefix}Staff{i + 1:02d}",
            "last_name": "Test",
            "full_name": full,
            "email": f"{prefix.lower()}staff{i + 1}@e2e-stress.example.com",
            "phone": f"+90555500{i + 1:04d}",
            "national_id": f"{prefix}NID{i + 1:08d}",
            "department": dept_names[dept_idx],
            "position": pos_titles[pos_idx],
            "department_id": dept_ids[dept_idx],
            "position_id": position_ids[pos_idx],
            "employment_type": "full_time",
            "hire_date": (now - timedelta(days=365 + (i * 7))).date().isoformat(),
            "base_salary": positions_docs[pos_idx]["base_salary"],
            "hourly_rate": round(positions_docs[pos_idx]["base_salary"] / 160, 2),
            "monthly_hours": 160,
            "annual_leave_entitlement": 14,
            "currency": "TRY",
            "active": True,
            "status": "active",
            "is_active": True,
            "manager_id": None,
            "skills": [],
            "certifications": [],
            "notes": f"{prefix} F8D seed staff",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 4) LEAVE BALANCES (30) — default 14 days for each staff
    for i, sid in enumerate(staff_ids):
        leave_balance_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "staff_id": sid,
            "year": now.year,
            "annual_entitled_days": 14,
            "used_days": 0,
            "pending_days": 0,
            "remaining_days": 14,
            "carryover_days": 0,
            "updated_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 5) ATTENDANCE RECORDS (60) — last 7 days × 10 staff sample
    # All records CLOSED (clock_out set) so spec clock-in can write OPEN rows.
    sample_staff = staff_ids[:10]
    for d in range(6):
        record_date = (now - timedelta(days=d + 1)).date()
        for sid in sample_staff:
            clock_in_dt = datetime(record_date.year, record_date.month, record_date.day, 9, 0, 0, tzinfo=UTC)
            clock_out_dt = datetime(record_date.year, record_date.month, record_date.day, 17, 30, 0, tzinfo=UTC)
            attendance_docs.append({
                "id": str(uuid.uuid4()), "tenant_id": stress_tid,
                "staff_id": sid,
                "date": record_date.isoformat(),
                "clock_in": clock_in_dt.isoformat(),
                "clock_out": clock_out_dt.isoformat(),
                "worked_minutes": 510,
                "overtime_minutes": 0,
                "break_minutes": 30,
                "source": "manual",
                "notes": f"{prefix} F8D seed attendance",
                "created_at": now_iso,
                "stress_seed": True, "stress_prefix": prefix,
            })

    # 6) SHIFT SCHEDULES (20) — next 7 days × 3 staff samples
    shift_types = ["morning", "evening", "night"]
    sched_count = 0
    for d in range(7):
        shift_date = (now + timedelta(days=d + 1)).date()
        for j in range(3):
            if sched_count >= 20:
                break
            sid = staff_ids[(d + j) % len(staff_ids)]
            shift = shift_types[j % len(shift_types)]
            start_hour = {"morning": 8, "evening": 16, "night": 0}[shift]
            shift_schedule_docs.append({
                "id": str(uuid.uuid4()), "tenant_id": stress_tid,
                "staff_id": sid,
                "staff_name": staff_docs[(d + j) % len(staff_docs)]["name"],
                "shift_date": shift_date.isoformat(),
                "date": shift_date.isoformat(),
                "shift_type": shift,
                "start_time": f"{start_hour:02d}:00",
                "end_time": f"{(start_hour + 8) % 24:02d}:00",
                "duration_minutes": 480,
                "status": "scheduled",
                "department_id": staff_docs[(d + j) % len(staff_docs)]["department_id"],
                "notes": f"{prefix} F8D seed shift",
                "created_at": now_iso,
                "stress_seed": True, "stress_prefix": prefix,
            })
            sched_count += 1

    # 7) LEAVE REQUESTS (5) — status=pending, ready for decision testing
    for i in range(5):
        sid = staff_ids[i]
        start_d = (now + timedelta(days=14 + i)).date()
        end_d = (now + timedelta(days=14 + i + 2)).date()
        leave_request_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "staff_id": sid,
            "leave_type": "annual",
            "start_date": start_d.isoformat(),
            "end_date": end_d.isoformat(),
            "days_requested": 3,
            "reason": f"{prefix} F8D seed leave request",
            "status": "pending",
            "decision_by": None,
            "decision_at": None,
            "decision_note": None,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 8) SHIFT SWAP REQUESTS (5) — status=pending, ready for consent + decision
    for i in range(5):
        requester = staff_ids[i]
        target = staff_ids[(i + 10) % len(staff_ids)]
        swap_date = (now + timedelta(days=7 + i)).date()
        # Router writes target_consent_status (not target_consent); mirror that
        # shape for forward-compat with list endpoint enrichers.
        shift_swap_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "shift_id": None,
            "shift_date": swap_date.isoformat(),
            "shift_type": "morning",
            "from_staff_id": requester,
            "requester_staff_id": requester,
            "target_staff_id": target,
            "target_consent_status": "pending",
            "target_consent_at": None,
            "target_consent_note": None,
            "reason": f"{prefix} F8D seed swap request",
            "status": "pending",
            "requested_by": None,
            "requested_at": now_iso,
            "decision_by": None,
            "decision_at": None,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 9) PERFORMANCE REVIEWS (3)
    for i in range(3):
        performance_docs.append({
            "id": str(uuid.uuid4()), "tenant_id": stress_tid,
            "staff_id": staff_ids[i],
            "period": f"{now.year}-Q{((now.month - 1) // 3) + 1}",
            "rating": 4,
            "comments": f"{prefix} F8D seed performance review",
            "reviewer_user_id": None,
            "status": "draft",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    return (departments_docs, positions_docs, staff_docs,
            leave_balance_docs, attendance_docs, shift_schedule_docs,
            leave_request_docs, shift_swap_docs, performance_docs)


def _build_f8e_docs(stress_tid: str, prefix: str, now: datetime):
    """F8E — Finance / Cashier / Accounting seed factory.

    Self-contained surface: cashier shift lifecycle, manual cash transactions,
    suppliers, expenses, accounting invoices, bank accounts, inventory items
    + stock movements, cash_flow audit trail, city ledger accounts.

    All rows tagged `stress_seed=True` + `stress_prefix=<prefix>` so the
    unified cleanup loop reaches them. No `_id` clash with live tenant data:
    every doc is stress-tenant-scoped (`tenant_id=stress_tid`).
    """
    cashier_shifts_docs: list[dict] = []
    cashier_txn_docs: list[dict] = []
    suppliers_docs: list[dict] = []
    expenses_docs: list[dict] = []
    invoices_docs: list[dict] = []
    bank_accounts_docs: list[dict] = []
    inventory_items_docs: list[dict] = []
    stock_movements_docs: list[dict] = []
    cash_flow_docs: list[dict] = []
    city_ledger_accounts_docs: list[dict] = []

    now_iso = now.isoformat()

    # 1) CASHIER SHIFTS (3) — ALL closed. Spec 24 opens its own shift so
    # the `uniq_tenant_open_shift` partial index doesn't 400 on open-shift.
    # If a leftover open shift exists from a prior aborted run, spec 24
    # Setup closes it first (defensive). Seed status="closed" everywhere.
    shift_ids: list[str] = []
    for i in range(3):
        status = "closed"
        opened_dt = now - timedelta(hours=8 * (3 - i))
        closed_dt = opened_dt + timedelta(hours=8)
        sid = str(uuid.uuid4())
        shift_ids.append(sid)
        opening = 1000.0 + i * 100
        cashier_shifts_docs.append({
            "_id": sid,
            "tenant_id": stress_tid,
            "cashier_name": f"{prefix}Cashier{i + 1}",
            "cashier_email": f"{prefix.lower()}cashier{i + 1}@e2e-stress.example.com",
            "opening_amount": opening,
            "cash_in": 250.0,
            "cash_out": 50.0,
            "status": status,
            "opened_at": opened_dt.isoformat(),
            "opened_by": f"{prefix.lower()}cashier{i + 1}@e2e-stress.example.com",
            "opened_by_name": f"{prefix}Cashier{i + 1}",
            "closed_at": closed_dt.isoformat(),
            "closing_amount": opening + 200.0,
            "expected_amount": opening + 200.0,
            "difference": 0.0,
            "denominations": {},
            "transactions": [],
            "created_at": opened_dt.isoformat(),
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 2) CASHIER TRANSACTIONS (30) — varied direction/method, attached to
    # the 3 closed seed shifts (standalone docs, not embedded; spec 24
    # operates on its own freshly-opened shift for clean lifecycle).
    methods = ["cash", "credit_card", "debit_card", "transfer"]
    directions = ["in", "out"]
    for i in range(30):
        shift_id = shift_ids[i % 3]  # round-robin across the 3 closed shifts
        direction = directions[i % 2]
        method = methods[i % len(methods)]
        amount = 50.0 + (i * 7.5)
        cashier_txn_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "shift_id": shift_id,
            "amount": amount,
            "original_amount": amount,
            "currency": "TRY",
            "fx_rate": 1.0,
            "method": method,
            "direction": direction,
            "type": "manual_in" if direction == "in" else "paid_out",
            "description": f"{prefix} F8E seed manual transaction {i + 1}",
            "ref_type": "manual",
            "ref_id": None,
            "created_by": f"{prefix.lower()}cashier1@e2e-stress.example.com",
            "created_by_name": f"{prefix}Cashier1",
            "created_at": (now - timedelta(hours=24 - i)).isoformat(),
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 3) SUPPLIERS (10)
    supplier_ids: list[str] = []
    supplier_categories = ["food", "beverage", "linen", "amenity", "maintenance",
                            "stationery", "cleaning", "electronics", "general", "uniform"]
    for i in range(10):
        sup_id = str(uuid.uuid4())
        supplier_ids.append(sup_id)
        suppliers_docs.append({
            "id": sup_id,
            "tenant_id": stress_tid,
            "name": f"{prefix}Supplier_{i + 1:02d}",
            "tax_office": f"{prefix}TaxOff",
            "tax_number": f"{prefix}TXN{i + 1:08d}",
            "email": f"{prefix.lower()}supplier{i + 1}@e2e-stress.example.com",
            "phone": f"+90555600{i + 1:04d}",
            "address": f"{prefix} Address line {i + 1}",
            "category": supplier_categories[i],
            "account_balance": 0.0,
            "active": True,
            "is_active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 4) EXPENSES (20) — varied category & VAT rate
    expense_categories = ["food", "beverage", "utilities", "maintenance",
                           "marketing", "salary", "cleaning", "stationery"]
    vat_rates = [0.0, 8.0, 18.0, 20.0]
    for i in range(20):
        cat = expense_categories[i % len(expense_categories)]
        vat = vat_rates[i % len(vat_rates)]
        gross = 100.0 + (i * 12.5)
        vat_amount = round(gross * vat / (100.0 + vat), 2) if vat > 0 else 0.0
        net = round(gross - vat_amount, 2)
        expenses_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "expense_number": f"{prefix}EXP{i + 1:05d}",
            "category": cat,
            "description": f"{prefix} F8E seed expense {i + 1}",
            "amount": net,
            "vat_rate": vat,
            "vat_amount": vat_amount,
            "total_amount": gross,
            "date": (now - timedelta(days=i)).date().isoformat(),
            "supplier_id": supplier_ids[i % len(supplier_ids)],
            "payment_method": methods[i % len(methods)],
            "receipt_url": None,
            "notes": f"{prefix} F8E seed",
            "status": "recorded",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 5) ACCOUNTING INVOICES (10) — mix of sales / purchase types
    invoice_types = ["sales", "purchase", "proforma", "credit_note", "debit_note"]
    for i in range(10):
        itype = invoice_types[i % len(invoice_types)]
        subtotal = 500.0 + (i * 75.0)
        total_vat = round(subtotal * 0.20, 2)
        total = round(subtotal + total_vat, 2)
        invoices_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "invoice_number": f"{prefix}INV{i + 1:05d}",
            "invoice_type": itype,
            "customer_name": f"{prefix}Customer_{i + 1:02d}",
            "customer_email": f"{prefix.lower()}customer{i + 1}@e2e-stress.example.com",
            "customer_tax_office": f"{prefix}TaxOff",
            "customer_tax_number": f"{prefix}CTX{i + 1:08d}",
            "customer_address": f"{prefix} Customer addr {i + 1}",
            "items": [{
                "description": f"{prefix} item {i + 1}",
                "quantity": 1,
                "unit_price": subtotal,
                "vat_rate": 20.0,
                "total": total,
            }],
            "subtotal": subtotal,
            "total_vat": total_vat,
            "total": total,
            "issue_date": (now - timedelta(days=i)).date().isoformat(),
            "due_date": (now + timedelta(days=30 - i)).date().isoformat(),
            "booking_id": None,
            "notes": f"{prefix} F8E seed invoice",
            "status": "issued",
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 6) BANK ACCOUNTS (5) — multi-currency
    bank_seeds = [
        ("Main TRY", "Garanti", "TR0001", "TRY", 50000.0),
        ("Operations TRY", "Yapi Kredi", "TR0002", "TRY", 25000.0),
        ("USD Reserve", "Garanti", "TR0003", "USD", 5000.0),
        ("EUR Reserve", "ING", "TR0004", "EUR", 3000.0),
        ("Petty Cash", "Akbank", "TR0005", "TRY", 2000.0),
    ]
    for i, (name, bank, iban_suffix, ccy, bal) in enumerate(bank_seeds):
        bank_accounts_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "name": f"{prefix}{name}",
            "bank_name": bank,
            "account_number": f"{prefix}ACC{i + 1:08d}",
            "iban": f"{prefix}TR99{iban_suffix}{i + 1:016d}",
            "currency": ccy,
            "balance": bal,
            "is_active": True,
            "active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 7) INVENTORY ITEMS (15) — linked to suppliers
    item_categories = ["food", "beverage", "amenity", "linen", "cleaning"]
    item_ids: list[str] = []
    for i in range(15):
        iid = str(uuid.uuid4())
        item_ids.append(iid)
        unit_cost = 5.0 + (i * 2.5)
        inventory_items_docs.append({
            "id": iid,
            "tenant_id": stress_tid,
            "name": f"{prefix}Item_{i + 1:02d}",
            "sku": f"{prefix}SKU{i + 1:05d}",
            "category": item_categories[i % len(item_categories)],
            "supplier_id": supplier_ids[i % len(supplier_ids)],
            "unit": "piece",
            "unit_cost": unit_cost,
            "stock_quantity": 100 + (i * 10),
            "reorder_level": 20,
            "active": True,
            "is_active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 8) STOCK MOVEMENTS (10) — initial intake history
    for i in range(10):
        item_id = item_ids[i]
        qty = 50 + (i * 5)
        movements_unit_cost = inventory_items_docs[i]["unit_cost"]
        stock_movements_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "item_id": item_id,
            "movement_type": "in",
            "quantity": qty,
            "unit_cost": movements_unit_cost,
            "total_value": round(qty * movements_unit_cost, 2),
            "reference": f"{prefix}MOV{i + 1:05d}",
            "notes": f"{prefix} F8E seed stock movement",
            "date": (now - timedelta(days=i)).date().isoformat(),
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 9) CASH FLOW (20) — synthetic audit trail entries
    for i in range(20):
        is_inflow = i % 2 == 0
        cash_flow_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "type": "inflow" if is_inflow else "outflow",
            "category": "operating",
            "amount": 250.0 + (i * 15.0),
            "currency": "TRY",
            "description": f"{prefix} F8E seed cash_flow entry {i + 1}",
            "reference_type": "expense" if not is_inflow else "invoice",
            "reference_id": None,
            "date": (now - timedelta(days=i)).date().isoformat(),
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    # 10) CITY LEDGER ACCOUNTS (5) — corporate accounts with credit limits
    for i in range(5):
        city_ledger_accounts_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": stress_tid,
            "account_name": f"{prefix}CityLedger_{i + 1:02d}",
            "company_name": f"{prefix}Company {i + 1}",
            "contact_person": f"{prefix}Contact {i + 1}",
            "email": f"{prefix.lower()}cl{i + 1}@e2e-stress.example.com",
            "phone": f"+90555700{i + 1:04d}",
            "address": f"{prefix} City Ledger addr {i + 1}",
            "credit_limit": 10000.0 + (i * 2500.0),
            "current_balance": 0.0,
            "payment_terms": 30,
            "active": True,
            "is_active": True,
            "created_at": now_iso,
            "stress_seed": True, "stress_prefix": prefix,
        })

    return (cashier_shifts_docs, cashier_txn_docs, suppliers_docs,
            expenses_docs, invoices_docs, bank_accounts_docs,
            inventory_items_docs, stock_movements_docs,
            cash_flow_docs, city_ledger_accounts_docs)


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
    # F8B: Guest Experience surface derived from baseline rooms/bookings/guests.
    qr_docs, complaint_docs, message_docs, notif_docs = _build_f8b_docs(
        rooms_docs, bookings_docs, guests_docs, stress_tid, prefix, now,
    )
    # F8C: MICE / Event / Banquet / Group Operations surface (standalone —
    # does not depend on rooms/bookings/guests; catalogs + events + opps).
    (spaces_docs, menus_docs, accounts_docs, contacts_docs,
     resources_docs, events_docs, opportunities_docs,
     opp_activities_docs, leads_docs, competitors_docs,
     packages_docs) = _build_f8c_docs(stress_tid, prefix, now)
    # F8D: HR / Staff / Shift / Leave / Department surface (standalone —
    # self-contained org structure with attendance/leave/shift seed).
    (hr_dept_docs, hr_pos_docs, hr_staff_docs,
     hr_leave_balance_docs, hr_attendance_docs, hr_shift_sched_docs,
     hr_leave_req_docs, hr_shift_swap_docs,
     hr_perf_docs) = _build_f8d_docs(stress_tid, prefix, now)
    # F8E: Finance / Cashier / Accounting surface (standalone —
    # cashier shift lifecycle + suppliers/expenses/invoices + bank
    # accounts + inventory + stock movements + cash_flow + city ledger).
    (cashier_shifts_docs, cashier_txn_docs, suppliers_docs,
     expenses_docs, invoices_docs, bank_accounts_docs,
     inventory_items_docs, stock_movements_docs,
     cash_flow_docs, city_ledger_accounts_docs) = _build_f8e_docs(
        stress_tid, prefix, now,
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
    orphan_cleanup: dict[str, int] = {}
    with tenant_context(stress_tid):
        from core.database import db
        # F8A tur-15 fix: residue from previous ABORTED runs (CI killed mid-spec,
        # network drop, OOM, etc.) accumulates in the stress tenant — teardown
        # only deletes the current-round prefix. Tur-14 verification surfaced
        # actual_rooms_total=9060 vs 560 with current prefix → 8500 orphans.
        # With sort('_id',1) on /api/pms/rooms, current-round extras (highest
        # _ids, inserted last) land at the END of the sorted result; with
        # fetchAllByPrefix maxPages=8 × pageSize=200 = 1600 capacity, pages
        # cover only the OLDEST 1600 docs → extras never reached → fetchedExtras=0.
        # Fix: scrub `stress_seed=True` docs with `stress_prefix != current`
        # across all stress collections BEFORE this round's inserts. Scoped
        # to the stress tenant + stress_seed marker → never touches real data.
        # Idempotent: also safe if no orphans exist (delete_count=0).
        for col_name in ("rooms", "bookings", "guests", "folios", "folio_charges",
                         "room_night_locks", "housekeeping_tasks",
                         "room_qr_requests", "service_complaints",
                         "messages", "notifications",
                         # F8C MICE surface — orphan scrub mirror.
                         "mice_spaces", "mice_menus", "mice_accounts",
                         "mice_contacts", "mice_resources", "mice_events",
                         "mice_opportunities", "mice_opportunity_activities",
                         "mice_packages",
                         # F8D HR surface — orphan scrub mirror.
                         "staff_members", "hr_departments", "hr_positions",
                         "attendance_records", "leave_requests",
                         "leave_balances", "shift_schedules",
                         "shift_swap_requests", "performance_reviews",
                         "payroll_records",
                         # F8E Finance / Cashier / Accounting surface —
                         # orphan scrub mirror.
                         "cashier_shifts", "cashier_transactions",
                         "expenses", "suppliers", "accounting_invoices",
                         "bank_accounts", "inventory_items",
                         "stock_movements", "cash_flow",
                         "city_ledger_accounts", "city_ledger_transactions"):
            try:
                res = await db[col_name].delete_many({
                    "tenant_id": stress_tid,
                    "stress_seed": True,
                    "stress_prefix": {"$ne": prefix},
                })
                orphan_cleanup[col_name] = res.deleted_count
            except Exception as e:
                orphan_cleanup[f"{col_name}_error"] = str(e)[:120]
        total_rooms_inserted = await _chunked_insert(db.rooms, rooms_docs, INSERT_CHUNK_SIZE)
        # Authoritative split — `counts["rooms"]` MUST equal base (500) for
        # tenant-isolation contract testing; extras are an internal stress-only
        # pool that doesn't represent real PMS inventory.
        counts["rooms"] = base_count
        # User-mandated explicit alias (CI run #24 follow-up): consumers that
        # read `base_rooms` get the same value as `rooms`; eliminates last
        # remnant of contract ambiguity.
        counts["base_rooms"] = base_count
        counts["extra_room_move_targets"] = extras_count
        counts["total_rooms"] = total_rooms_inserted
        counts["guests"] = await _chunked_insert(db.guests, guests_docs, INSERT_CHUNK_SIZE)
        counts["bookings"] = await _chunked_insert(db.bookings, bookings_docs, INSERT_CHUNK_SIZE)
        counts["folios"] = await _chunked_insert(db.folios, folios_docs, INSERT_CHUNK_SIZE)
        counts["folio_charges"] = await _chunked_insert(db.folio_charges, folio_charges_docs, INSERT_CHUNK_SIZE)
        counts["room_night_locks"] = await _chunked_insert(db.room_night_locks, rnl_docs, INSERT_CHUNK_SIZE)
        counts["housekeeping_tasks"] = await _chunked_insert(db.housekeeping_tasks, hk_docs, INSERT_CHUNK_SIZE)
        # F8B Guest Experience surface
        counts["room_qr_requests"] = await _chunked_insert(db.room_qr_requests, qr_docs, INSERT_CHUNK_SIZE)
        counts["service_complaints"] = await _chunked_insert(db.service_complaints, complaint_docs, INSERT_CHUNK_SIZE)
        counts["messages"] = await _chunked_insert(db.messages, message_docs, INSERT_CHUNK_SIZE)
        counts["notifications"] = await _chunked_insert(db.notifications, notif_docs, INSERT_CHUNK_SIZE)
        # F8C MICE / Event / Banquet / Group Operations surface
        counts["mice_spaces"] = await _chunked_insert(db.mice_spaces, spaces_docs, INSERT_CHUNK_SIZE)
        counts["mice_menus"] = await _chunked_insert(db.mice_menus, menus_docs, INSERT_CHUNK_SIZE)
        counts["mice_accounts"] = await _chunked_insert(db.mice_accounts, accounts_docs + competitors_docs, INSERT_CHUNK_SIZE)
        counts["mice_contacts"] = await _chunked_insert(db.mice_contacts, contacts_docs, INSERT_CHUNK_SIZE)
        counts["mice_resources"] = await _chunked_insert(db.mice_resources, resources_docs, INSERT_CHUNK_SIZE)
        counts["mice_events"] = await _chunked_insert(db.mice_events, events_docs, INSERT_CHUNK_SIZE)
        counts["mice_opportunities"] = await _chunked_insert(db.mice_opportunities, opportunities_docs + leads_docs, INSERT_CHUNK_SIZE)
        counts["mice_opportunity_activities"] = await _chunked_insert(db.mice_opportunity_activities, opp_activities_docs, INSERT_CHUNK_SIZE)
        counts["mice_packages"] = await _chunked_insert(db.mice_packages, packages_docs, INSERT_CHUNK_SIZE)
        # F8D HR / Staff / Shift / Leave / Department surface
        counts["hr_departments"] = await _chunked_insert(db.hr_departments, hr_dept_docs, INSERT_CHUNK_SIZE)
        counts["hr_positions"] = await _chunked_insert(db.hr_positions, hr_pos_docs, INSERT_CHUNK_SIZE)
        counts["staff_members"] = await _chunked_insert(db.staff_members, hr_staff_docs, INSERT_CHUNK_SIZE)
        counts["leave_balances"] = await _chunked_insert(db.leave_balances, hr_leave_balance_docs, INSERT_CHUNK_SIZE)
        counts["attendance_records"] = await _chunked_insert(db.attendance_records, hr_attendance_docs, INSERT_CHUNK_SIZE)
        counts["shift_schedules"] = await _chunked_insert(db.shift_schedules, hr_shift_sched_docs, INSERT_CHUNK_SIZE)
        counts["leave_requests"] = await _chunked_insert(db.leave_requests, hr_leave_req_docs, INSERT_CHUNK_SIZE)
        counts["shift_swap_requests"] = await _chunked_insert(db.shift_swap_requests, hr_shift_swap_docs, INSERT_CHUNK_SIZE)
        counts["performance_reviews"] = await _chunked_insert(db.performance_reviews, hr_perf_docs, INSERT_CHUNK_SIZE)
        # F8E Finance / Cashier / Accounting surface
        counts["cashier_shifts"] = await _chunked_insert(db.cashier_shifts, cashier_shifts_docs, INSERT_CHUNK_SIZE)
        counts["cashier_transactions"] = await _chunked_insert(db.cashier_transactions, cashier_txn_docs, INSERT_CHUNK_SIZE)
        counts["suppliers"] = await _chunked_insert(db.suppliers, suppliers_docs, INSERT_CHUNK_SIZE)
        counts["expenses"] = await _chunked_insert(db.expenses, expenses_docs, INSERT_CHUNK_SIZE)
        counts["accounting_invoices"] = await _chunked_insert(db.accounting_invoices, invoices_docs, INSERT_CHUNK_SIZE)
        counts["bank_accounts"] = await _chunked_insert(db.bank_accounts, bank_accounts_docs, INSERT_CHUNK_SIZE)
        counts["inventory_items"] = await _chunked_insert(db.inventory_items, inventory_items_docs, INSERT_CHUNK_SIZE)
        counts["stock_movements"] = await _chunked_insert(db.stock_movements, stock_movements_docs, INSERT_CHUNK_SIZE)
        counts["cash_flow"] = await _chunked_insert(db.cash_flow, cash_flow_docs, INSERT_CHUNK_SIZE)
        counts["city_ledger_accounts"] = await _chunked_insert(db.city_ledger_accounts, city_ledger_accounts_docs, INSERT_CHUNK_SIZE)
        # city_ledger_transactions is NOT seeded — specs write transactions
        # against the seeded city_ledger_accounts; cleanup loop still scrubs
        # the collection via the unified STRESS_COLLECTIONS sweep.
        # payroll_records is NOT seeded — specs are read-only on payroll
        # (`/api/hr/payroll/finalize` MUST NOT be called in stress; it writes
        # live workflow rows). Cleanup loop still reaches it via orphan scrub
        # in case future specs add seed rows.

        # F8A tur-14 diagnostic: post-insert DB ground-truth verification.
        # CI run #26 still reports `fetchedExtras=0` despite tur-13 sort fix
        # being deployed and local repro of insert+projection round-trip
        # passing. We've exhausted hypothesis-driven debugging; this block
        # surfaces the ACTUAL state of `db.rooms` immediately after
        # `_chunked_insert` returns, so the next CI run tells us
        # definitively which step is dropping data:
        #   - actual_total == 560 + actual_extras == 60   → DB is correct,
        #     bug is in /api/pms/rooms fetch path (despite sort fix).
        #   - actual_total == 560 + actual_extras == 0   → insert wrote
        #     docs but stripped `room_move_target` (factory/serializer bug).
        #   - actual_total < 560                          → `_chunked_insert`
        #     silently dropped docs despite returning 560 (insert_many
        #     ordered=False BulkWriteError handling).
        # Counts only, no PII / no document dumps — kept lightweight.
        verification: dict[str, Any] = {}
        try:
            verification["actual_rooms_total"] = await db.rooms.count_documents(
                {"tenant_id": stress_tid},
            )
            verification["actual_rooms_with_prefix"] = await db.rooms.count_documents(
                {"tenant_id": stress_tid, "stress_prefix": prefix},
            )
            verification["actual_extras_total"] = await db.rooms.count_documents(
                {"tenant_id": stress_tid, "room_move_target": True},
            )
            verification["actual_extras_with_prefix"] = await db.rooms.count_documents(
                {"tenant_id": stress_tid, "stress_prefix": prefix, "room_move_target": True},
            )
            # Round-trip a single extras doc to check field-name drift through
            # the same projection used by /api/pms/rooms.
            extras_sample = await db.rooms.find_one(
                {"tenant_id": stress_tid, "room_move_target": True},
                {"_id": 0, "id": 1, "room_number": 1, "stress_prefix": 1,
                 "room_move_target": 1, "is_active": 1, "is_virtual": 1,
                 "status": 1},
            )
            verification["extras_sample_keys"] = sorted(extras_sample.keys()) if extras_sample else None
            verification["extras_sample_prefix_match"] = (
                isinstance(extras_sample, dict)
                and isinstance(extras_sample.get("stress_prefix"), str)
                and extras_sample["stress_prefix"].startswith(prefix)
            ) if extras_sample else False
        except Exception as e:
            verification["error"] = str(e)[:200]
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
        "post_insert_verification": verification,
        "orphan_cleanup": orphan_cleanup,
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
