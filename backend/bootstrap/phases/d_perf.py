"""Phase D — Agency/Redis/Cache/Optim/CM/Tenant/DB-Optimizer/KBS-migration/Metering/Flag/Deploy."""
import logging
import os

from core.database import _raw_db, db

logger = logging.getLogger(__name__)


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
        logger.info("✅ Tenant uniqueness indexes ensured (hotel_id, username)")
    except Exception as e:
        logger.warning(f"Tenant uniqueness index error: {e}")

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

    # Entitlement, Metering & Feature Flag indexes
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

    # Deploy Pipeline indexes
    try:
        await _raw_db.deploy_pipelines.create_index([("pipeline_id", 1)], unique=True, name="idx_pipeline_id")
        await _raw_db.deploy_pipelines.create_index([("started_at", -1)], name="idx_pipeline_started")
        await _raw_db.rollback_evaluations.create_index([("evaluated_at", -1)], name="idx_rollback_eval_time")
        await _raw_db.rollback_history.create_index([("executed_at", -1)], name="idx_rollback_history_time")
        logger.info("✅ Deploy pipeline indexes ensured")
    except Exception as e:
        logger.warning(f"Deploy pipeline index creation: {e}")
