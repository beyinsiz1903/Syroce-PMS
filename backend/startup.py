"""
startup.py — Application Lifecycle Handlers

Startup and shutdown events for the FastAPI application.
Called by server.py during bootstrap orchestration.
"""
import logging
import os
from datetime import UTC

from core.database import _raw_db, client, db

logger = logging.getLogger(__name__)


async def on_startup(app):
    """Run all startup initialization tasks."""

    # Expose db via app.state for health checks
    app.state.db = db

    # ── Crypto Service Validation ────────────────────────────────────
    try:
        from core.crypto import get_crypto_service
        crypto_svc = get_crypto_service()
        health = crypto_svc.health()
        logger.info(
            "Crypto service initialized: v2=%s kid=%s bypass=%s",
            health["v2_enabled"], health["current_kid"], health["bypass_active"],
        )
        if health["bypass_active"]:
            logger.critical("CRYPTO_BYPASS_ALLOWED=true — ENCRYPTION IS DISABLED")
    except Exception as e:
        logger.error(f"Crypto service startup failed: {e}")
        from infra.production_config import is_strict_env
        if is_strict_env():
            raise

    # ── Secrets Manager Validation ───────────────────────────────────
    try:
        from core.secrets import get_secrets_config, get_secrets_manager
        config = get_secrets_config()  # Validates config, fails loudly if invalid
        sm = get_secrets_manager()
        await sm.ensure_indexes()
        logger.info("Secrets manager initialized: provider=%s env=%s", config.provider, config.app_env)
    except Exception as e:
        logger.error(f"Secrets manager startup validation failed: {e}")
        from infra.production_config import is_strict_env
        if is_strict_env():
            raise  # Hard fail in production/staging

    # ── PII Audit indexes ───────────────────────────────────────────
    try:
        from security.pii_audit import get_pii_audit
        pii_audit = get_pii_audit()
        await pii_audit.ensure_indexes()
        logger.info("PII audit indexes ensured")
    except Exception as e:
        logger.warning(f"PII audit index creation error: {e}")

    # ── Rotation Engine indexes ──────────────────────────────────────
    try:
        from security.rotation_engine import get_rotation_engine
        rotation_engine = get_rotation_engine()
        await rotation_engine.ensure_indexes()
        logger.info("Rotation engine indexes ensured")
    except Exception as e:
        logger.warning(f"Rotation engine index creation error: {e}")

    # ── Control Plane Startup Validation ────────────────────────────
    try:
        from controlplane.startup_validator import validate_startup
        from infra.production_config import is_strict_env
        strict = is_strict_env()
        cp_report = await validate_startup(strict=strict)
        logger.info(
            "Control plane validation: %s (%d issues)",
            cp_report.get("overall", "unknown"),
            len(cp_report.get("failures", [])),
        )
    except Exception as e:
        logger.error(f"Control plane startup validation failed: {e}")
        from infra.production_config import is_strict_env
        if is_strict_env():
            raise

    # ── Event Timeline indexes ───────────────────────────────────────
    try:
        from controlplane.timeline_writer import ensure_timeline_indexes
        await ensure_timeline_indexes()
        logger.info("Event timeline indexes ensured")
    except Exception as e:
        logger.warning(f"Event timeline index creation error: {e}")

    # ── Webhook Raw Payload indexes ───────────────────────────────────
    try:
        await _raw_db.webhook_raw_payloads.create_index(
            [("correlation_id", 1)],
            name="idx_raw_payload_correlation",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("tenant_id", 1), ("external_id", 1), ("received_at", -1)],
            name="idx_raw_payload_tenant_ext",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("tenant_id", 1), ("provider", 1), ("received_at", -1)],
            name="idx_raw_payload_provider",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("received_at", 1)],
            name="idx_raw_payload_ttl",
            expireAfterSeconds=7776000,  # 90 days
        )
        logger.info("Webhook raw payload indexes ensured")
    except Exception as e:
        logger.warning(f"Webhook raw payload index creation error: {e}")

    # ── Dashboard snapshot indexes + worker ────────────────────────
    try:
        from controlplane.dashboard_aggregator import (
            ensure_snapshot_indexes,
            get_snapshot_worker,
        )
        await ensure_snapshot_indexes()
        snapshot_worker = get_snapshot_worker()
        await snapshot_worker.start()
        app.state.dashboard_snapshot_worker = snapshot_worker
        logger.info("Dashboard snapshot worker started (60s interval)")
    except Exception as e:
        logger.warning(f"Dashboard snapshot worker startup error: {e}")

    # ── Deploy event indexes ────────────────────────────────────────
    try:
        from controlplane.deploy_tracker import ensure_deploy_indexes
        await ensure_deploy_indexes()
        logger.info("Deploy event indexes ensured")
    except Exception as e:
        logger.warning(f"Deploy event index creation error: {e}")

    # ── Auto-seed demo data ─────────────────────────────────────────
    # v109 round-8 architect blocker: NEVER seed demo data in production.
    # The seed contains a real-looking HotelRunner token in auto_seed.py
    # (lines 835/874/989). Production must not boot with these credentials
    # written into a real tenant. Operators can override with
    # ALLOW_AUTO_SEED_IN_PROD=1 if they have rotated the seed token.
    # 5th-pass: use the unified helper so APP_ENV/ENVIRONMENT/NODE_ENV are
    # all honored consistently (matches production_config gates above).
    from infra.production_config import is_production_env
    _seed_override = os.environ.get("ALLOW_AUTO_SEED_IN_PROD", "").lower() in {"1", "true", "yes"}
    if is_production_env() and not _seed_override:
        logger.info("Auto-seed skipped — production mode (set ALLOW_AUTO_SEED_IN_PROD=1 to override)")
    else:
        try:
            from auto_seed import auto_seed_if_empty
            await auto_seed_if_empty(_raw_db)
        except Exception as e:
            logger.warning(f"Auto-seed error: {e}")

    # ── Ensure Exely webhook test connection exists ──────────────────
    try:
        existing = await _raw_db.exely_connections.find_one({"hotel_code": "501694"}, {"_id": 1})
        if not existing:
            tenant = await _raw_db.tenants.find_one({}, {"_id": 0, "id": 1})
            tid = tenant["id"] if tenant else "demo"
            from datetime import datetime
            await _raw_db.exely_connections.insert_one({
                "id": str(__import__("uuid").uuid4()),
                "tenant_id": tid,
                "hotel_code": "501694",
                "credentials_ref": "",
                "endpoint_url": "",
                "property_name": "Exely Webhook Connection",
                "auto_sync_reservations": True,
                "sync_interval_minutes": 15,
                "mode": "sandbox",
                "currency": "TRY",
                "is_active": True,
                "room_types": [],
                "rate_plans": [],
                "connected_at": datetime.now(UTC).isoformat(),
                "last_sync_at": None,
                "created_by": "startup_ensure",
            })
            logger.info("Exely webhook connection (501694) ensured on startup")
    except Exception as e:
        logger.warning(f"Exely connection ensure error: {e}")

    # ── Booking overbooking prevention indexes ────────────────────────
    try:
        from core.atomic_booking import ensure_booking_indexes
        await ensure_booking_indexes()
        logger.info("Booking overlap prevention indexes ensured")
    except Exception as e:
        logger.warning(f"Booking index creation error: {e}")

    # ── Room-Type Inventory indexes + worker (ADR-003, Phase C.1) ────
    try:
        from core.room_type_inventory_service import (
            ensure_room_type_inventory_indexes,
            get_inventory_worker,
        )
        await ensure_room_type_inventory_indexes()
        inv_worker = get_inventory_worker()
        await inv_worker.start()
        app.state.room_type_inventory_worker = inv_worker
        logger.info("Room-type inventory worker started (300s interval)")
    except Exception as e:
        logger.warning(f"Room-type inventory worker startup error: {e}")

    # ── Booking hold sweeper (TTL auto-release) ──────────────────────
    try:
        from core.booking_hold_service import start_hold_sweeper
        start_hold_sweeper()
        logger.info("Booking hold sweeper started")
    except Exception as e:
        logger.warning(f"Booking hold sweeper start error: {e}")

    # ── Mailing automation worker (rezervasyon onay/hatırlatma vb.) ──
    try:
        from workers.mailing_automation import start as start_mailing_automation
        start_mailing_automation()
        logger.info("Mailing automation worker started (600s interval)")
    except Exception as e:
        logger.warning(f"Mailing automation worker start error: {e}")

    # ── Marketplace subscription expiry worker (saatlik) ──
    try:
        import asyncio as _asyncio

        from workers.subscription_expiry import run_loop as _sub_loop
        _asyncio.create_task(_sub_loop(3600), name="subscription-expiry")
        logger.info("Subscription expiry worker started (3600s interval)")
    except Exception as e:
        logger.warning(f"Subscription expiry worker start error: {e}")

    # ── Marketplace indexes + product seed ──
    try:
        from core.subscriptions import ensure_indexes as _ms_indexes
        await _ms_indexes()
        logger.info("Marketplace indexes ensured")
    except Exception as e:
        logger.warning(f"Marketplace index creation error: {e}")

    # ── Check-in/Check-out transaction indexes ─────────────────────
    try:
        from core.atomic_checkin_checkout import ensure_checkin_checkout_indexes
        await ensure_checkin_checkout_indexes()
        logger.info("Check-in/check-out indexes ensured")
    except Exception as e:
        logger.warning(f"Check-in/check-out index creation error: {e}")

    # ── Folio Ledger indexes ─────────────────────────────────────────
    try:
        from core.folio_ledger_service import ensure_folio_ledger_indexes
        await ensure_folio_ledger_indexes()
    except Exception as e:
        logger.warning(f"Folio ledger index creation error: {e}")

    # ── Learning Loop indexes ────────────────────────────────────────
    try:
        from core.learning_loop import ensure_learning_loop_indexes
        await ensure_learning_loop_indexes()
    except Exception as e:
        logger.warning(f"Learning loop index creation error: {e}")

    # ── PERF-001: Compound indexes for hot queries ─────────────────
    try:
        await _ensure_performance_indexes()
        logger.info("Performance indexes ensured")
    except Exception as e:
        logger.warning(f"Performance index creation error: {e}")

    # ── Agency booking indexes ──────────────────────────────────────
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

    # ── Redis cache (best-effort) ───────────────────────────────────
    try:
        logger.info("🚀 Initializing Redis ultra-fast cache...")
        from redis_cache import init_redis_cache
        init_redis_cache()
        logger.info("✅ Redis cache initialized!")
    except Exception as e:
        logger.warning(f"Redis cache initialization: {e}")

    # ── Cache warmer ────────────────────────────────────────────────
    try:
        logger.info("🔥 Initializing ultra-fast cache warmer...")
        from cache_warmer import initialize_cache_warmer
        await initialize_cache_warmer(_raw_db)
        logger.info("✅ Cache warmer initialized - responses will be instant!")
    except Exception as e:
        logger.warning(f"Cache warmer initialization: {e}")

    # ── Optimization systems ────────────────────────────────────────
    try:
        logger.info("🚀 Initializing enterprise optimization systems...")
        any_rms_enabled = await _raw_db.organizations.find_one(
            {"$or": [{"plan": "enterprise"}, {"subscription_tier": "enterprise"}, {"features.hidden_rms": True}]},
            {"_id": 1},
        )
        if not any_rms_enabled:
            logger.info("ℹ️ No orgs with RMS enabled; skipping optimization init")
        # Note: legacy `optimization_endpoints` module was removed; archival/materialized
        # views are now handled by domain-specific routers and scheduled jobs.
    except Exception as e:
        logger.warning(f"Optimization system initialization error: {e}")

    # ── Channel Manager 9-collection indexes ───────────────────────
    try:
        from domains.channel_manager.unified_repository import ensure_indexes
        await ensure_indexes()
        logger.info("✅ Channel Manager 9-collection indexes created")
    except Exception as e:
        logger.warning(f"CM 9-collection indexes error: {e}")

    # ── Tenant uniqueness indexes (hotel_id, username per tenant) ──
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

    # ── Database optimization ───────────────────────────────────────
    try:
        logger.info("🚀 Running comprehensive database optimization...")
        from infra.database_optimizer import DatabaseOptimizer
        db_optimizer = DatabaseOptimizer(_raw_db)
        opt_result = await db_optimizer.create_all_indexes()
        total_idx = sum(r.get("created", 0) for r in opt_result.values() if isinstance(r, dict) and "created" in r)
        logger.info(f"✅ Database optimization complete: {total_idx} indexes ensured")
    except Exception as e:
        logger.warning(f"Database optimization warning: {e}")

    # ── Performance indexes ─────────────────────────────────────────
    try:
        logger.info("🚀 Creating performance indexes for large-scale operations...")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("check_in", 1), ("check_out", 1)], name="idx_bookings_tenant_checkin_checkout")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("status", 1), ("check_in", 1)], name="idx_bookings_tenant_status_checkin")
        await _raw_db.bookings.create_index([("tenant_id", 1), ("room_id", 1), ("check_in", 1)], name="idx_bookings_tenant_room_checkin")
        await _raw_db.rooms.create_index([("tenant_id", 1), ("room_number", 1)], name="idx_rooms_tenant_number", unique=True)
        await _raw_db.rooms.create_index([("tenant_id", 1), ("status", 1), ("room_type", 1)], name="idx_rooms_tenant_status_type")
        # Drop legacy global unique email index if present (causes duplicate key for empty emails)
        try:
            await _raw_db.guests.drop_index("email_1")
        except Exception:
            pass
        await _raw_db.guests.create_index([("tenant_id", 1), ("email", 1)], name="idx_guests_tenant_email")
        await _raw_db.guests.create_index([("tenant_id", 1), ("phone", 1)], name="idx_guests_tenant_phone")
        await _raw_db.folios.create_index([("tenant_id", 1), ("booking_id", 1)], name="idx_folios_tenant_booking")
        await _raw_db.folios.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="idx_folios_tenant_status_created")
        # KBS v2: atomik tekillik kilidi — aynı (tenant, booking, action) için
        # aynı anda en fazla 1 açık iş (pending|in_progress) garanti.
        # Closed (done|dead) state'lere geçildiğinde _open_lock unset edilir →
        # ileride yeni iş açılabilir. Partial filter: sadece açık işler indexlenir.
        try:
            # KBS v2 migration (idempotent):
            # 1) Closed (done|dead) state'lerdeki tüm jobs'tan _open_lock kaldır
            #    — closed bir job lock tutamaz; aksi halde gelecekteki enqueue
            #    kalıcı olarak bloke olur.
            r1 = await _raw_db.kbs_reports.update_many(
                {"_kind": "queue_job",
                 "_open_lock": {"$exists": True},
                 "status": {"$in": ["done", "dead"]}},
                {"$unset": {"_open_lock": ""}},
            )
            # 2) Aynı _open_lock değerine sahip birden fazla AÇIK job varsa
            #    en yenisini (created_at desc) tut, kalanlarda lock'ı kaldır
            #    (orphan iş olarak kuyrukta kalır ama lock'ı bloke etmez).
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
                drop_ids = grp["ids"][1:]  # en yeniyi tut, eskileri unlock
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
            # 3) Index'in gerçekten oluştuğunu doğrula — yoksa atomik tekillik yok.
            existing = await _raw_db.kbs_reports.index_information()
            if "uniq_kbs_open_lock" not in existing:
                raise RuntimeError("uniq_kbs_open_lock index not present after create_index")
            logger.info("✅ KBS atomik tekillik index hazır (uniq_kbs_open_lock)")
        except Exception as ix_err:
            # Atomik tekillik garantisi olmadan KBS kuyruğu güvenli değil → loud failure.
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

    # ── Entitlement, Metering & Feature Flag indexes ───────────────
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

    # ── Deploy Pipeline indexes ──────────────────────────────────────
    try:
        await _raw_db.deploy_pipelines.create_index([("pipeline_id", 1)], unique=True, name="idx_pipeline_id")
        await _raw_db.deploy_pipelines.create_index([("started_at", -1)], name="idx_pipeline_started")
        await _raw_db.rollback_evaluations.create_index([("evaluated_at", -1)], name="idx_rollback_eval_time")
        await _raw_db.rollback_history.create_index([("executed_at", -1)], name="idx_rollback_history_time")
        logger.info("✅ Deploy pipeline indexes ensured")
    except Exception as e:
        logger.warning(f"Deploy pipeline index creation: {e}")

    # ── OTA-002: Outbox Pattern indexes ─────────────────────────────
    try:
        from core.outbox_service import ensure_outbox_indexes
        await ensure_outbox_indexes(_raw_db)
        logger.info("Outbox pattern indexes ensured (OTA-002)")
    except Exception as e:
        logger.warning(f"Outbox index creation error: {e}")

    # ── OTA-002: Start production outbox worker ─────────────────────
    try:
        from core.outbox_worker import outbox_ota_worker
        await outbox_ota_worker.start()
        app.state.outbox_ota_worker = outbox_ota_worker
        logger.info("OTA Outbox Worker started (guaranteed delivery)")
    except Exception as e:
        logger.warning(f"OTA Outbox Worker startup warning: {e}")

    # ── DATA-001: Import bridge indexes + worker ─────────────────────
    try:
        from core.import_bridge_service import ensure_import_indexes
        await ensure_import_indexes()
        logger.info("Import bridge indexes ensured (DATA-001)")
    except Exception as e:
        logger.warning(f"Import bridge index creation error: {e}")

    try:
        from core.import_retry_worker import import_retry_worker
        await import_retry_worker.start()
        app.state.import_retry_worker = import_retry_worker
        logger.info("Import Retry Worker started (DATA-001)")
    except Exception as e:
        logger.warning(f"Import Retry Worker startup warning: {e}")

    # ── Legacy outbox lifecycle worker (migration events only) ──────
    try:
        from shared_kernel.outbox_lifecycle import outbox_lifecycle_worker
        await outbox_lifecycle_worker.start()
        app.state.outbox_lifecycle_worker = outbox_lifecycle_worker
        logger.info("Legacy outbox lifecycle worker started")
    except Exception as e:
        logger.warning(f"Outbox lifecycle worker startup warning: {e}")

    # ── Af-sadakat outbound dispatcher loop ─────────────────────────
    try:
        import asyncio as _asyncio_afs

        from core.afsadakat_outbound import dispatch_pending_loop as _afs_loop
        app.state.afsadakat_dispatcher_task = _asyncio_afs.create_task(
            _afs_loop(), name="afsadakat-outbound-dispatcher"
        )
        logger.info("✅ Af-sadakat outbound dispatcher started")
    except Exception as e:
        logger.warning(f"Af-sadakat outbound dispatcher warning: {e}")

    # ── Channel Manager v2 indexes ──────────────────────────────────
    try:
        from channel_manager.infrastructure.indexes import create_cm_indexes
        await create_cm_indexes()
        logger.info("✅ Channel Manager v2 indexes created")
    except Exception as e:
        logger.warning(f"Channel Manager v2 indexes warning: {e}")

    # ── Event Bus ───────────────────────────────────────────────────
    try:
        from modules.event_bus.abstraction import event_bus
        await event_bus.initialize()
        logger.info(f"✅ Event Bus initialized in {event_bus.mode.upper()} mode")
    except Exception as e:
        logger.warning(f"Event Bus initialization warning: {e}")

    # ── Persistence indexes ─────────────────────────────────────────
    try:
        from modules.persistence_repositories import ensure_all_indexes
        await ensure_all_indexes()
        logger.info("✅ Persistence repository indexes ensured")
    except Exception as e:
        logger.warning(f"Persistence indexes warning: {e}")

    # ── Infrastructure Hardening ────────────────────────────────────
    # The WS Redis adapter must always have its `local_handler` wired —
    # even when Redis is unavailable — so that read-receipt and typing
    # events still reach clients in single-instance / Redis-down mode.
    # We initialise the adapter unconditionally and only attach a Redis
    # client + cross-instance subscriptions when the connection succeeds.
    from infra.ws_redis_adapter import ws_redis_adapter
    from infra.auth_cache_pubsub import auth_cache_pubsub
    from infra.kbs_queue_pubsub import kbs_queue_pubsub
    from websocket_server import local_broadcast as _ws_local_broadcast

    try:
        from infra.redis_cluster import redis_cluster
        connected = await redis_cluster.connect()
        if connected:
            from infra.distributed_lock import lock_manager
            lock_manager.set_redis(redis_cluster.get_lock_client())
            # Build a per-worker unique instance id so pub/sub loopback
            # guards (``source_instance`` checks in ws_redis_adapter and
            # auth_cache_pubsub) actually distinguish workers. Without
            # uniqueness, every worker would skip every broadcast as its
            # "own" and cross-instance fan-out would silently break.
            import os as _os
            import socket as _socket
            import uuid as _uuid
            if hasattr(redis_cluster, "instance_id") and getattr(
                redis_cluster, "instance_id", None
            ):
                instance_id = redis_cluster.instance_id
            else:
                instance_id = (
                    f"{_socket.gethostname()}:{_os.getpid()}:"
                    f"{_uuid.uuid4().hex[:8]}"
                )
            await ws_redis_adapter.initialize(
                redis_cluster.get_pubsub_client(),
                instance_id,
                local_handler=_ws_local_broadcast,
            )
            # Subscribe to rooms whose events must traverse instances:
            # 'pms' carries internal_message_read / internal_user_typing
            # so live read receipts and typing indicators work under
            # horizontal scaling.
            try:
                await ws_redis_adapter.subscribe("pms")
            except Exception as e:
                logger.warning(f"WS Redis subscribe('pms') warning: {e}")
            # Auth cache cross-instance invalidation. Without this, a
            # role change or module-flag toggle is honoured only on the
            # worker that processed it; other workers keep serving stale
            # values for up to 30 s (user) / 60 s (tenant).
            try:
                await auth_cache_pubsub.initialize(
                    redis_cluster.get_pubsub_client(),
                    instance_id,
                )
            except Exception as e:
                logger.warning(f"Auth cache pub/sub init warning: {e}")
            # KBS queue SSE bridge. Without this the desktop KBS agent
            # subscribed to ``GET /api/kbs/queue/stream`` on W1 would
            # never see jobs enqueued on W2 — the local-only fallback
            # keeps single-worker correctness.
            try:
                await kbs_queue_pubsub.initialize(
                    redis_cluster.get_pubsub_client(),
                    instance_id,
                )
            except Exception as e:
                logger.warning(f"KBS queue pub/sub init warning: {e}")
            from infra.horizontal_scaling import scaling_manager
            await scaling_manager.initialize(redis_cluster.get_client())
            logger.info(f"✅ Infrastructure Hardening initialized (Redis: {redis_cluster.mode})")
        else:
            # Redis unavailable: keep WS adapter in local-only mode so
            # `ws_redis_adapter.publish(...)` still fans out to clients
            # connected to this single instance.
            await ws_redis_adapter.initialize(
                None, "single-instance", local_handler=_ws_local_broadcast,
            )
            logger.info(
                "ℹ️ Infrastructure Hardening: Redis unavailable, "
                "WS adapter running in local-only mode"
            )
    except Exception as e:
        logger.warning(f"Infrastructure Hardening init warning: {e}")
        # Last-resort: even if redis_cluster import/connect threw, keep
        # local WS broadcasts working so chat features don't silently die.
        try:
            if not ws_redis_adapter._local_handler:  # type: ignore[attr-defined]
                await ws_redis_adapter.initialize(
                    None, "single-instance", local_handler=_ws_local_broadcast,
                )
        except Exception as inner:
            logger.error(f"WS adapter local-only fallback init failed: {inner}")

    # ── Cloud observability ─────────────────────────────────────────
    try:
        from infra.cloud_observability import otel_tracer, sentry_integration
        await otel_tracer.initialize()
        await sentry_integration.initialize()
        logger.info("✅ Cloud observability initialized")
    except Exception as e:
        logger.warning(f"Cloud observability init warning: {e}")

    # ── Production Go-Live validators ───────────────────────────────
    try:
        from infra.mongo_production import mongo_validator
        mongo_validator.set_db(_raw_db, client)
        from infra.security_checklist import security_checklist
        security_checklist.set_db(_raw_db)
        from infra.readiness_validator import readiness_validator
        readiness_validator.set_db(_raw_db)
        from infra.production_config import production_config
        startup_result = production_config.startup_check()
        logger.info(f"✅ Production Go-Live validators initialized (config: {startup_result['status']})")
    except RuntimeError:
        # v109 round-8 architect 4th-pass: production_config.startup_check()
        # raises RuntimeError on intentional fail-closed conditions (forbidden
        # leaked secrets, STRICT_TENANT_MODE missing in prod). These are
        # explicit go-live gates — re-raise so the process exits and ops sees
        # the abort instead of silently booting with insecure config.
        logger.error("❌ Production Go-Live validator REFUSED boot — see RuntimeError above")
        raise
    except Exception as e:
        logger.warning(f"Production Go-Live validators init warning: {e}")

    # ── ARI Push Engine ──────────────────────────────────────────────
    try:
        from domains.channel_manager.ari.adapters.exely_ari_adapter import ExelyARIAdapter
        from domains.channel_manager.ari.adapters.hotelrunner_ari_adapter import HotelRunnerARIAdapter
        from domains.channel_manager.ari.outbound_service import register_provider_adapter
        register_provider_adapter("hotelrunner", HotelRunnerARIAdapter())
        register_provider_adapter("exely", ExelyARIAdapter())
        # Create MongoDB indexes for ARI collections
        await _raw_db["ari_events"].create_index([("tenant_id", 1), ("property_id", 1), ("created_at", -1)])
        await _raw_db["ari_change_sets"].create_index([("tenant_id", 1), ("status", 1), ("created_at", 1)])
        await _raw_db["ari_change_sets"].create_index([("coalescing_key", 1), ("status", 1)])
        await _raw_db["ari_change_sets"].create_index([("provider", 1), ("property_id", 1), ("provider_delta_hash", 1)])
        await _raw_db["ari_outbound_logs"].create_index([("tenant_id", 1), ("property_id", 1), ("pushed_at", -1)])
        await _raw_db["ari_drift_state"].create_index([("tenant_id", 1), ("property_id", 1), ("provider", 1)])
        logger.info("✅ ARI Push Engine initialized (HotelRunner + Exely adapters)")
    except Exception as e:
        logger.warning(f"ARI Push Engine init warning: {e}")

    # ── Cache re-warm ───────────────────────────────────────────────
    try:
        from cache_warmer import initialize_cache_warmer
        await initialize_cache_warmer(_raw_db)
    except Exception:
        pass

    # ── Monitoring Worker ─────────────────────────────────────────────
    try:
        from domains.channel_manager.monitoring.monitoring_worker import start_monitoring_worker
        await start_monitoring_worker()
        logger.info("✅ Operational Monitoring worker started (60s interval)")
    except Exception as e:
        logger.warning(f"Monitoring worker init warning: {e}")

    # ── Exely Pull Scheduler (auto-start) ────────────────────────────
    try:
        active_exely = await _raw_db.exely_connections.find_one(
            {"is_active": True, "auto_sync_reservations": True}, {"_id": 1}
        )
        if active_exely:
            from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler
            _exely_int = int(os.getenv("SYROCE_EXELY_PULL_INTERVAL", "180"))
            await exely_pull_scheduler.start(interval_seconds=_exely_int)
            app.state.exely_pull_scheduler = exely_pull_scheduler
            logger.info(f"✅ Exely Pull Scheduler started ({_exely_int}s interval, auto-import enabled)")
        else:
            logger.info("ℹ️ No active Exely connections; pull scheduler not started")
    except Exception as e:
        logger.warning(f"Exely Pull Scheduler init warning: {e}")

    # ── HotelRunner Pull Scheduler (auto-start) ─────────────────────────
    try:
        active_hr = await _raw_db.hotelrunner_connections.find_one(
            {"is_active": True, "auto_sync_reservations": True}, {"_id": 1}
        )
        if active_hr:
            from domains.channel_manager.providers.hotelrunner_sync import pull_scheduler as hr_pull_scheduler
            _hr_int = int(os.getenv("SYROCE_HR_PULL_INTERVAL", "180"))
            await hr_pull_scheduler.start(interval_seconds=_hr_int)
            app.state.hr_pull_scheduler = hr_pull_scheduler
            logger.info(f"HotelRunner Pull Scheduler started ({_hr_int}s interval, adaptive backoff active)")
            # Also start push queue worker for automatic retry of failed pushes
            from domains.channel_manager.hr_push_queue_worker import push_queue_worker as hr_push_worker
            await hr_push_worker.start()
            app.state.hr_push_queue_worker = hr_push_worker
            logger.info("HotelRunner Push Queue Worker started (120s interval)")
        else:
            logger.info("No active HotelRunner connections; pull scheduler not started")
    except Exception as e:
        logger.warning(f"HotelRunner Pull Scheduler init warning: {e}")

    # ── Cockpit Snapshot Worker ────────────────────────────────────────
    try:
        from domains.channel_manager.cockpit_snapshot_worker import start_cockpit_worker
        tenant = await _raw_db.organizations.find_one({}, {"_id": 0, "id": 1})
        if tenant:
            start_cockpit_worker(tenant["id"], interval=3.0)
            logger.info("✅ Cockpit snapshot worker started (3s interval)")
    except Exception as e:
        logger.warning(f"Cockpit snapshot worker init warning: {e}")

    # ── NA-001/NA-002: Night Audit Hardening indexes ─────────────────
    try:
        from core.night_audit_hardened import ensure_night_audit_indexes
        await ensure_night_audit_indexes()
        logger.info("✅ Night audit hardening indexes ensured (NA-001/NA-002)")
    except Exception as e:
        logger.warning(f"Night audit hardening indexes error: {e}")

    # ── Night Audit Scheduler ─────────────────────────────────────────
    try:
        from domains.pms.night_audit.scheduler import start_scheduler
        start_scheduler()
        logger.info("✅ Night Audit Scheduler started (60s check interval, hardened)")
    except Exception as e:
        logger.warning(f"Night Audit Scheduler init warning: {e}")

    # ── Availability Reconciliation Worker ──────────────────────────────
    try:
        has_channels = await _raw_db.exely_connections.find_one(
            {"is_active": True}, {"_id": 1}
        ) or await _raw_db.hotelrunner_connections.find_one(
            {"is_active": True}, {"_id": 1}
        )
        if has_channels:
            from domains.channel_manager.availability_reconciliation_worker import availability_reconciliation_worker
            await availability_reconciliation_worker.start(interval_seconds=900)
            app.state.availability_reconciliation_worker = availability_reconciliation_worker
            logger.info("✅ Availability Reconciliation Worker started (15min interval)")
        else:
            logger.info("ℹ️ No active channel connections; reconciliation worker not started")
    except Exception as e:
        logger.warning(f"Availability Reconciliation Worker init warning: {e}")


async def on_shutdown(app):
    """Graceful shutdown: close connections and stop workers."""

    # Infrastructure cleanup
    try:
        from infra.horizontal_scaling import scaling_manager
        await scaling_manager.deregister()
        from infra.ws_redis_adapter import ws_redis_adapter
        await ws_redis_adapter.close()
        # Close auth-cache pubsub before tearing down the Redis client so
        # the listener task gets a clean cancel + UNSUBSCRIBE instead of
        # noisy connection-error tracebacks during shutdown.
        try:
            from infra.auth_cache_pubsub import auth_cache_pubsub
            await auth_cache_pubsub.close()
        except Exception as e:
            logger.warning(f"Auth cache pub/sub shutdown warning: {e}")
        try:
            from infra.kbs_queue_pubsub import kbs_queue_pubsub
            await kbs_queue_pubsub.close()
        except Exception as e:
            logger.warning(f"KBS queue pub/sub shutdown warning: {e}")
        from infra.redis_cluster import redis_cluster
        await redis_cluster.close()
    except Exception as e:
        logger.warning(f"Infrastructure shutdown warning: {e}")

    # Dashboard snapshot worker
    snapshot_worker = getattr(app.state, "dashboard_snapshot_worker", None)
    if snapshot_worker is not None:
        try:
            await snapshot_worker.stop()
        except Exception as e:
            logger.warning(f"Dashboard snapshot worker shutdown warning: {e}")

    # Room-Type Inventory worker (Phase C.1)
    inv_worker = getattr(app.state, "room_type_inventory_worker", None)
    if inv_worker is not None:
        try:
            await inv_worker.stop()
        except Exception as e:
            logger.warning(f"Room-type inventory worker shutdown warning: {e}")

    # Af-sadakat outbound dispatcher
    afs_task = getattr(app.state, "afsadakat_dispatcher_task", None)
    if afs_task is not None and not afs_task.done():
        try:
            afs_task.cancel()
            try:
                await afs_task
            except (Exception, BaseException):
                pass
        except Exception as e:
            logger.warning(f"Af-sadakat dispatcher shutdown warning: {e}")

    # OTA-002: Stop production outbox worker
    ota_worker = getattr(app.state, "outbox_ota_worker", None)
    if ota_worker is not None:
        try:
            await ota_worker.stop()
        except Exception as e:
            logger.warning(f"OTA Outbox Worker shutdown warning: {e}")

    # DATA-001: Stop import retry worker
    import_worker = getattr(app.state, "import_retry_worker", None)
    if import_worker is not None:
        try:
            await import_worker.stop()
        except Exception as e:
            logger.warning(f"Import Retry Worker shutdown warning: {e}")

    # Outbox lifecycle worker
    worker = getattr(app.state, "outbox_lifecycle_worker", None)
    if worker is not None:
        try:
            await worker.stop()
        except Exception as e:
            logger.warning(f"Outbox lifecycle worker shutdown warning: {e}")

    # Monitoring worker
    try:
        from domains.channel_manager.monitoring.monitoring_worker import stop_monitoring_worker
        await stop_monitoring_worker()
    except Exception as e:
        logger.warning(f"Monitoring worker shutdown warning: {e}")

    # Cockpit snapshot worker
    try:
        from domains.channel_manager.cockpit_snapshot_worker import stop_cockpit_worker
        stop_cockpit_worker()
    except Exception as e:
        logger.warning(f"Cockpit snapshot worker shutdown warning: {e}")

    # Exely Pull Scheduler
    scheduler = getattr(app.state, "exely_pull_scheduler", None)
    if scheduler is not None:
        try:
            await scheduler.stop()
        except Exception as e:
            logger.warning(f"Exely Pull Scheduler shutdown warning: {e}")

    # HotelRunner Pull Scheduler
    hr_scheduler = getattr(app.state, "hr_pull_scheduler", None)
    if hr_scheduler is not None:
        try:
            await hr_scheduler.stop()
        except Exception as e:
            logger.warning(f"HotelRunner Pull Scheduler shutdown warning: {e}")

    # HotelRunner Push Queue Worker
    hr_push = getattr(app.state, "hr_push_queue_worker", None)
    if hr_push is not None:
        try:
            await hr_push.stop()
        except Exception as e:
            logger.warning(f"HotelRunner Push Queue Worker shutdown warning: {e}")

    # Night Audit Scheduler
    try:
        from domains.pms.night_audit.scheduler import stop_scheduler
        stop_scheduler()
    except Exception as e:
        logger.warning(f"Night Audit Scheduler shutdown warning: {e}")

    # Availability Reconciliation Worker
    recon_worker = getattr(app.state, "availability_reconciliation_worker", None)
    if recon_worker is not None:
        try:
            await recon_worker.stop()
        except Exception as e:
            logger.warning(f"Availability Reconciliation Worker shutdown warning: {e}")

    # Close MongoDB client
    client.close()


async def _ensure_performance_indexes():
    """PERF-001: Create compound indexes for hot query patterns."""
    indexes = [
        # Bookings: availability check, calendar, status queries
        ("bookings", [("tenant_id", 1), ("status", 1), ("check_in", 1)], "idx_booking_status_checkin", {}),
        ("bookings", [("tenant_id", 1), ("room_id", 1), ("check_in", 1), ("check_out", 1)], "idx_booking_room_dates", {}),
        ("bookings", [("tenant_id", 1), ("guest_id", 1), ("status", 1)], "idx_booking_guest_status", {}),
        ("bookings", [("tenant_id", 1), ("created_at", -1)], "idx_booking_created", {}),
        # Rooms: listing, availability
        ("rooms", [("tenant_id", 1), ("is_active", 1), ("room_type", 1)], "idx_room_type_active", {}),
        ("rooms", [("tenant_id", 1), ("status", 1)], "idx_room_status", {}),
        # Folios: lookup by booking
        ("folios", [("tenant_id", 1), ("booking_id", 1), ("status", 1)], "idx_folio_booking_status", {}),
        # Folio charges
        ("folio_charges", [("folio_id", 1), ("tenant_id", 1), ("voided", 1)], "idx_charge_folio", {}),
        # Payments
        ("payments", [("folio_id", 1), ("tenant_id", 1), ("voided", 1)], "idx_payment_folio", {}),
        # Guests: search
        ("guests", [("tenant_id", 1), ("name", 1)], "idx_guest_name", {}),
        # Outbox events: processing queue
        ("outbox_events", [("status", 1), ("event_type", 1), ("created_at", 1)], "idx_outbox_queue", {}),
        # Housekeeping
        ("housekeeping_tasks", [("tenant_id", 1), ("status", 1), ("room_id", 1)], "idx_hk_status_room", {}),
        # Audit trail
        ("pms_audit_trail", [("tenant_id", 1), ("entity_id", 1), ("timestamp", -1)], "idx_audit_entity", {}),
    ]
    for coll_name, keys, name, kwargs in indexes:
        try:
            await _raw_db[coll_name].create_index(keys, name=name, background=True, **kwargs)
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning(f"Index {name} on {coll_name} failed: {e}")
