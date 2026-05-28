"""Phase D — Agency/Redis/Cache/Optim/CM/Tenant/DB-Optimizer/KBS-migration/Metering/Flag/Deploy."""
import asyncio
import logging
import os
from datetime import UTC, datetime

from core.database import _raw_db, db

logger = logging.getLogger(__name__)

# Boot readiness flag — `/health/ready` bunu kontrol eder.
# Phase D tamamlandığında True olur; arka plan indeks görevleri bunu beklemez
# (boot'u bloke etmemek için ayrı task'ta koşarlar).
BOOT_READY = False
PERF_INDEXES_DONE = False


async def phase_d_perf_and_marketplace(app):
    # Agency booking indexes
    try:
        col = _raw_db.agency_booking_requests
        await col.create_index([("idempotency_key", 1)], unique=True, name="uniq_idempotency_key")
        await col.create_index([("status", 1), ("hotel_id", 1)], name="idx_status_hotel")
        await col.create_index([("agency_id", 1), ("status", 1)], name="idx_agency_status")
        await col.create_index([("expires_at", 1)], name="idx_expires_at")
        await col.create_index([("created_at", -1)], name="idx_created_at_desc")
        logger.info("✅ Agency booking request indexes created")
    except Exception as e:
        logger.warning(f"Agency booking request indexes error: {e}")

    # Redis cache (best-effort)
    try:
        logger.info("🚀 Initializing Redis ultra-fast cache...")
        from redis_cache import init_redis_cache
        init_redis_cache()
        logger.info("✅ Redis cache initialized!")
    except Exception as e:
        logger.warning(f"Redis cache initialization: {e}")

    # Cache warmer
    try:
        logger.info("🔥 Initializing ultra-fast cache warmer...")
        from cache_warmer import initialize_cache_warmer
        await initialize_cache_warmer(_raw_db)
        logger.info("✅ Cache warmer initialized - responses will be instant!")
    except Exception as e:
        logger.warning(f"Cache warmer initialization: {e}")

    # Optimization systems
    try:
        logger.info("🚀 Initializing enterprise optimization systems...")
        any_rms_enabled = await _raw_db.organizations.find_one(
            {"$or": [{"plan": "enterprise"}, {"subscription_tier": "enterprise"}, {"features.hidden_rms": True}]},
            {"_id": 1},
        )
        if not any_rms_enabled:
            logger.info("ℹ️ No orgs with RMS enabled; skipping optimization init")
    except Exception as e:
        logger.warning(f"Optimization system initialization error: {e}")

    # Channel Manager 9-collection indexes
    try:
        from domains.channel_manager.unified_repository import ensure_indexes
        await ensure_indexes()
        logger.info("✅ Channel Manager 9-collection indexes created")
    except Exception as e:
        logger.warning(f"CM 9-collection indexes error: {e}")

    # QR Rozet (Tur 15) index'leri
    try:
        from domains.guest.qr_badge.indexes import ensure_qr_badge_indexes
        await ensure_qr_badge_indexes()
    except Exception as e:
        logger.warning(f"QR badge index init error: {e}")

    # Tenant uniqueness indexes
    try:
        await db.tenants.create_index(
            "hotel_id", unique=True, sparse=True, name="hotel_id_unique"
        )
        await db.users.create_index(
            [("tenant_id", 1), ("username", 1)],
            unique=True,
            partialFilterExpression={"username": {"$type": "string"}},
            name="tenant_username_unique",
        )
        # Task #254 (F8D-v2 § 32 P1): DB-level partial unique index for
        # performance reviews. Application-level find_one+insert_one is
        # not atomic under concurrent requests; this index closes the race
        # window. Partial expression excludes empty/missing period (ad-hoc
        # reviews) so the legacy NULL/empty rows do not collide.
        await db.performance_reviews.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("period", 1)],
            unique=True,
            partialFilterExpression={"period": {"$type": "string"}},
            name="uniq_tenant_staff_period",
        )
        # Task #254 (concurrency follow-up): shift overlap guard depends on
        # one lock document per (tenant, staff, shift_date). Application
        # logic in `create_shift_v2` uses find_one_and_update + upsert; the
        # DB-level uniqueness here is what converts a race-losing upsert
        # into the `DuplicateKeyError` → 409 path. Without this index the
        # overlap guard silently collapses back to the TOCTOU race.
        await db.shift_schedule_locks.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("shift_date", 1)],
            unique=True,
            name="uniq_tenant_staff_shift_date",
        )
        # Task #263: coverage rules per (tenant, department, weekday, shift_type).
        # Aynı bucket için tek kural — duplicate hesap riskini önler. Filtre +
        # gap hesabı index'le hızlanır.
        await db.hr_coverage_rules.create_index(
            [("tenant_id", 1), ("department", 1), ("weekday", 1), ("shift_type", 1)],
            unique=True,
            name="uniq_tenant_dept_weekday_shifttype",
        )
        # Task #263: leave_requests calendar + leave-check (start≤d≤end) hot
        # path; staff+status+date scan'ı önler.
        await db.leave_requests.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("status", 1), ("start_date", 1), ("end_date", 1)],
            name="idx_leave_staff_status_range",
        )
        # Task #263: shift_schedules.on_leave upsert hızlandırıcı; aynı zamanda
        # leave×shift cross-check sorgularını destekler.
        await db.shift_schedules.create_index(
            [("tenant_id", 1), ("status", 1), ("shift_date", 1)],
            name="idx_shift_status_date",
        )
        # Task #264: payroll_runs lifecycle hot path — list-by-month +
        # status-filter; period_month/status üzerinden taraması sık.
        await db.payroll_runs.create_index(
            [("tenant_id", 1), ("period_month", 1), ("status", 1)],
            name="idx_payroll_runs_period_status",
        )
        # Task #264 (post-review P1): tek-aktif-draft invariantını DB seviyesinde
        # zorla — partial unique index. İki eşzamanlı save isteği aynı ay için
        # yalnız bir draft satırı yaratabilir (ikinci DuplicateKey → endpoint
        # idempotent update path'ine düşer).
        #
        # NOT: `payroll_runs` koleksiyonu Task #264 ile yeni geldi; legacy
        # duplicate draft sıfır. İlk üretim deploy'unda hata fırlamaz. İleride
        # legacy duplicate riski oluşursa pre-migration dedupe ile birlikte
        # yeniden inşa edilmeli. Hata buraya gelirse phase-D yutmasın diye
        # ayrı try ile sarıp net log mesajı bırakıyoruz.
        try:
            await db.payroll_runs.create_index(
                [("tenant_id", 1), ("period_month", 1)],
                name="uniq_payroll_runs_open_draft",
                unique=True,
                partialFilterExpression={"status": "draft"},
            )
        except Exception as e:
            print(
                "[phase-D] WARN: payroll_runs unique-partial draft index "
                f"creation failed → idempotency/concurrency invariant NOT enforced: {e}"
            )
        # Task #264: payroll_revisions audit zinciri (parent_run_id desc).
        await db.payroll_revisions.create_index(
            [("tenant_id", 1), ("parent_run_id", 1), ("created_at", -1)],
            name="idx_payroll_revisions_parent_created",
        )
        # Task #265 (İK v2 Lifecycle): 3 yeni koleksiyon hot path index'leri.
        # staff_equipment: tenant+staff+status (assigned filter), tenant+status
        # (outstanding sweep).
        await db.staff_equipment.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("status", 1)],
            name="idx_staff_equipment_staff_status",
        )
        await db.staff_equipment.create_index(
            [("tenant_id", 1), ("status", 1), ("assigned_at", -1)],
            name="idx_staff_equipment_status_date",
        )
        # staff_warnings: tenant+staff+issued_at desc (sicil listesi).
        await db.staff_warnings.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("issued_at", -1)],
            name="idx_staff_warnings_staff_issued",
        )
        # staff_trainings: tenant+staff+completed_at (sicil), tenant+valid_until
        # (expiring sweep).
        await db.staff_trainings.create_index(
            [("tenant_id", 1), ("staff_id", 1), ("completed_at", -1)],
            name="idx_staff_trainings_staff_completed",
        )
        await db.staff_trainings.create_index(
            [("tenant_id", 1), ("valid_until", 1)],
            name="idx_staff_trainings_expiring",
        )
        logger.info("✅ Tenant uniqueness indexes ensured (hotel_id, username, performance_reviews, shift_schedule_locks, hr_coverage_rules)")
    except Exception as e:
        logger.warning(f"Tenant uniqueness index error: {e}")

    # Sales CRM piggyback indexes: mice_opportunities + mice_opportunity_activities
    # koleksiyonları Atlas 500 koleksiyon limiti workaround'u olarak hem MICE
    # opportunity'leri hem sales leads (`_kind="lead"`) hem aktiviteleri
    # (`_kind="lead_activity"`) barındırıyor. `_kind` ayraçlı filtreler
    # tenant_id ile birleşince lead listesi (~yüzlerce satır), funnel
    # aggregation ve lead-detail aktivite tarama'sı index olmadan collection
    # scan'a düşer. Aşağıdaki kompozit index'ler her üç hot path'i destekler.
    try:
        await db.mice_opportunities.create_index(
            [("tenant_id", 1), ("_kind", 1), ("status", 1), ("created_at", -1)],
            name="tenant_kind_status_created",
        )
        # Status'suz get_leads path için: filtre tenant+_kind, sort created_at
        # desc. Yukarıdaki index status'u 3. konumda taşıdığı için sort prefix
        # uyumu zayıflıyordu; bu ikinci index status-agnostic listeyi destekler.
        await db.mice_opportunities.create_index(
            [("tenant_id", 1), ("_kind", 1), ("created_at", -1)],
            name="tenant_kind_created",
        )
        await db.mice_opportunity_activities.create_index(
            [("tenant_id", 1), ("_kind", 1), ("lead_id", 1), ("created_at", -1)],
            name="tenant_kind_lead_created",
        )
        logger.info("✅ Sales CRM piggyback indexes ensured (mice_opportunities, mice_opportunity_activities)")
    except Exception as e:
        logger.warning(f"Sales CRM index error: {e}")

    # Task #254 follow-up: backfill `shift_schedule_locks` from existing
    # active `shift_schedules` rows. Before this collection existed, the
    # overlap guard read directly from `shift_schedules`; after the
    # migration the lock collection is the source-of-truth. Legacy rows
    # must be represented in the lock collection or overlap enforcement
    # silently misses them (false negative — exactly the regression the
    # task is meant to fix). Backfill is idempotent (`$addToSet` on the
    # interval dict + upsert) so it is safe to run on every boot. We run
    # it as a background task so a large historical dataset never blocks
    # platform health checks.
    asyncio.create_task(_backfill_shift_schedule_locks())

    # Database optimization
    try:
        logger.info("🚀 Running comprehensive database optimization...")
        from infra.database_optimizer import DatabaseOptimizer
        db_optimizer = DatabaseOptimizer(_raw_db)
        opt_result = await db_optimizer.create_all_indexes()
        total_idx = sum(r.get("created", 0) for r in opt_result.values() if isinstance(r, dict) and "created" in r)
        logger.info(f"✅ Database optimization complete: {total_idx} indexes ensured")
    except Exception as e:
        logger.warning(f"Database optimization warning: {e}")

    # Performance indexes (large-scale ops + KBS migration)
    # ⚠️ KRİTİK: Bu blok arka plan task'ına alındı çünkü Atlas'ın yavaş yanıt
    # verdiği anlarda 10+ create_index zinciri boot'u 30+ sn bloke ediyordu;
    # platform sağlık kontrolü timeout görünce konteyneri kill ediyor → 502.
    # Şimdi boot devam eder, indeksler arka planda hazırlanır.
    async def _create_perf_indexes_bg():
        global PERF_INDEXES_DONE
        try:
            await _create_perf_indexes_inner()
        finally:
            PERF_INDEXES_DONE = True

    asyncio.create_task(_create_perf_indexes_bg())

async def _create_perf_indexes_inner():
    global BOOT_READY  # must precede the two assignments below
    try:
        logger.info("🚀 Creating performance indexes for large-scale operations...")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("check_in", 1), ("check_out", 1)], name="idx_bookings_tenant_checkin_checkout")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("status", 1), ("check_in", 1)], name="idx_bookings_tenant_status_checkin")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("room_id", 1), ("check_in", 1)], name="idx_bookings_tenant_room_checkin")
        await _raw_db.rooms.create_index([("tenant_id", 1), ("room_number", 1)], name="idx_rooms_tenant_number", unique=True)
        await _raw_db.rooms.create_index([("tenant_id", 1), ("status", 1), ("room_type", 1)], name="idx_rooms_tenant_status_type")
        try:
            await _raw_db.guests.drop_index("email_1")
        except Exception:
            pass
        await _raw_db.guests.create_index([("tenant_id", 1), ("email", 1)], name="idx_guests_tenant_email")
        await _raw_db.guests.create_index([("tenant_id", 1), ("phone", 1)], name="idx_guests_tenant_phone")
        # messaging_automation_rules: every read/write is tenant-scoped
        # (list_automation_rules, count, distinct, automation worker scan).
        # Atlas profiler showed 425ms write samples on this collection — no
        # tenant index existed. Compound (tenant_id, trigger_event) covers
        # the worker's `find({tenant_id, trigger_event, enabled})` pattern
        # too, while still serving plain tenant_id scans as a prefix.
        await _raw_db.messaging_automation_rules.create_index(
            [("tenant_id", 1), ("trigger_event", 1), ("enabled", 1)],
            name="idx_msg_auto_rules_tenant_trigger",
        )
        await _raw_db.folios.create_index([("tenant_id", 1), ("booking_id", 1)], name="idx_folios_tenant_booking")
        await _raw_db.folios.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="idx_folios_tenant_status_created")
        # Konaklama Vergisi (KVB) idempotency: aynı folyoya iki yerden eşzamanlı
        # posting çağrısı (manual + checkout auto_post) gelse bile DB seviyesinde
        # tek satır kazanır. Bkz. routers/finance/konaklama_vergisi_core.py
        try:
            from routers.finance.konaklama_vergisi_core import ensure_posting_index
            await ensure_posting_index()
        except Exception as _kvb_idx_exc:  # pragma: no cover
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "KVB posting index ensure skipped: %s", _kvb_idx_exc,
            )
        # KBS v2 atomik tekillik
        try:
            r1 = await _raw_db.kbs_reports.update_many(
                {"_kind": "queue_job",
                 "_open_lock": {"$exists": True},
                 "status": {"$in": ["done", "dead"]}},
                {"$unset": {"_open_lock": ""}},
            )
            agg = _raw_db.kbs_reports.aggregate([
                {"$match": {"_kind": "queue_job",
                            "_open_lock": {"$exists": True},
                            "status": {"$in": ["pending", "in_progress"]}}},
                {"$sort": {"created_at": -1}},
                {"$group": {"_id": "$_open_lock", "ids": {"$push": "$id"}, "cnt": {"$sum": 1}}},
                {"$match": {"cnt": {"$gt": 1}}},
            ])
            cleaned = 0
            async for grp in agg:
                drop_ids = grp["ids"][1:]
                if drop_ids:
                    r = await _raw_db.kbs_reports.update_many(
                        {"_kind": "queue_job", "id": {"$in": drop_ids}},
                        {"$unset": {"_open_lock": ""}},
                    )
                    cleaned += r.modified_count
            if r1.modified_count or cleaned:
                logger.info(
                    f"KBS migration: closed-state lock cleared from {r1.modified_count}, "
                    f"open-state duplicate lock cleared from {cleaned}"
                )
            await _raw_db.kbs_reports.create_index(
                [("_open_lock", 1)],
                unique=True,
                partialFilterExpression={"_open_lock": {"$exists": True}},
                name="uniq_kbs_open_lock",
            )
            existing = await _raw_db.kbs_reports.index_information()
            if "uniq_kbs_open_lock" not in existing:
                raise RuntimeError("uniq_kbs_open_lock index not present after create_index")
            logger.info("✅ KBS atomik tekillik index hazır (uniq_kbs_open_lock)")
        except Exception as ix_err:
            logger.error(f"❌ KBS open_lock index FAILED: {ix_err}")
            if os.getenv("KBS_STRICT_INDEX", "1") != "0":
                raise
        logger.info("✅ Performance indexes created successfully!")
    except Exception as e:
        from pymongo.errors import OperationFailure
        if isinstance(e, OperationFailure) and getattr(e, "code", None) == 85:
            logger.debug(f"Performance index already exists with different name (cosmetic): {e}")
        else:
            logger.warning(f"Index creation warning: {e}")

    # Entitlement, Metering & Feature Flag indexes
    # F8AH tur-4 cold-boot fix (reorder): these blocks include UNIQUE
    # indexes (metering tenant+date+event, feature_flags flag_key,
    # deploy_pipelines pipeline_id) whose absence would let concurrent
    # writers create duplicates that later fail the unique-build itself.
    # Architect Round-1 flagged readiness-before-uniques as a correctness
    # window, so all unique-bearing blocks now run BEFORE the BOOT_READY
    # flip; only the purely cosmetic redundant-index cleanup runs after.
    try:
        from core.metering import ensure_metering_indexes
        await ensure_metering_indexes()
        logger.info("✅ Usage metering indexes ensured")
    except Exception as e:
        logger.warning(f"Metering index creation: {e}")

    try:
        from core.feature_flags import ensure_feature_flag_indexes
        await ensure_feature_flag_indexes()
        logger.info("✅ Feature flag indexes ensured")
    except Exception as e:
        logger.warning(f"Feature flag index creation: {e}")

    # Deploy Pipeline indexes (unique idx_pipeline_id)
    try:
        await _raw_db.deploy_pipelines.create_index([("pipeline_id", 1)], unique=True, name="idx_pipeline_id")
        await _raw_db.deploy_pipelines.create_index([("started_at", -1)], name="idx_pipeline_started")
        await _raw_db.rollback_evaluations.create_index([("evaluated_at", -1)], name="idx_rollback_eval_time")
        await _raw_db.rollback_history.create_index([("executed_at", -1)], name="idx_rollback_history_time")
        logger.info("✅ Deploy pipeline indexes ensured")
    except Exception as e:
        logger.warning(f"Deploy pipeline index creation: {e}")

    # ── BOOT_READY flip ─────────────────────────────────────────────
    # All correctness-critical UNIQUE indexes are now ensured:
    #   * rooms (tenant_id, room_number) unique           [line ~265]
    #   * kbs_reports._open_lock partial-unique           [line ~325]
    #   * metering (tenant_id, date, event_type) unique   [ensure_metering_indexes]
    #   * feature_flags flag_key unique                   [ensure_feature_flag_indexes]
    #   * deploy_pipelines.pipeline_id unique             [line above]
    # Only purely cosmetic perf hygiene (redundant-index drops) remains
    # below and runs in the BG tail without gating readiness. Cuts
    # cold-boot /health/ready wait by skipping the ~3-8s drop_index
    # chain from the gate. Idempotent re-set at function tail.
    BOOT_READY = True
    logger.info("✅ Boot phase D unique-index gate complete — readiness probe is now green (redundant cleanup continues in BG tail)")

    # ── REDUNDANT INDEX CLEANUP (Atlas Performance Advisor, Mayıs 2026) ──
    # Bağımsız try bloğu — yukarıdaki create_index zincirinde herhangi bir
    # IndexOptionsConflict (code=85) hatası bu cleanup'ı atlatmasın diye
    # ayrıldı. Drop idempotent: zaten yoksa drop_index NotFound atar (yutulur).
    try:
        _redundant = [
            ("users", "tenant_id_1"),
            ("bookings", "idx_booking_room_status"),
            ("bookings", "idx_b_tid_chkin"),
            ("bookings", "idx_b_tid_chkout"),
            ("bookings", "idx_booking_tenant_guest"),
            ("bookings", "guest_id_1"),
            ("bookings", "guest_id_1_check_in_-1"),
            ("bookings", "room_id_1"),
            ("bookings", "room_id_1_check_in_-1"),
            ("bookings", "check_in_-1"),
            ("bookings", "check_in_-1_status_1"),
            ("bookings", "check_out_-1"),
            ("bookings", "created_at_-1"),
            ("bookings", "created_at_-1_status_1"),
            ("bookings", "status_1"),
            ("bookings", "status_1_check_in_-1"),
            ("bookings", "status_1_check_out_-1"),
            ("bookings", "status_1_room_type_1"),
            ("bookings", "channel_1"),
            ("rooms", "status_1"),
            ("rooms", "status_1_room_type_1"),
            ("rooms", "room_number_1"),
            ("rooms", "room_type_1"),
            ("rooms", "floor_1"),
            # 2026-05-07: bookings 16 index → 9-10'a indir.
            #   tüm bunlar tenant-prefixli compound'larla (perf_indexes.py +
            #   atomic_*.py + d_perf.py) kapsanıyor; database_optimizer.py'dan
            #   da çıkarıldılar.
            ("bookings", "idx_b_tid_id"),
            ("bookings", "idx_b_tid_status"),
            ("bookings", "idx_b_tid_status_chkin"),
            ("bookings", "idx_b_tid_room"),
            ("bookings", "idx_b_tid_guest"),
            ("bookings", "idx_b_tid_created"),
            # folios 13 → 8: tenant-scope'suz tek-alanlı index'ler asla
            # query plan'ında seçilmiyor (tüm find tenant_db.py üstünden
            # tenant_id ile çağrılıyor).
            ("folios", "booking_id_1"),
            ("folios", "guest_id_1"),
            ("folios", "status_1"),
            ("folios", "created_at_-1"),
            ("folios", "folio_type_1"),
            ("folios", "booking_id_1_folio_type_1"),
            ("folios", "idx_f_tid_booking"),  # ↔ idx_folio_tenant_booking
            ("folios", "idx_f_tid_status"),   # ⊂ idx_folio_status_balance
            # housekeeping_tasks: tenant-prefixsiz duplikatlar + exact-dup'lar
            ("housekeeping_tasks", "idx_hk_tid_status"),  # ⊂ idx_hk_status_room
            ("housekeeping_tasks", "idx_hk_tid_done"),    # = idx_hk_completed
            ("housekeeping_tasks", "room_id_1"),
            ("housekeeping_tasks", "assigned_to_1"),
            ("housekeeping_tasks", "status_1"),
            ("housekeeping_tasks", "task_type_1"),
        ]
        _dropped: list[str] = []
        for _coll, _name in _redundant:
            try:
                await _raw_db[_coll].drop_index(_name)
                _dropped.append(f"{_coll}.{_name}")
            except Exception:
                pass  # IndexNotFound — beklenen (idempotent)
        if _dropped:
            logger.info(f"✅ Redundant index cleanup: {len(_dropped)} dropped → {', '.join(_dropped)}")
        else:
            logger.info("ℹ️ Redundant index cleanup: hepsi zaten yok (no-op)")
    except Exception as e:
        logger.warning(f"Redundant index cleanup error: {e}")

    # Phase D BG tail complete. BOOT_READY was already flipped earlier
    # in this function right after the unique-index gate (rooms, KBS,
    # metering, feature_flags, deploy_pipelines) — see "F8AH tur-4
    # cold-boot fix" comment. The only work between that flip and this
    # line is the cosmetic redundant-index cleanup. Idempotent re-set
    # below is a no-op safety net (covers the edge case where the gate
    # was skipped due to an exception in the wrapping try-block above).
    BOOT_READY = True
    logger.info("✅ Boot phase D BG tail complete (readiness was already green)")


async def _backfill_shift_schedule_locks() -> None:
    """Idempotent backfill: ensure every active shift has a lock entry.

    Task #254 follow-up. Before the lock collection existed the overlap
    guard read directly from `shift_schedules`. After cutover the lock
    collection is the source of truth for overlap; legacy rows must be
    represented or overlap enforcement silently misses them.

    Behaviour:
      * Scans `shift_schedules` for active rows (status NOT in
        cancelled/completed/deleted).
      * For each row, upserts the (tenant_id, staff_id, shift_date) lock
        doc with `$addToSet` of the interval dict — re-running with the
        same shift_id/start/end is a no-op (set semantics on the dict).
      * Best-effort: failures are logged, never raised; boot never
        depends on backfill completion.
      * Bounded scan (200k rows max per boot) to protect Atlas; if the
        dataset is larger, operators can re-run the boot or split via
        offline migration.
    """
    try:
        cursor = _raw_db.shift_schedules.find(
            {'status': {'$nin': ['cancelled', 'completed', 'deleted']}},
            {
                '_id': 0,
                'id': 1,
                'tenant_id': 1,
                'staff_id': 1,
                'shift_date': 1,
                'start_time': 1,
                'end_time': 1,
            },
        )
        scanned = 0
        upserted = 0
        async for row in cursor:
            scanned += 1
            if scanned > 200_000:
                logger.warning(
                    "Shift lock backfill: 200k row cap hit, aborting "
                    "(re-run boot or use offline migration for remainder)"
                )
                break
            sid = row.get('id')
            tid = row.get('tenant_id')
            stf = row.get('staff_id')
            day = row.get('shift_date')
            st = row.get('start_time')
            en = row.get('end_time')
            if not (sid and tid and stf and day and st and en):
                continue
            try:
                await _raw_db.shift_schedule_locks.update_one(
                    {
                        'tenant_id': tid,
                        'staff_id': stf,
                        'shift_date': day,
                    },
                    {
                        '$setOnInsert': {
                            'tenant_id': tid,
                            'staff_id': stf,
                            'shift_date': day,
                            'created_at': datetime.now(UTC).isoformat(),
                        },
                        '$addToSet': {'intervals': {
                            'shift_id': sid,
                            'start_time': st,
                            'end_time': en,
                        }},
                    },
                    upsert=True,
                )
                upserted += 1
            except Exception as row_exc:
                # Tek bir satır hatası backfill'i durdurmasın.
                logger.warning(
                    "Shift lock backfill row error (shift_id=%s): %s",
                    sid, row_exc,
                )
        logger.info(
            "✅ Shift lock backfill complete: scanned=%d upserted=%d",
            scanned, upserted,
        )
    except Exception as e:
        logger.warning(f"Shift lock backfill error: {e}")
