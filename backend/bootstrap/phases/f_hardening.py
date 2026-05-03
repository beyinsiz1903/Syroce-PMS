"""Phase F — Infra hardening (Redis/WS/auth/kbs/scaling) + observability + prod validators."""
import logging

from core.database import _raw_db, client

logger = logging.getLogger(__name__)


async def phase_f_hardening_and_observability(app):
    from infra.auth_cache_pubsub import auth_cache_pubsub
    from infra.kbs_queue_pubsub import kbs_queue_pubsub
    from infra.ws_redis_adapter import ws_redis_adapter
    from websocket_server import local_broadcast as _ws_local_broadcast

    try:
        from infra.redis_cluster import redis_cluster
        connected = await redis_cluster.connect()
        if connected:
            from infra.distributed_lock import lock_manager
            lock_manager.set_redis(redis_cluster.get_lock_client())
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
            try:
                await ws_redis_adapter.subscribe("pms")
            except Exception as e:
                logger.warning(f"WS Redis subscribe('pms') warning: {e}")
            try:
                await auth_cache_pubsub.initialize(
                    redis_cluster.get_pubsub_client(),
                    instance_id,
                )
            except Exception as e:
                logger.warning(f"Auth cache pub/sub init warning: {e}")
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
            await ws_redis_adapter.initialize(
                None, "single-instance", local_handler=_ws_local_broadcast,
            )
            logger.info(
                "ℹ️ Infrastructure Hardening: Redis unavailable, "
                "WS adapter running in local-only mode"
            )
    except Exception as e:
        logger.warning(f"Infrastructure Hardening init warning: {e}")
        try:
            if not ws_redis_adapter._local_handler:  # type: ignore[attr-defined]
                await ws_redis_adapter.initialize(
                    None, "single-instance", local_handler=_ws_local_broadcast,
                )
        except Exception as inner:
            logger.error(f"WS adapter local-only fallback init failed: {inner}")

    # Cloud observability
    try:
        from infra.cloud_observability import otel_tracer, sentry_integration
        await otel_tracer.initialize()
        await sentry_integration.initialize()
        logger.info("✅ Cloud observability initialized")
    except Exception as e:
        logger.warning(f"Cloud observability init warning: {e}")

    # Production Go-Live validators
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
        logger.error("❌ Production Go-Live validator REFUSED boot — see RuntimeError above")
        raise
    except Exception as e:
        logger.warning(f"Production Go-Live validators init warning: {e}")
