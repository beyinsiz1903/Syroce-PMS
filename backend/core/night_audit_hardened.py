"""
NA-001 / NA-002: Night Audit Hardening — Financial Close Engine
================================================================
State-machine driven night audit with:
  - Run-level orchestration (night_audit_runs)
  - Item-level transactional posting (night_audit_run_items)
  - Idempotent duplicate prevention (unique indexes on folio_charges)
  - Business date roll ONLY after verified successful close
  - Stale run detection, resume, and abort capabilities

Stages: validating → candidate_build → posting_charges → reconciling → rolling_date → completed
Status: pending → running → (blocked | failed | completed | partial_recovery_required)

"Date roll is a result, not a starting point."
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from typing import Any

from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.database import client, db

logger = logging.getLogger("core.night_audit_hardened")

# ── Constants ──────────────────────────────────────────────────
STALE_THRESHOLD_SECONDS = 900  # 15 min without heartbeat = stale
DEFAULT_PROPERTY = "default"
DEFAULT_CURRENCY = "TRY"
VAT_RATE = 0.10
ACCOMMODATION_TAX_RATE = 0.02

# Status
S_RUNNING = "running"
S_BLOCKED = "blocked"
S_FAILED = "failed"
S_COMPLETED = "completed"
S_PARTIAL = "partial_recovery_required"

# Stage
ST_VALIDATING = "validating"
ST_CANDIDATE = "candidate_build"
ST_POSTING = "posting_charges"
ST_RECONCILING = "reconciling"
ST_ROLLING = "rolling_date"
ST_COMPLETED = "completed"

# Item status
IS_PENDING = "pending"
IS_POSTED = "posted"
IS_SKIPPED = "skipped"
IS_FAILED = "failed"


def _now():
    return datetime.now(UTC)


def _now_iso():
    return _now().isoformat()


def _next_date(d: str) -> str:
    return (dt_date.fromisoformat(d) + timedelta(days=1)).isoformat()


# ═══════════════════════════════════════════════════════════════
#  INDEX SETUP
# ═══════════════════════════════════════════════════════════════

async def ensure_night_audit_indexes():
    """Create all required indexes for the hardened night audit."""
    idx_defs = [
        (
            "night_audit_runs",
            [("tenant_id", 1), ("property_id", 1), ("business_date", 1)],
            "idx_na_runs_unique_date",
            {"unique": True, "partialFilterExpression": {"property_id": {"$exists": True}}},
        ),
        (
            "night_audit_runs",
            [("tenant_id", 1), ("status", 1), ("started_at", -1)],
            "idx_na_runs_status",
            {},
        ),
        (
            "night_audit_runs",
            [("status", 1), ("last_heartbeat_at", 1)],
            "idx_na_runs_heartbeat",
            {},
        ),
        (
            "night_audit_run_items",
            [("run_id", 1), ("status", 1), ("created_at", 1)],
            "idx_na_items_run_status",
            {},
        ),
        (
            "night_audit_run_items",
            [("tenant_id", 1), ("booking_id", 1), ("posting_date", 1), ("posting_type", 1)],
            "idx_na_items_booking_dedup",
            {},
        ),
        (
            "folio_charges",
            [("tenant_id", 1), ("booking_id", 1), ("business_date", 1), ("charge_type", 1)],
            "idx_folio_charges_na_dedup",
            {"unique": True, "partialFilterExpression": {"business_date": {"$exists": True}, "charge_type": {"$exists": True}}},
        ),
    ]
    for coll, keys, name, kwargs in idx_defs:
        try:
            await db[coll].create_index(keys, name=name, background=True, **kwargs)
        except Exception as e:
            if "already exists" not in str(e) and "IndexOptionsConflict" not in str(e):
                logger.warning("Index %s on %s failed: %s", name, coll, e)
    logger.info("Night audit hardening indexes ensured (NA-001/NA-002)")


# ═══════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

async def _set_stage(run_id: str, stage: str, extra: dict = None):
    update = {"stage": stage, "last_heartbeat_at": _now_iso(), "updated_at": _now_iso()}
    if extra:
        update.update(extra)
    await db.night_audit_runs.update_one({"id": run_id}, {"$set": update})


async def _fail_run(run_id: str, stage: str, msg: str, status: str = S_FAILED):
    existing = await db.night_audit_runs.find_one({"id": run_id}, {"_id": 0, "errors": 1})
    errors = (existing or {}).get("errors", [])
    errors.append(msg)
    await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
        "status": status, "stage": stage, "errors": errors,
        "updated_at": _now_iso(), "completed_at": _now_iso(),
    }})


async def _heartbeat(run_id: str):
    await db.night_audit_runs.update_one(
        {"id": run_id}, {"$set": {"last_heartbeat_at": _now_iso()}},
    )


# ═══════════════════════════════════════════════════════════════
#  1. START NIGHT AUDIT
# ═══════════════════════════════════════════════════════════════

async def start_night_audit(
    tenant_id: str,
    property_id: str = None,
    business_date: str = None,
    trigger_source: str = "manual",
    actor: dict = None,
    skip_validations: bool = False,
    dry_run: bool = False,
    force_rerun: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """
    Main entry point. Creates a run, validates, builds candidates,
    posts charges transactionally, reconciles, and rolls business date.

    Modal toggle bayraklari:
    - skip_validations: ön kontrolleri atla (ön açık folio/overdue check-out/pending arrival uyarılarını yok say).
    - dry_run: aday seti olustur ama gercek folio_charges/balance/booking guncellemesi yapma; tarih rollanmaz.
    - force_rerun: ayni is gunu icin mevcut completed/failed run varsa yeni run aç (idempotency yine folio_charges unique index ile korunur).
    """
    prop_id = property_id or DEFAULT_PROPERTY
    # Bug fix: business_date verilmediginde takvim tarihine dusulmemeli; otelin
    # acik is gunu (tenant_settings.business_date) kullanilmali. Aksi halde gece
    # denetimi gercek is gununden farkli bir tarihi kapatir ve tarih ileri sicrar.
    if not business_date:
        ts = await db.tenant_settings.find_one(
            {"tenant_id": tenant_id}, {"_id": 0, "business_date": 1},
        )
        bd = (ts or {}).get("business_date") or _now().date().isoformat()
    else:
        bd = business_date
    actor = actor or {}
    run_id = str(uuid.uuid4())
    now = _now_iso()

    run_doc = {
        "id": run_id, "tenant_id": tenant_id, "property_id": prop_id,
        "business_date": bd, "status": S_RUNNING, "stage": ST_VALIDATING,
        "trigger_source": trigger_source, "started_by": actor,
        "lock_token": str(uuid.uuid4()),
        "candidate_count": 0, "processed_count": 0, "failed_count": 0, "skipped_count": 0,
        "warnings": [], "errors": [],
        "skip_validations": skip_validations, "dry_run": dry_run,
        "force_rerun": force_rerun, "reason": reason,
        "started_at": now, "completed_at": None,
        "last_heartbeat_at": now, "created_at": now, "updated_at": now,
    }

    # ── Create run (unique index prevents duplicate) ──
    try:
        await db.night_audit_runs.insert_one({**run_doc})
    except DuplicateKeyError:
        if force_rerun:
            # Tamamlanmis veya basarisiz onceki run icin acik kapi: eski run'i
            # 'rerun_superseded' olarak isaretle ve yeni run icin yeniden insert dene.
            existing = await db.night_audit_runs.find_one(
                {"tenant_id": tenant_id, "property_id": prop_id, "business_date": bd},
                {"_id": 0, "id": 1, "status": 1},
            )
            if existing and existing["status"] in (S_COMPLETED, S_FAILED, S_PARTIAL, S_BLOCKED, "rerun_superseded", "dry_run_completed"):
                # property_id'yi unset ediyoruz cunku unique index partial filter
                # `property_id: {$exists: true}` icerir — boylece supersede edilen
                # eski run unique constraint'ten cikar, yeni insert calisir.
                # Orijinal property_id'yi superseded_property_id'ye tasiyoruz.
                await db.night_audit_runs.update_one(
                    {"id": existing["id"]},
                    {
                        "$set": {
                            "status": "rerun_superseded", "updated_at": _now_iso(),
                            "superseded_by": run_id, "superseded_at": _now_iso(),
                            "superseded_property_id": prop_id,
                        },
                        "$unset": {"property_id": ""},
                    },
                )
                try:
                    await db.night_audit_runs.insert_one({**run_doc})
                except DuplicateKeyError:
                    return await _handle_duplicate_run(tenant_id, prop_id, bd)
            else:
                return await _handle_duplicate_run(tenant_id, prop_id, bd)
        else:
            dup = await _handle_duplicate_run(tenant_id, prop_id, bd)
            # Dry-run kayitlari otomatik supersede edildi → tek seferlik retry insert.
            if dup.get("code") == "RETRY":
                try:
                    await db.night_audit_runs.insert_one({**run_doc})
                except DuplicateKeyError:
                    return await _handle_duplicate_run(tenant_id, prop_id, bd)
            else:
                return dup

    run_doc.pop("_id", None)

    # ── Execute pipeline stages ──
    return await _execute_pipeline(
        run_id, tenant_id, prop_id, bd,
        skip_validations=skip_validations, dry_run=dry_run,
    )


async def _execute_pipeline(
    run_id: str, tenant_id: str, prop_id: str, bd: str,
    skip_validations: bool = False, dry_run: bool = False,
) -> dict:
    """Execute the full night audit pipeline for a run."""

    # ── Stage: Validate ──
    if not skip_validations:
        try:
            validation = await _validate_preconditions(tenant_id, prop_id, bd)
            if validation["blocking_errors"]:
                await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
                    "status": S_BLOCKED, "stage": ST_VALIDATING,
                    "errors": validation["blocking_errors"],
                    "warnings": validation["warnings"],
                    "updated_at": _now_iso(), "completed_at": _now_iso(),
                }})
                return {"success": False, "error": "Pre-audit validation failed", "code": "VALIDATION_BLOCKED",
                        "run_id": run_id, "blockers": validation["blocking_errors"]}
            if validation["warnings"]:
                await db.night_audit_runs.update_one(
                    {"id": run_id}, {"$set": {"warnings": validation["warnings"]}},
                )
        except Exception as e:
            await _fail_run(run_id, ST_VALIDATING, f"Validation error: {e}")
            return {"success": False, "error": str(e), "code": "VALIDATION_ERROR", "run_id": run_id}
    else:
        await db.night_audit_runs.update_one(
            {"id": run_id}, {"$set": {"warnings": ["Validations skipped by operator"]}},
        )

    # ── Stage: Build candidates ──
    try:
        await _set_stage(run_id, ST_CANDIDATE)
        candidate_count = await _build_candidate_set(tenant_id, prop_id, bd, run_id)
        await db.night_audit_runs.update_one(
            {"id": run_id}, {"$set": {"candidate_count": candidate_count}},
        )
    except Exception as e:
        await _fail_run(run_id, ST_CANDIDATE, f"Candidate build error: {e}")
        return {"success": False, "error": str(e), "code": "CANDIDATE_ERROR", "run_id": run_id}

    # ── Dry run: aday seti olusturuldu, gercek post yapilmadan ozet don ──
    if dry_run:
        # Pending item'lari bilgi amacli sayalim, ama folio'lara yazmayalim.
        pending = await db.night_audit_run_items.count_documents(
            {"run_id": run_id, "status": IS_PENDING},
        )
        skipped = await db.night_audit_run_items.count_documents(
            {"run_id": run_id, "status": IS_SKIPPED},
        )
        await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
            "status": "dry_run_completed", "stage": ST_COMPLETED,
            "processed_count": 0, "failed_count": 0, "skipped_count": skipped,
            "completed_at": _now_iso(), "updated_at": _now_iso(),
        }})
        run = await db.night_audit_runs.find_one({"id": run_id}, {"_id": 0})
        return {"success": True, "dry_run": True, "would_post": pending,
                "would_skip": skipped, "run": run}

    # ── Stage: Post charges ──
    return await _posting_and_close(run_id, tenant_id, bd)


async def _handle_duplicate_run(tenant_id: str, prop_id: str, bd: str) -> dict:
    existing = await db.night_audit_runs.find_one(
        {"tenant_id": tenant_id, "property_id": prop_id, "business_date": bd}, {"_id": 0},
    )
    if not existing:
        return {"success": False, "error": "Concurrent insert conflict", "code": "CONFLICT"}

    st = existing["status"]
    if st == "dry_run_completed":
        # Dry-run kayitlari finansal yan etki uretmedigi icin otomatik supersede edilir;
        # bu sayede operator dry-run sonrasi gercek run'i ayrica force_rerun
        # gerektirmeden baslatabilir. Eski kayit unique index disina cikarilir.
        await db.night_audit_runs.update_one(
            {"id": existing["id"]},
            {
                "$set": {
                    "status": "rerun_superseded", "updated_at": _now_iso(),
                    "superseded_at": _now_iso(),
                    "superseded_property_id": prop_id,
                    "supersede_reason": "auto_after_dry_run",
                },
                "$unset": {"property_id": ""},
            },
        )
        return {"success": False, "error": "RETRY_AFTER_DRY_RUN_SUPERSEDE", "code": "RETRY"}
    if st == S_COMPLETED:
        return {"success": False, "error": f"Night audit already completed for {bd}", "code": "ALREADY_COMPLETED", "run": existing}
    if st == S_BLOCKED:
        return {"success": False, "error": f"Night audit blocked for {bd}. Resolve issues first.", "code": "BLOCKED", "run": existing}
    if st == S_RUNNING:
        hb = existing.get("last_heartbeat_at")
        if hb:
            hb_dt = datetime.fromisoformat(hb)
            if hb_dt.tzinfo is None:
                hb_dt = hb_dt.replace(tzinfo=UTC)
            age = (_now() - hb_dt).total_seconds()
            if age > STALE_THRESHOLD_SECONDS:
                await _fail_run(existing["id"], existing.get("stage", ST_POSTING),
                                f"Stale run detected ({int(age)}s). Marked for recovery.", S_PARTIAL)
                return {"success": False, "error": "Stale run detected, marked for recovery", "code": "STALE_RECOVERED", "run_id": existing["id"]}
        return {"success": False, "error": "Night audit already running", "code": "ALREADY_RUNNING", "run_id": existing["id"]}
    if st in (S_FAILED, S_PARTIAL):
        return {"success": False, "error": f"Previous run in {st}. Use resume endpoint.", "code": "NEEDS_RESUME", "run_id": existing["id"]}
    return {"success": False, "error": f"Unexpected state: {st}", "code": "UNEXPECTED"}


async def _posting_and_close(run_id: str, tenant_id: str, bd: str) -> dict:
    """Post charges, reconcile, and roll date. Shared by start and resume."""
    # ── Stage: Post charges ──
    try:
        await _set_stage(run_id, ST_POSTING)
        posted, failed, skipped = await _post_charges(tenant_id, run_id)
        await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
            "processed_count": posted, "failed_count": failed, "skipped_count": skipped,
        }})
    except Exception as e:
        await _fail_run(run_id, ST_POSTING, f"Posting error: {e}")
        return {"success": False, "error": str(e), "code": "POSTING_ERROR", "run_id": run_id}

    # ── Stage: Reconcile ──
    try:
        await _set_stage(run_id, ST_RECONCILING)
        recon = await _reconcile(run_id)
        if not recon["passed"]:
            st = S_PARTIAL if recon.get("has_failed_items") else S_FAILED
            await _fail_run(run_id, ST_RECONCILING, recon.get("reason", "Reconciliation failed"), st)
            return {"success": False, "error": "Reconciliation failed", "code": "RECONCILIATION_FAILED",
                    "run_id": run_id, "details": recon}
    except Exception as e:
        await _fail_run(run_id, ST_RECONCILING, f"Reconciliation error: {e}")
        return {"success": False, "error": str(e), "code": "RECONCILIATION_ERROR", "run_id": run_id}

    # ── Stage: Roll business date ──
    try:
        await _set_stage(run_id, ST_ROLLING)
        await _roll_business_date(tenant_id, bd)
    except Exception as e:
        await _fail_run(run_id, ST_ROLLING, f"Date roll error: {e}")
        return {"success": False, "error": str(e), "code": "DATE_ROLL_ERROR", "run_id": run_id}

    # ── Complete ──
    await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
        "status": S_COMPLETED, "stage": ST_COMPLETED,
        "completed_at": _now_iso(), "updated_at": _now_iso(),
    }})
    final = await db.night_audit_runs.find_one({"id": run_id}, {"_id": 0})
    return {"success": True, "run": final}


# ═══════════════════════════════════════════════════════════════
#  2. VALIDATION
# ═══════════════════════════════════════════════════════════════

async def _validate_preconditions(
    tenant_id: str, property_id: str, bd: str,
) -> dict[str, Any]:
    """Validate preconditions before posting. Returns blocking errors and warnings."""
    blocking: list[str] = []
    warnings: list[str] = []

    # 1. No running/blocked/partial audit for this tenant
    active = await db.night_audit_runs.find_one({
        "tenant_id": tenant_id,
        "status": {"$in": [S_RUNNING, S_BLOCKED, S_PARTIAL]},
        "business_date": {"$ne": bd},
    }, {"_id": 0, "id": 1, "business_date": 1, "status": 1})
    if active:
        blocking.append(
            f"Active audit run exists for different date {active['business_date']} (status: {active['status']}, id: {active['id']})"
        )

    # 2. Checked-in bookings without room assignment
    orphans = await db.bookings.count_documents({
        "tenant_id": tenant_id, "status": "checked_in",
        "room_id": {"$in": [None, ""]},
    })
    if orphans > 0:
        blocking.append(f"{orphans} checked-in booking(s) without room assignment")

    # 3. Checked-in bookings must have at least one open folio
    # N+1 fix: per-booking find_one yerine iki toplu sorgu
    checked_in = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in"},
        {"_id": 0, "id": 1, "folio_id": 1, "guest_name": 1},
    ).to_list(2000)

    if checked_in:
        explicit_folio_ids = [bk.get("folio_id") for bk in checked_in if bk.get("folio_id")]
        booking_ids_no_folio = [bk["id"] for bk in checked_in if not bk.get("folio_id")]

        valid_folio_id_set: set = set()
        if explicit_folio_ids:
            async for f in db.folios.find(
                {"id": {"$in": explicit_folio_ids}, "tenant_id": tenant_id, "status": "open"},
                {"_id": 0, "id": 1},
            ):
                valid_folio_id_set.add(f["id"])

        booking_with_open_folio_set: set = set()
        if booking_ids_no_folio:
            async for f in db.folios.find(
                {"booking_id": {"$in": booking_ids_no_folio}, "tenant_id": tenant_id, "status": "open"},
                {"_id": 0, "booking_id": 1},
            ):
                booking_with_open_folio_set.add(f["booking_id"])

        missing_folio_count = 0
        for bk in checked_in:
            fid = bk.get("folio_id")
            if fid:
                if fid not in valid_folio_id_set:
                    missing_folio_count += 1
            else:
                if bk["id"] not in booking_with_open_folio_set:
                    missing_folio_count += 1

        if missing_folio_count > 0:
            blocking.append(f"{missing_folio_count} checked-in booking(s) without an open folio")

    # 4. BLOCKING: overdue check-outs (still checked_in past their check_out date)
    # Bu misafirler ya cikis yapmali ya da konaklama uzatilmali; sessizce ek bir gece
    # yazilmasi musafire fazla fatura ve veri tutarsizligi yaratir.
    overdue_checkouts = await db.bookings.count_documents({
        "tenant_id": tenant_id, "status": "checked_in",
        "check_out": {"$lte": bd},
    })
    if overdue_checkouts > 0:
        blocking.append(
            f"{overdue_checkouts} rezervasyonun cikis tarihi gectigi halde hala 'checked-in'. "
            f"Gece denetiminden once cikis yapin veya konaklamayi uzatin."
        )

    # 5. BLOCKING: pending arrivals (confirmed/guaranteed but never checked in by audit time)
    # Otomatik no-show yerine personel karari bekleyelim. 'Dogrulamalari Atla'
    # bayragi ile bilerek bypass edilirse mevcut akis no-show yazar.
    pending_arrivals = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
        "check_in": {"$lte": bd},
    })
    if pending_arrivals > 0:
        blocking.append(
            f"{pending_arrivals} rezervasyonun giris tarihi gectigi halde check-in yapilmadi. "
            f"Misafirleri check-in edin, manuel no-show isaretleyin veya rezervasyonu iptal edin. "
            f"Otomatik no-show istenirse 'Dogrulamalari Atla' ile devam edin."
        )

    # 6. Warning: open POS transactions
    try:
        open_pos = await db.pos_transactions.count_documents({"tenant_id": tenant_id, "status": "open"})
        if open_pos > 0:
            warnings.append(f"{open_pos} unposted POS transaction(s)")
    except Exception:
        pass

    # 7. Warning: housekeeping in progress
    try:
        hk = await db.housekeeping_tasks.count_documents({"tenant_id": tenant_id, "status": "in_progress"})
        if hk > 0:
            warnings.append(f"{hk} housekeeping task(s) still in progress")
    except Exception:
        pass

    return {"blocking_errors": blocking, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════
#  3. CANDIDATE SET GENERATION
# ═══════════════════════════════════════════════════════════════

async def _build_candidate_set(
    tenant_id: str, property_id: str, bd: str, run_id: str,
) -> int:
    """Build the posting candidate set and persist to night_audit_run_items."""
    now = _now_iso()
    items: list[dict] = []

    # ── Room charges for checked-in stayover guests ──
    # N+1 fix: tum bookings'i once topla, sonra folio + folio_charges idempotency icin tek sorgu
    bookings_list = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in"},
        {"_id": 0, "id": 1, "room_id": 1, "folio_id": 1,
         "room_rate": 1, "rate": 1, "total_amount": 1,
         "check_in": 1, "check_out": 1, "guest_name": 1, "currency": 1},
    ).to_list(5000)

    booking_ids_no_folio = [b["id"] for b in bookings_list if not b.get("folio_id")]
    folio_by_booking: dict = {}
    if booking_ids_no_folio:
        async for f in db.folios.find(
            {"booking_id": {"$in": booking_ids_no_folio}, "tenant_id": tenant_id, "status": "open"},
            {"_id": 0, "id": 1, "booking_id": 1},
        ):
            folio_by_booking[f["booking_id"]] = f["id"]

    all_booking_ids = [b["id"] for b in bookings_list]
    already_posted_set: set = set()
    if all_booking_ids:
        async for c in db.folio_charges.find(
            {"tenant_id": tenant_id, "booking_id": {"$in": all_booking_ids},
             "business_date": bd, "charge_type": "room_charge"},
            {"_id": 0, "booking_id": 1},
        ):
            already_posted_set.add(c["booking_id"])

    for booking in bookings_list:
        booking_id = booking["id"]

        # Resolve nightly rate
        rate = booking.get("room_rate") or booking.get("rate") or 0.0
        if rate <= 0 and booking.get("total_amount") and booking.get("check_in") and booking.get("check_out"):
            try:
                ci = datetime.fromisoformat(booking["check_in"].replace("Z", "+00:00"))
                co = datetime.fromisoformat(booking["check_out"].replace("Z", "+00:00"))
                nights = max((co - ci).days, 1)
                rate = round(booking["total_amount"] / nights, 2)
            except Exception:
                rate = 0.0

        # Resolve folio
        folio_id = booking.get("folio_id") or folio_by_booking.get(booking_id)

        # Determine item status
        item_status = IS_PENDING
        reason = None
        if rate <= 0:
            item_status = IS_SKIPPED
            reason = "zero_or_missing_rate"
        elif not folio_id:
            item_status = IS_SKIPPED
            reason = "no_open_folio"

        # Check if already posted for this business_date (idempotency)
        if item_status == IS_PENDING and booking_id in already_posted_set:
            item_status = IS_SKIPPED
            reason = "already_posted_for_business_date"

        vat = round(rate * VAT_RATE, 2)
        acc_tax = round(rate * ACCOMMODATION_TAX_RATE, 2)
        total = round(rate + vat + acc_tax, 2)

        items.append({
            "id": str(uuid.uuid4()), "run_id": run_id, "tenant_id": tenant_id,
            "booking_id": booking_id, "folio_id": folio_id,
            "room_id": booking.get("room_id"),
            "posting_type": "room_charge", "posting_date": bd,
            "amount": rate, "tax_amount": round(vat + acc_tax, 2), "total": total,
            "tax_breakdown": {"vat": vat, "accommodation_tax": acc_tax},
            "currency": booking.get("currency") or DEFAULT_CURRENCY,
            "status": item_status, "reason": reason,
            "journal_entry_id": None,
            "created_at": now, "updated_at": now,
        })

    # ── No-show candidates ──
    no_show_cursor = db.bookings.find({
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
        "check_in": {"$lte": bd},
    }, {"_id": 0, "id": 1, "room_id": 1, "folio_id": 1,
        "guest_name": 1, "cancellation_policy": 1, "currency": 1})
    async for booking in no_show_cursor:
        # Only if check_in date has passed (today or before)
        no_show_fee = (booking.get("cancellation_policy") or {}).get("no_show_fee", 0)
        items.append({
            "id": str(uuid.uuid4()), "run_id": run_id, "tenant_id": tenant_id,
            "booking_id": booking["id"], "folio_id": booking.get("folio_id"),
            "room_id": booking.get("room_id"),
            "posting_type": "no_show", "posting_date": bd,
            "amount": no_show_fee, "tax_amount": 0, "total": no_show_fee,
            "tax_breakdown": {}, "currency": booking.get("currency") or DEFAULT_CURRENCY,
            "status": IS_PENDING, "reason": None,
            "journal_entry_id": None,
            "created_at": now, "updated_at": now,
        })

    if items:
        await db.night_audit_run_items.insert_many([{**it} for it in items])
    return len(items)


# ═══════════════════════════════════════════════════════════════
#  4. TRANSACTIONAL POSTING
# ═══════════════════════════════════════════════════════════════

async def _post_charges(tenant_id: str, run_id: str) -> tuple[int, int, int]:
    """Post all pending items transactionally. Returns (posted, failed, skipped).

    Performance: items run with bounded concurrency (asyncio.gather) so 30 in-house
    transactions complete in ~3s wall time instead of 30s sequential. Each item
    keeps its own MongoDB transaction for atomicity, and the unique index on
    folio_charges still guarantees idempotency under parallel load.
    """
    posted = 0
    failed = 0

    items: list[dict] = await db.night_audit_run_items.find(
        {"run_id": run_id, "status": IS_PENDING}, {"_id": 0},
    ).to_list(20000)

    if not items:
        skipped = await db.night_audit_run_items.count_documents(
            {"run_id": run_id, "status": IS_SKIPPED},
        )
        return 0, 0, skipped

    # Bounded concurrency: 8 paralel transaction makul yuk altinda hizli ve guvenli
    sem = asyncio.Semaphore(8)
    heartbeat_counter = {"n": 0}

    async def _run_one(item: dict) -> bool:
        async with sem:
            if item["posting_type"] == "room_charge":
                ok = await _post_room_charge_item(tenant_id, item, run_id)
            elif item["posting_type"] == "no_show":
                ok = await _post_no_show_item(tenant_id, item, run_id)
            else:
                ok = False
            heartbeat_counter["n"] += 1
            if heartbeat_counter["n"] % 20 == 0:
                try:
                    await _heartbeat(run_id)
                except Exception:
                    pass
            return ok

    results = await asyncio.gather(*(_run_one(it) for it in items), return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            failed += 1
        elif r:
            posted += 1
        else:
            failed += 1

    # Count skipped
    skipped = await db.night_audit_run_items.count_documents(
        {"run_id": run_id, "status": IS_SKIPPED},
    )
    return posted, failed, skipped


async def _post_room_charge_item(tenant_id: str, item: dict, run_id: str) -> bool:
    """Post a single room charge within a MongoDB transaction."""
    item_id = item["id"]
    charge_id = str(uuid.uuid4())
    journal_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        async with await client.start_session() as session:
            async with session.start_transaction(
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
                read_preference=ReadPreference.PRIMARY,
            ):
                # 1. Claim item atomically
                claimed = await db.night_audit_run_items.find_one_and_update(
                    {"id": item_id, "status": IS_PENDING},
                    {"$set": {"status": "processing", "updated_at": now}},
                    session=session,
                )
                if not claimed:
                    return False  # Already claimed or processed

                # 2. Insert folio charge (unique index prevents duplicate)
                charge_doc = {
                    "id": charge_id, "tenant_id": tenant_id,
                    "folio_id": item["folio_id"], "booking_id": item["booking_id"],
                    "charge_category": "room", "charge_type": "room_charge",
                    "description": f"Room charge - {item['posting_date']}",
                    "unit_price": item["amount"], "quantity": 1,
                    "amount": item["amount"],
                    "tax_rate": round((VAT_RATE + ACCOMMODATION_TAX_RATE) * 100, 1),
                    "tax_amount": item["tax_amount"],
                    "tax_breakdown": item.get("tax_breakdown", {}),
                    "total": item["total"],
                    "currency": item.get("currency", DEFAULT_CURRENCY),
                    "business_date": item["posting_date"],
                    "date": now,
                    "night_audit_date": item["posting_date"],
                    "posted_by": "night_audit",
                    "run_id": run_id, "run_item_id": item_id,
                    "voided": False, "created_at": now,
                }
                await db.folio_charges.insert_one({**charge_doc}, session=session)

                # 3. Update folio balance
                if item["folio_id"]:
                    await db.folios.update_one(
                        {"id": item["folio_id"], "tenant_id": tenant_id},
                        {"$inc": {"balance": item["total"]}},
                        session=session,
                    )

                # 4. Journal / audit entry
                await db.pms_audit_trail.insert_one({
                    "id": journal_id, "tenant_id": tenant_id,
                    "entity_type": "folio_charge", "entity_id": charge_id,
                    "action": "night_audit_room_charge",
                    "performed_by": "night_audit",
                    "metadata": {
                        "run_id": run_id, "booking_id": item["booking_id"],
                        "folio_id": item["folio_id"], "amount": item["total"],
                        "business_date": item["posting_date"],
                    },
                    "timestamp": now,
                }, session=session)

                # 5. Mark item posted
                await db.night_audit_run_items.update_one(
                    {"id": item_id},
                    {"$set": {
                        "status": IS_POSTED, "journal_entry_id": journal_id,
                        "updated_at": now,
                    }},
                    session=session,
                )

        return True

    except DuplicateKeyError:
        # Charge already exists — mark as skipped (idempotent)
        await db.night_audit_run_items.update_one(
            {"id": item_id},
            {"$set": {"status": IS_SKIPPED, "reason": "duplicate_charge_prevented", "updated_at": _now_iso()}},
        )
        return True  # Not a failure, just already posted

    except Exception as e:
        logger.error("Room charge posting failed for item %s: %s", item_id, e)
        await db.night_audit_run_items.update_one(
            {"id": item_id},
            {"$set": {"status": IS_FAILED, "reason": str(e)[:500], "updated_at": _now_iso()}},
        )
        return False


async def _post_no_show_item(tenant_id: str, item: dict, run_id: str) -> bool:
    """Post a no-show entry: update booking status and optionally charge fee."""
    item_id = item["id"]
    now = _now_iso()

    try:
        async with await client.start_session() as session:
            async with session.start_transaction(
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
                read_preference=ReadPreference.PRIMARY,
            ):
                # Claim item
                claimed = await db.night_audit_run_items.find_one_and_update(
                    {"id": item_id, "status": IS_PENDING},
                    {"$set": {"status": "processing", "updated_at": now}},
                    session=session,
                )
                if not claimed:
                    return False

                # Mark booking as no-show
                await db.bookings.update_one(
                    {"id": item["booking_id"], "tenant_id": tenant_id},
                    {"$set": {
                        "status": "no_show",
                        "no_show_date": now,
                        "no_show_processed_by": "night_audit",
                    }},
                    session=session,
                )

                # Release room
                if item.get("room_id"):
                    await db.rooms.update_one(
                        {"id": item["room_id"], "tenant_id": tenant_id},
                        {"$set": {"status": "available", "current_booking_id": None}},
                        session=session,
                    )

                # Post no-show fee if applicable
                if item["amount"] > 0 and item.get("folio_id"):
                    fee_id = str(uuid.uuid4())
                    await db.folio_charges.insert_one({
                        "id": fee_id, "tenant_id": tenant_id,
                        "folio_id": item["folio_id"], "booking_id": item["booking_id"],
                        "charge_category": "no_show_fee", "charge_type": "no_show_fee",
                        "description": f"No-show fee - {item['posting_date']}",
                        "amount": item["amount"], "total": item["amount"],
                        "tax_amount": 0, "business_date": item["posting_date"],
                        "date": now, "posted_by": "night_audit",
                        "run_id": run_id, "run_item_id": item_id,
                        "voided": False, "created_at": now,
                    }, session=session)

                # Mark item posted
                await db.night_audit_run_items.update_one(
                    {"id": item_id},
                    {"$set": {"status": IS_POSTED, "updated_at": now}},
                    session=session,
                )

        return True

    except Exception as e:
        logger.error("No-show posting failed for item %s: %s", item_id, e)
        await db.night_audit_run_items.update_one(
            {"id": item_id},
            {"$set": {"status": IS_FAILED, "reason": str(e)[:500], "updated_at": _now_iso()}},
        )
        return False


# ═══════════════════════════════════════════════════════════════
#  5. RECONCILIATION
# ═══════════════════════════════════════════════════════════════

async def _reconcile(run_id: str) -> dict[str, Any]:
    """Verify posting integrity before rolling the date."""
    total = await db.night_audit_run_items.count_documents({"run_id": run_id})
    posted = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": IS_POSTED})
    skipped = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": IS_SKIPPED})
    failed_count = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": IS_FAILED})
    pending = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": IS_PENDING})
    processing = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": "processing"})

    if failed_count > 0:
        return {
            "passed": False, "has_failed_items": True,
            "reason": f"{failed_count} item(s) failed posting",
            "total": total, "posted": posted, "skipped": skipped,
            "failed": failed_count, "pending": pending,
        }
    if pending > 0 or processing > 0:
        return {
            "passed": False, "has_failed_items": False,
            "reason": f"{pending} pending, {processing} processing items remain",
            "total": total, "posted": posted, "skipped": skipped, "pending": pending,
        }

    return {
        "passed": True, "total": total,
        "posted": posted, "skipped": skipped, "failed": 0,
    }


# ═══════════════════════════════════════════════════════════════
#  6. BUSINESS DATE ROLL
# ═══════════════════════════════════════════════════════════════

async def _roll_business_date(tenant_id: str, current_bd: str):
    """Advance the business date. Only called after successful reconciliation."""
    next_bd = _next_date(current_bd)
    await db.tenant_settings.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "business_date": next_bd,
            "previous_business_date": current_bd,
            "business_date_updated_at": _now_iso(),
        }},
        upsert=True,
    )
    logger.info("Business date rolled: %s → %s (tenant: %s)", current_bd, next_bd, tenant_id)


# ═══════════════════════════════════════════════════════════════
#  7. RESUME
# ═══════════════════════════════════════════════════════════════

async def resume_night_audit(
    tenant_id: str, run_id: str, actor: dict = None,
) -> dict[str, Any]:
    """
    Resume a failed/partial_recovery run.
    Resets failed items to pending and re-enters the posting pipeline.
    """
    run = await db.night_audit_runs.find_one(
        {"id": run_id, "tenant_id": tenant_id}, {"_id": 0},
    )
    if not run:
        return {"success": False, "error": "Run not found", "code": "NOT_FOUND"}
    if run["status"] not in (S_FAILED, S_PARTIAL, S_BLOCKED):
        return {"success": False, "error": f"Run status is {run['status']}, cannot resume", "code": "INVALID_STATE"}

    # Reset failed items to pending
    await db.night_audit_run_items.update_many(
        {"run_id": run_id, "status": IS_FAILED},
        {"$set": {"status": IS_PENDING, "reason": None, "updated_at": _now_iso()}},
    )

    # If blocked, re-run validation first
    if run["status"] == S_BLOCKED:
        bd = run["business_date"]
        prop_id = run.get("property_id", DEFAULT_PROPERTY)
        await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
            "status": S_RUNNING, "stage": ST_VALIDATING,
            "errors": [], "updated_at": _now_iso(), "completed_at": None,
            "last_heartbeat_at": _now_iso(),
        }})
        validation = await _validate_preconditions(tenant_id, prop_id, bd)
        if validation["blocking_errors"]:
            await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
                "status": S_BLOCKED, "errors": validation["blocking_errors"],
                "updated_at": _now_iso(), "completed_at": _now_iso(),
            }})
            return {"success": False, "error": "Still blocked", "code": "STILL_BLOCKED",
                    "blockers": validation["blocking_errors"]}

    # Re-enter pipeline at posting stage
    await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
        "status": S_RUNNING, "errors": [],
        "updated_at": _now_iso(), "completed_at": None,
        "last_heartbeat_at": _now_iso(),
    }})

    return await _posting_and_close(run_id, tenant_id, run["business_date"])


# ═══════════════════════════════════════════════════════════════
#  8. ABORT
# ═══════════════════════════════════════════════════════════════

async def abort_night_audit(
    tenant_id: str, run_id: str, actor: dict = None,
) -> dict[str, Any]:
    """Abort a running/blocked/partial run. Does NOT roll back posted charges."""
    run = await db.night_audit_runs.find_one(
        {"id": run_id, "tenant_id": tenant_id}, {"_id": 0},
    )
    if not run:
        return {"success": False, "error": "Run not found", "code": "NOT_FOUND"}
    if run["status"] == S_COMPLETED:
        return {"success": False, "error": "Cannot abort a completed run", "code": "ALREADY_COMPLETED"}

    await db.night_audit_runs.update_one({"id": run_id}, {"$set": {
        "status": S_FAILED, "updated_at": _now_iso(), "completed_at": _now_iso(),
        "errors": run.get("errors", []) + [f"Aborted by {(actor or {}).get('id', 'unknown')}"],
    }})

    # Cancel pending items
    await db.night_audit_run_items.update_many(
        {"run_id": run_id, "status": {"$in": [IS_PENDING, "processing"]}},
        {"$set": {"status": IS_SKIPPED, "reason": "run_aborted", "updated_at": _now_iso()}},
    )

    return {"success": True, "message": "Run aborted", "run_id": run_id}


# ═══════════════════════════════════════════════════════════════
#  8b. PRE-AUDIT PREVIEW (Hazirlik / Genel Bakis)
# ═══════════════════════════════════════════════════════════════

async def _sample_bookings(query: dict, limit: int = 25) -> list[dict]:
    """Engelleyici/uyari listeleri icin orneklem rezervasyonlar (Duzelt linki).

    `guest_name` ve `room_no` bookings dokumaninda bos olabilir (ayri
    guests/rooms koleksiyonlarinda tutulur). Bos olanlari toplu lookup ile
    doldurarak UI'da UUID yerine gercek isim/oda no goster.
    """
    cursor = db.bookings.find(
        query,
        {
            "_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
            "room_id": 1, "room_no": 1,
            "check_in": 1, "check_out": 1, "status": 1, "confirmation_code": 1,
        },
    ).limit(limit)
    items = [b async for b in cursor]

    # Tenant scoping: lookup'lar SADECE caller'in kendi tenant'inda kalmali.
    # query.tenant_id yoksa (regex/karmasik filter) lookup'lari atla — sizinti
    # riskini almaktansa misafir adi gostermemeyi tercih et.
    tenant_id = query.get("tenant_id") if isinstance(query.get("tenant_id"), str) else None
    if not tenant_id:
        return items

    missing_guest_ids = {b["guest_id"] for b in items
                        if not b.get("guest_name") and b.get("guest_id")}
    missing_room_ids = {b["room_id"] for b in items
                       if not b.get("room_no") and b.get("room_id")}

    guest_map: dict = {}
    if missing_guest_ids:
        async for g in db.guests.find(
            {"tenant_id": tenant_id, "id": {"$in": list(missing_guest_ids)}},
            {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1},
        ):
            full = (g.get("name") or
                    " ".join(filter(None, [g.get("first_name"), g.get("last_name")])).strip())
            if full:
                guest_map[g["id"]] = full

    room_map: dict = {}
    if missing_room_ids:
        async for r in db.rooms.find(
            {"tenant_id": tenant_id, "id": {"$in": list(missing_room_ids)}},
            {"_id": 0, "id": 1, "room_number": 1, "room_no": 1},
        ):
            room_map[r["id"]] = r.get("room_number") or r.get("room_no")

    for b in items:
        if not b.get("guest_name") and b.get("guest_id") in guest_map:
            b["guest_name"] = guest_map[b["guest_id"]]
        if not b.get("room_no") and b.get("room_id") in room_map and room_map[b["room_id"]]:
            b["room_no"] = room_map[b["room_id"]]

    return items


async def build_audit_preview(tenant_id: str, property_id: str | None = None) -> dict:
    """Gece denetimi 'Hazirlik' ekrani icin yapisal ozet.

    HotelRunner'in Genel Bakis sayfasinin mantigi: gece denetimini baslatmadan
    once kullanici neyi yapip neyi yapmadigini gorur, sorunlu rezervasyonlara
    direkt atlar (action=edit_booking + booking_id).

    Doner:
      business_date / calendar_date / date_drift_days
      blockers[] : engelleyici sorunlar (kategori, mesaj, sayi, ornek 25 kayit)
      warnings[] : engellemeyen uyarilar
      rooms      : oda durumlari ozeti
      guests     : misafir hareketleri ozeti
      last_run   : son night_audit_run (varsa) — UI Son Denetim Ozeti'ni dolu tutmak icin
    """
    prop_id = property_id or DEFAULT_PROPERTY

    settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    bd = (settings or {}).get("business_date") or _now().date().isoformat()
    cal = _now().date().isoformat()
    drift = (dt_date.fromisoformat(cal) - dt_date.fromisoformat(bd)).days

    blockers: list[dict] = []
    warnings: list[dict] = []

    # 1) Baska bir is gunu icin running/blocked/partial run var mi?
    active = await db.night_audit_runs.find_one(
        {
            "tenant_id": tenant_id,
            "status": {"$in": [S_RUNNING, S_BLOCKED, S_PARTIAL]},
            "business_date": {"$ne": bd},
        },
        {"_id": 0, "id": 1, "business_date": 1, "status": 1},
    )
    if active:
        blockers.append({
            "category": "active_run_other_date",
            "label": "Baska tarih icin aktif denetim var",
            "message": (
                f"Farkli is gunu ({active['business_date']}, durum: {active['status']}) icin "
                f"acik bir denetim mevcut. Once o denetimi tamamlayin/iptal edin."
            ),
            "count": 1,
            "items": [{"run_id": active["id"], "business_date": active["business_date"], "status": active["status"]}],
            "action": "open_run",
        })

    # 2) Oda atamasi olmayan checked-in rezervasyonlar
    orphans_q = {"tenant_id": tenant_id, "status": "checked_in", "room_id": {"$in": [None, ""]}}
    orphans_count = await db.bookings.count_documents(orphans_q)
    if orphans_count > 0:
        blockers.append({
            "category": "checked_in_no_room",
            "label": "Oda atanmamis check-in",
            "message": f"{orphans_count} check-in misafire oda atanmamis.",
            "count": orphans_count,
            "items": await _sample_bookings(orphans_q),
            "action": "edit_booking",
        })

    # 3) Acik folio'su olmayan checked-in rezervasyonlar
    checked_in = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in"},
        {"_id": 0, "id": 1, "folio_id": 1, "guest_name": 1, "room_no": 1, "check_in": 1, "check_out": 1},
    ).to_list(2000)
    if checked_in:
        explicit_folio_ids = [bk.get("folio_id") for bk in checked_in if bk.get("folio_id")]
        booking_ids_no_folio = [bk["id"] for bk in checked_in if not bk.get("folio_id")]

        valid_folio_id_set: set = set()
        if explicit_folio_ids:
            async for f in db.folios.find(
                {"id": {"$in": explicit_folio_ids}, "tenant_id": tenant_id, "status": "open"},
                {"_id": 0, "id": 1},
            ):
                valid_folio_id_set.add(f["id"])

        booking_with_open_folio_set: set = set()
        if booking_ids_no_folio:
            async for f in db.folios.find(
                {"booking_id": {"$in": booking_ids_no_folio}, "tenant_id": tenant_id, "status": "open"},
                {"_id": 0, "booking_id": 1},
            ):
                booking_with_open_folio_set.add(f["booking_id"])

        missing = [
            bk for bk in checked_in
            if (bk.get("folio_id") and bk["folio_id"] not in valid_folio_id_set)
            or (not bk.get("folio_id") and bk["id"] not in booking_with_open_folio_set)
        ]
        if missing:
            blockers.append({
                "category": "checked_in_no_open_folio",
                "label": "Acik folyosuz check-in",
                "message": f"{len(missing)} check-in misafirin acik bir folyosu yok.",
                "count": len(missing),
                "items": [
                    {
                        "id": bk["id"], "guest_name": bk.get("guest_name"),
                        "room_no": bk.get("room_no"), "check_in": bk.get("check_in"),
                        "check_out": bk.get("check_out"),
                    } for bk in missing[:25]
                ],
                "action": "edit_booking",
            })

    # 4) Cikis tarihi gecmis ama hala checked_in
    overdue_q = {"tenant_id": tenant_id, "status": "checked_in", "check_out": {"$lte": bd}}
    overdue_count = await db.bookings.count_documents(overdue_q)
    if overdue_count > 0:
        blockers.append({
            "category": "overdue_checkouts",
            "label": "Gec cikis (overdue)",
            "message": (
                f"{overdue_count} rezervasyonun cikis tarihi gectigi halde hala 'checked-in'. "
                f"Cikis yapin veya konaklamayi uzatin."
            ),
            "count": overdue_count,
            "items": await _sample_bookings(overdue_q),
            "action": "checkout_or_extend",
        })

    # 5) Geliş tarihi gecmis confirmed/guaranteed (no-check-in)
    pending_arr_q = {
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
        "check_in": {"$lte": bd},
    }
    pending_count = await db.bookings.count_documents(pending_arr_q)
    if pending_count > 0:
        blockers.append({
            "category": "pending_arrivals",
            "label": "Bekleyen geliş (no-check-in)",
            "message": (
                f"{pending_count} rezervasyonun giris tarihi gectigi halde check-in yapilmadi. "
                f"Check-in yapin, no-show isaretleyin veya iptal edin."
            ),
            "count": pending_count,
            "items": await _sample_bookings(pending_arr_q),
            "action": "checkin_or_no_show",
        })

    # 6) Devam eden housekeeping (uyari, engellemez)
    inprog_hk = await db.housekeeping_tasks.count_documents({
        "tenant_id": tenant_id, "status": {"$in": ["in_progress", "started"]},
    })
    if inprog_hk > 0:
        warnings.append({
            "category": "housekeeping_in_progress",
            "label": "Devam eden kat hizmetleri",
            "message": f"{inprog_hk} oda kat hizmetleri devam ediyor.",
            "count": inprog_hk,
        })

    # 7) Acik POS / SPA siparişleri (varsa)
    try:
        open_pos = await db.pos_orders.count_documents({
            "tenant_id": tenant_id, "status": {"$in": ["open", "pending"]},
        })
        if open_pos > 0:
            warnings.append({
                "category": "pos_open_orders",
                "label": "Acik POS siparişleri",
                "message": f"{open_pos} POS siparişi hala acik (folyoya henüz yansimamis olabilir).",
                "count": open_pos,
            })
    except Exception:
        pass

    # 8) Oda durumlari ozeti
    rooms_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    room_status_counts: dict[str, int] = {}
    try:
        async for row in db.rooms.aggregate(rooms_pipeline):
            room_status_counts[(row.get("_id") or "unknown").lower()] = row["count"]
    except Exception:
        pass
    rooms_total = sum(room_status_counts.values())
    rooms_summary = {
        "total": rooms_total,
        "occupied": room_status_counts.get("occupied", 0),
        "available": room_status_counts.get("available", 0) + room_status_counts.get("clean", 0),
        "dirty": room_status_counts.get("dirty", 0),
        "out_of_order": room_status_counts.get("out_of_order", 0) + room_status_counts.get("ooo", 0),
        "blocked": room_status_counts.get("blocked", 0),
    }

    # 9) Misafir hareketleri ozeti
    in_house = await db.bookings.count_documents({"tenant_id": tenant_id, "status": "checked_in"})
    arriving_today = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
        "check_in": bd,
    })
    departing_today = await db.bookings.count_documents({
        "tenant_id": tenant_id, "status": "checked_in", "check_out": bd,
    })
    cancellations_today = await db.bookings.count_documents({
        "tenant_id": tenant_id, "status": "cancelled",
        "$or": [{"cancelled_at": {"$regex": f"^{bd}"}}, {"updated_at": {"$regex": f"^{bd}"}}],
    })
    guests_summary = {
        "in_house": in_house,
        "arriving_today": arriving_today,
        "departing_today": departing_today,
        "cancellations_today": cancellations_today,
    }

    # 10) Bu is gunu icin son run (UI Son Denetim Ozeti'ni doldurmak icin)
    last_run = await db.night_audit_runs.find_one(
        {"tenant_id": tenant_id, "property_id": prop_id, "business_date": bd},
        {"_id": 0}, sort=[("started_at", -1)],
    )

    return {
        "business_date": bd,
        "calendar_date": cal,
        "date_drift_days": drift,
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "rooms": rooms_summary,
        "guests": guests_summary,
        "last_run": last_run,
    }


# ═══════════════════════════════════════════════════════════════
#  9. QUERIES
# ═══════════════════════════════════════════════════════════════

async def get_run_status(tenant_id: str, property_id: str = None) -> dict:
    """Get current night audit status for a tenant."""
    prop_id = property_id or DEFAULT_PROPERTY
    settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    bd = (settings or {}).get("business_date", _now().date().isoformat())

    latest_run = await db.night_audit_runs.find_one(
        {"tenant_id": tenant_id, "property_id": prop_id},
        {"_id": 0}, sort=[("started_at", -1)],
    )

    running_count = await db.night_audit_runs.count_documents(
        {"tenant_id": tenant_id, "status": S_RUNNING},
    )
    blocked_count = await db.night_audit_runs.count_documents(
        {"tenant_id": tenant_id, "status": S_BLOCKED},
    )
    partial_count = await db.night_audit_runs.count_documents(
        {"tenant_id": tenant_id, "status": S_PARTIAL},
    )

    return {
        "current_business_date": bd,
        "latest_run": latest_run,
        "running_count": running_count,
        "blocked_count": blocked_count,
        "partial_recovery_count": partial_count,
    }


async def get_runs(
    tenant_id: str, limit: int = 20, skip: int = 0,
    status_filter: str = None,
) -> dict:
    """List night audit runs for a tenant."""
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if status_filter:
        query["status"] = status_filter
    runs = await db.night_audit_runs.find(
        query, {"_id": 0},
    ).sort("started_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.night_audit_runs.count_documents(query)
    return {"runs": runs, "total": total, "limit": limit, "skip": skip}


async def get_run_detail(tenant_id: str, run_id: str) -> dict | None:
    """Get a specific run by ID."""
    return await db.night_audit_runs.find_one(
        {"id": run_id, "tenant_id": tenant_id}, {"_id": 0},
    )


async def get_run_items(
    tenant_id: str, run_id: str, status_filter: str = None,
    limit: int = 100, skip: int = 0,
) -> dict:
    """List items for a specific run."""
    query: dict[str, Any] = {"run_id": run_id, "tenant_id": tenant_id}
    if status_filter:
        query["status"] = status_filter
    items = await db.night_audit_run_items.find(
        query, {"_id": 0},
    ).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)
    total = await db.night_audit_run_items.count_documents(query)
    return {"items": items, "total": total, "limit": limit, "skip": skip}


async def detect_stale_runs() -> list[dict]:
    """Find runs that appear stuck (running but heartbeat expired)."""
    cutoff = (_now() - timedelta(seconds=STALE_THRESHOLD_SECONDS)).isoformat()
    stale = await db.night_audit_runs.find(
        {"status": S_RUNNING, "last_heartbeat_at": {"$lt": cutoff}},
        {"_id": 0},
    ).to_list(100)
    return stale


async def get_health_metrics() -> dict[str, Any]:
    """Provide metrics for /health/deep endpoint."""
    try:
        # Get any tenant's last successful close
        last_completed = await db.night_audit_runs.find_one(
            {"status": S_COMPLETED}, {"_id": 0, "completed_at": 1, "business_date": 1, "tenant_id": 1},
            sort=[("completed_at", -1)],
        )
        running = await db.night_audit_runs.count_documents({"status": S_RUNNING})
        blocked = await db.night_audit_runs.count_documents({"status": S_BLOCKED})
        partial = await db.night_audit_runs.count_documents({"status": S_PARTIAL})
        failed = await db.night_audit_runs.count_documents({"status": S_FAILED})
        stale = await detect_stale_runs()

        # Current business date (from first tenant)
        settings = await db.tenant_settings.find_one({}, {"_id": 0, "business_date": 1})

        return {
            "current_business_date": (settings or {}).get("business_date"),
            "last_successful_close_at": last_completed.get("completed_at") if last_completed else None,
            "last_completed_date": last_completed.get("business_date") if last_completed else None,
            "running_count": running,
            "blocked_count": blocked,
            "partial_recovery_count": partial,
            "failed_count": failed,
            "stale_running_count": len(stale),
        }
    except Exception as e:
        return {"error": str(e)}
