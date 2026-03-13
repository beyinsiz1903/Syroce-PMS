"""
startup.py — Application Lifecycle Handlers

Startup and shutdown events for the FastAPI application.
Called by server.py during bootstrap orchestration.
"""
import logging

from core.database import db, client

logger = logging.getLogger(__name__)


async def on_startup(app):
    """Run all startup initialization tasks."""

    # Expose db via app.state for health checks
    app.state.db = db

    # ── Auto-seed demo data ─────────────────────────────────────────
    try:
        from auto_seed import auto_seed_if_empty
        await auto_seed_if_empty(db)
    except Exception as e:
        logger.warning(f"Auto-seed error: {e}")

    # ── Agency booking indexes ──────────────────────────────────────
    try:
        col = db.agency_booking_requests
        await col.create_index([("idempotency_key", 1)], unique=True, name="uniq_idempotency_key")
        await col.create_index([("status", 1), ("hotel_id", 1)], name="idx_status_hotel")
        await col.create_index([("agency_id", 1), ("status", 1)], name="idx_agency_status")
        await col.create_index([("expires_at", 1)], name="idx_expires_at")
        await col.create_index([("created_at", -1)], name="idx_created_at_desc")
        print("✅ Agency booking request indexes created")
    except Exception as e:
        logger.warning(f"Agency booking request indexes error: {e}")

    # ── Redis cache (best-effort) ───────────────────────────────────
    try:
        print("🚀 Initializing Redis ultra-fast cache...")
        from redis_cache import init_redis_cache
        init_redis_cache()
        print("✅ Redis cache initialized!")
    except Exception as e:
        logger.warning(f"Redis cache initialization: {e}")

    # ── Cache warmer ────────────────────────────────────────────────
    try:
        print("🔥 Initializing ultra-fast cache warmer...")
        from cache_warmer import initialize_cache_warmer
        await initialize_cache_warmer(db)
        print("✅ Cache warmer initialized - responses will be instant!")
    except Exception as e:
        logger.warning(f"Cache warmer initialization: {e}")

    # ── Optimization systems ────────────────────────────────────────
    try:
        print("🚀 Initializing enterprise optimization systems...")
        any_rms_enabled = await db.organizations.find_one(
            {"$or": [{"plan": "enterprise"}, {"subscription_tier": "enterprise"}, {"features.hidden_rms": True}]},
            {"_id": 1},
        )
        if not any_rms_enabled:
            print("ℹ️ No orgs with RMS enabled; skipping optimization init")
        else:
            import redis
            from optimization_endpoints import init_optimization_managers
            redis_client = redis.Redis(host="127.0.0.1", port=6379, db=0, socket_connect_timeout=2, decode_responses=False)
            redis_client.ping()
            init_optimization_managers(db, redis_client)
            from optimization_endpoints import archival_manager, materialized_views_manager
            if archival_manager:
                await archival_manager.setup_indexes()
            if materialized_views_manager:
                await materialized_views_manager.setup_indexes()
                await materialized_views_manager.refresh_dashboard_metrics()
            print("🎉 Enterprise optimization systems ready!")
    except Exception as e:
        logger.warning(f"Optimization system initialization error: {e}")

    # ── Channel Manager 9-collection indexes ───────────────────────
    try:
        from domains.channel_manager.unified_repository import ensure_indexes
        await ensure_indexes()
        print("✅ Channel Manager 9-collection indexes created")
    except Exception as e:
        logger.warning(f"CM 9-collection indexes error: {e}")

    # ── Database optimization ───────────────────────────────────────
    try:
        print("🚀 Running comprehensive database optimization...")
        from database_optimizer import DatabaseOptimizer
        db_optimizer = DatabaseOptimizer(db)
        opt_result = await db_optimizer.create_all_indexes()
        total_idx = sum(r.get("created", 0) for r in opt_result.values() if isinstance(r, dict) and "created" in r)
        print(f"✅ Database optimization complete: {total_idx} indexes ensured")
    except Exception as e:
        logger.warning(f"Database optimization warning: {e}")

    # ── Performance indexes ─────────────────────────────────────────
    try:
        print("🚀 Creating performance indexes for large-scale operations...")
        await db.bookings.create_index([("tenant_id", 1), ("check_in", 1), ("check_out", 1)], name="idx_bookings_tenant_checkin_checkout")
        await db.bookings.create_index([("tenant_id", 1), ("status", 1), ("check_in", 1)], name="idx_bookings_tenant_status_checkin")
        await db.bookings.create_index([("tenant_id", 1), ("room_id", 1), ("check_in", 1)], name="idx_bookings_tenant_room_checkin")
        await db.rooms.create_index([("tenant_id", 1), ("room_number", 1)], name="idx_rooms_tenant_number", unique=True)
        await db.rooms.create_index([("tenant_id", 1), ("status", 1), ("room_type", 1)], name="idx_rooms_tenant_status_type")
        await db.guests.create_index([("tenant_id", 1), ("email", 1)], name="idx_guests_tenant_email")
        await db.guests.create_index([("tenant_id", 1), ("phone", 1)], name="idx_guests_tenant_phone")
        await db.folios.create_index([("tenant_id", 1), ("booking_id", 1)], name="idx_folios_tenant_booking")
        await db.folios.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="idx_folios_tenant_status_created")
        print("✅ Performance indexes created successfully!")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

    # ── Outbox lifecycle worker ─────────────────────────────────────
    try:
        from shared_kernel.outbox_lifecycle import outbox_lifecycle_worker
        await outbox_lifecycle_worker.start()
        app.state.outbox_lifecycle_worker = outbox_lifecycle_worker
        print("✅ Temporary operational outbox worker started")
    except Exception as e:
        logger.warning(f"Outbox lifecycle worker startup warning: {e}")

    # ── Channel Manager v2 indexes ──────────────────────────────────
    try:
        from channel_manager.infrastructure.indexes import create_cm_indexes
        await create_cm_indexes()
        print("✅ Channel Manager v2 indexes created")
    except Exception as e:
        logger.warning(f"Channel Manager v2 indexes warning: {e}")

    # ── Event Bus ───────────────────────────────────────────────────
    try:
        from modules.event_bus.abstraction import event_bus
        await event_bus.initialize()
        print(f"✅ Event Bus initialized in {event_bus.mode.upper()} mode")
    except Exception as e:
        logger.warning(f"Event Bus initialization warning: {e}")

    # ── Persistence indexes ─────────────────────────────────────────
    try:
        from modules.persistence_repositories import ensure_all_indexes
        await ensure_all_indexes()
        print("✅ Persistence repository indexes ensured")
    except Exception as e:
        logger.warning(f"Persistence indexes warning: {e}")

    # ── Infrastructure Hardening ────────────────────────────────────
    try:
        from infra.redis_cluster import redis_cluster
        connected = await redis_cluster.connect()
        if connected:
            from infra.distributed_lock import lock_manager
            lock_manager.set_redis(redis_cluster.get_lock_client())
            from infra.ws_redis_adapter import ws_redis_adapter
            await ws_redis_adapter.initialize(
                redis_cluster.get_pubsub_client(),
                redis_cluster.instance_id if hasattr(redis_cluster, "instance_id") else "main",
            )
            from infra.horizontal_scaling import scaling_manager
            await scaling_manager.initialize(redis_cluster.get_client())
            print(f"✅ Infrastructure Hardening initialized (Redis: {redis_cluster.mode})")
        else:
            print("ℹ️ Infrastructure Hardening: Redis unavailable, using fallback modes")
    except Exception as e:
        logger.warning(f"Infrastructure Hardening init warning: {e}")

    # ── Cloud observability ─────────────────────────────────────────
    try:
        from infra.cloud_observability import otel_tracer, sentry_integration
        await otel_tracer.initialize()
        await sentry_integration.initialize()
        print("✅ Cloud observability initialized")
    except Exception as e:
        logger.warning(f"Cloud observability init warning: {e}")

    # ── Production Go-Live validators ───────────────────────────────
    try:
        from infra.mongo_production import mongo_validator
        mongo_validator.set_db(db, client)
        from infra.security_checklist import security_checklist
        security_checklist.set_db(db)
        from infra.readiness_validator import readiness_validator
        readiness_validator.set_db(db)
        from infra.production_config import production_config
        startup_result = production_config.startup_check()
        print(f"✅ Production Go-Live validators initialized (config: {startup_result['status']})")
    except Exception as e:
        logger.warning(f"Production Go-Live validators init warning: {e}")

    # ── ARI Push Engine ──────────────────────────────────────────────
    try:
        from domains.channel_manager.ari.outbound_service import register_provider_adapter
        from domains.channel_manager.ari.adapters.hotelrunner_ari_adapter import HotelRunnerARIAdapter
        from domains.channel_manager.ari.adapters.exely_ari_adapter import ExelyARIAdapter
        register_provider_adapter("hotelrunner", HotelRunnerARIAdapter())
        register_provider_adapter("exely", ExelyARIAdapter())
        # Create MongoDB indexes for ARI collections
        await db["ari_events"].create_index([("tenant_id", 1), ("property_id", 1), ("created_at", -1)])
        await db["ari_change_sets"].create_index([("tenant_id", 1), ("status", 1), ("created_at", 1)])
        await db["ari_change_sets"].create_index([("coalescing_key", 1), ("status", 1)])
        await db["ari_change_sets"].create_index([("provider", 1), ("property_id", 1), ("provider_delta_hash", 1)])
        await db["ari_outbound_logs"].create_index([("tenant_id", 1), ("property_id", 1), ("pushed_at", -1)])
        await db["ari_drift_state"].create_index([("tenant_id", 1), ("property_id", 1), ("provider", 1)])
        print("✅ ARI Push Engine initialized (HotelRunner + Exely adapters)")
    except Exception as e:
        logger.warning(f"ARI Push Engine init warning: {e}")

    # ── Cache re-warm ───────────────────────────────────────────────
    try:
        from cache_warmer import initialize_cache_warmer
        await initialize_cache_warmer(db)
    except Exception:
        pass


async def on_shutdown(app):
    """Graceful shutdown: close connections and stop workers."""

    # Infrastructure cleanup
    try:
        from infra.horizontal_scaling import scaling_manager
        await scaling_manager.deregister()
        from infra.ws_redis_adapter import ws_redis_adapter
        await ws_redis_adapter.close()
        from infra.redis_cluster import redis_cluster
        await redis_cluster.close()
    except Exception as e:
        logger.warning(f"Infrastructure shutdown warning: {e}")

    # Outbox lifecycle worker
    worker = getattr(app.state, "outbox_lifecycle_worker", None)
    if worker is not None:
        try:
            await worker.stop()
        except Exception as e:
            logger.warning(f"Outbox lifecycle worker shutdown warning: {e}")

    # Close MongoDB client
    client.close()
