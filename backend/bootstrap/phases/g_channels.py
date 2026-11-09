"""Phase G — Channels (ARI/Exely/HR), monitoring, night audit, recon."""

import logging
import os

from core.database import _raw_db

logger = logging.getLogger(__name__)

EXELY_PULL_SUPERVISOR_MAX_TICK_SECONDS = 60


async def _start_exely_pull_supervisor(app):
    """Keep an idle supervisor ready for tenants that opt in after startup.

    The worker selects only active, explicitly enabled connections on every
    tick and acquires their distributed interval leases. A startup snapshot of
    opted-in tenants must not decide whether later tenant controls can work.
    The global safety gate still prevents starting the worker at all.
    """
    from domains.channel_manager.providers.exely.production_safety import reservation_sync_block_reason

    block = reservation_sync_block_reason()
    if block:
        logger.warning("Exely Pull Scheduler blocked reason=%s", block)
        return False

    from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler

    # A 180-second supervisor tick makes a five-minute tenant lease due
    # only on the sixth minute. Cap the scan interval, not the tenant lease:
    # the distributed lock still decides when the next provider read can run.
    configured_interval = int(os.getenv("SYROCE_EXELY_PULL_INTERVAL", str(EXELY_PULL_SUPERVISOR_MAX_TICK_SECONDS)))
    interval = max(1, min(configured_interval, EXELY_PULL_SUPERVISOR_MAX_TICK_SECONDS))
    started = await exely_pull_scheduler.start(interval_seconds=interval)
    if started:
        app.state.exely_pull_scheduler = exely_pull_scheduler
        logger.info("Exely Pull Scheduler supervisor started (%ss tick; enabled tenants only)", interval)
    return started


async def phase_g_channels_and_audit(app):
    # Historical HotelRunner imports may contain rooms[].price (before tax)
    # while reservation reads are deliberately disabled in production. Repair
    # only that exact legacy signature from the immutable local event store;
    # this performs no provider I/O and is safe to repeat across replicas.
    try:
        from domains.channel_manager.ingest.hotelrunner_total_repair import (
            reconcile_hotelrunner_guest_totals_from_local_events,
        )

        repaired_totals = await reconcile_hotelrunner_guest_totals_from_local_events(_raw_db)
        if repaired_totals:
            logger.info(
                "HotelRunner stored reservation totals repaired count=%d",
                repaired_totals,
            )
    except Exception as e:
        logger.warning(
            "HotelRunner local total reconciliation warning exception_class=%s",
            type(e).__name__,
        )

    # ARI Push Engine
    try:
        from domains.channel_manager.ari.adapters.exely_ari_adapter import ExelyARIAdapter
        from domains.channel_manager.ari.adapters.hotelrunner_ari_adapter import HotelRunnerARIAdapter
        from domains.channel_manager.ari.outbound_service import register_provider_adapter
        from domains.channel_manager.ari.repositories import ensure_current_ack_index

        register_provider_adapter("hotelrunner", HotelRunnerARIAdapter())
        register_provider_adapter("exely", ExelyARIAdapter())
        await _raw_db["ari_events"].create_index([("tenant_id", 1), ("property_id", 1), ("created_at", -1)])
        await _raw_db["ari_change_sets"].create_index([("tenant_id", 1), ("status", 1), ("created_at", 1)])
        await _raw_db["ari_change_sets"].create_index([("coalescing_key", 1), ("status", 1)])
        await _raw_db["ari_change_sets"].create_index([("provider", 1), ("property_id", 1), ("provider_delta_hash", 1)])
        await ensure_current_ack_index(_raw_db)
        await _raw_db["ari_outbound_logs"].create_index([("tenant_id", 1), ("property_id", 1), ("pushed_at", -1)])
        await _raw_db["ari_drift_state"].create_index([("tenant_id", 1), ("property_id", 1), ("provider", 1)])
        await _raw_db["hotelrunner_ari_deliveries"].create_index([("tenant_id", 1), ("state", 1), ("created_at", 1)])
        await _raw_db["exely_ari_deliveries"].create_index(
            [("operation_identity", 1)],
            unique=True,
            name="uq_exely_ari_operation_identity",
        )
        await _raw_db["exely_ari_deliveries"].create_index(
            [("active_fingerprint", 1)],
            unique=True,
            partialFilterExpression={"active_fingerprint": {"$type": "string"}},
            name="uq_exely_ari_unconfirmed_fingerprint",
        )
        await _raw_db["exely_ari_deliveries"].create_index(
            [("tenant_id", 1), ("state", 1), ("created_at", 1)],
            name="ix_exely_ari_reconciliation",
        )
        await _raw_db["exely_ari_deliveries"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("created_at", -1), ("_id", -1)],
            partialFilterExpression={"rate_periods": {"$exists": True}},
            name="ix_exely_rate_receipts",
        )
        await _raw_db["exely_scheduler_leases"].create_index(
            [("tenant_id", 1)],
            unique=True,
            name="uq_exely_scheduler_lease_tenant",
        )
        from workers.ari_push_worker import start_push_worker

        await start_push_worker()
        logger.info("✅ ARI Push Engine initialized (HotelRunner + Exely adapters)")
    except Exception as e:
        logger.error("ARI Push Engine initialization failed: %s", type(e).__name__)
        raise

    # Cache re-warm
    try:
        from cache_warmer import initialize_cache_warmer

        await initialize_cache_warmer(_raw_db)
    except Exception:
        pass

    # Monitoring Worker
    try:
        from domains.channel_manager.monitoring.monitoring_worker import start_monitoring_worker

        await start_monitoring_worker()
        logger.info("✅ Operational Monitoring worker started (60s interval)")
    except Exception as e:
        logger.warning(f"Monitoring worker init warning: {e}")

    # Exely Pull Scheduler (auto-start)
    try:
        await _start_exely_pull_supervisor(app)
    except Exception as e:
        logger.warning("Exely Pull Scheduler init warning exception_class=%s", type(e).__name__)

    # HotelRunner Pull Scheduler (auto-start)
    try:
        from domains.channel_manager.providers.hotelrunner.production_safety import (
            ari_write_block_reason as hotelrunner_ari_block_reason,
        )
        from domains.channel_manager.providers.hotelrunner.production_safety import (
            reservation_sync_block_reason as hotelrunner_reservation_block_reason,
        )

        reservation_block = hotelrunner_reservation_block_reason()
        ari_block = hotelrunner_ari_block_reason()
        active_hr = None
        if not reservation_block or not ari_block:
            active_hr = await _raw_db.hotelrunner_connections.find_one(
                {"is_active": True, "auto_sync_reservations": True},
                {"_id": 1},
            )
        if active_hr:
            if reservation_block:
                logger.warning("HotelRunner Pull Scheduler blocked reason=%s", reservation_block)
            else:
                from domains.channel_manager.providers.hotelrunner_sync import pull_scheduler as hr_pull_scheduler

                _hr_int = int(os.getenv("SYROCE_HR_PULL_INTERVAL", "180"))
                started = await hr_pull_scheduler.start(interval_seconds=_hr_int)
                if started:
                    app.state.hr_pull_scheduler = hr_pull_scheduler
                    logger.info(f"HotelRunner Pull Scheduler started ({_hr_int}s interval, adaptive backoff active)")
            if ari_block:
                logger.warning("HotelRunner Push Queue Worker blocked reason=%s", ari_block)
            else:
                from domains.channel_manager.hr_push_queue_worker import push_queue_worker as hr_push_worker

                started = await hr_push_worker.start()
                if started:
                    app.state.hr_push_queue_worker = hr_push_worker
                    logger.info("HotelRunner Push Queue Worker started (120s interval)")
        elif reservation_block or ari_block:
            logger.warning(
                "HotelRunner background workers blocked reservation_reason=%s ari_reason=%s",
                reservation_block or "NONE",
                ari_block or "NONE",
            )
        else:
            logger.info("No active HotelRunner connections; pull scheduler not started")
    except Exception as e:
        logger.warning(f"HotelRunner Pull Scheduler init warning: {e}")

    # Cockpit Snapshot Worker
    try:
        from domains.channel_manager.cockpit_snapshot_worker import start_cockpit_worker

        tenant = await _raw_db.organizations.find_one({}, {"_id": 0, "id": 1})
        if tenant:
            start_cockpit_worker(tenant["id"], interval=3.0)
            logger.info("✅ Cockpit snapshot worker started (3s interval)")
    except Exception as e:
        logger.warning(f"Cockpit snapshot worker init warning: {e}")

    # NA-001/NA-002: Night Audit Hardening indexes
    try:
        from core.night_audit_hardened import ensure_night_audit_indexes

        await ensure_night_audit_indexes()
        logger.info("✅ Night audit hardening indexes ensured (NA-001/NA-002)")
    except Exception as e:
        logger.warning(f"Night audit hardening indexes error: {e}")

    # Night Audit Scheduler — Task #362: retired. The in-process asyncio loop is
    # replaced by the per-tenant Celery flow (celery_tasks.night_audit_dispatch_task
    # beat + night_audit_for_tenant worker task). Starting it here would
    # double-trigger audits, so it is intentionally not started anymore.

    # Web Push abonelik temizlik worker'ı
    try:
        from domains.guest.messaging.web_push_cleanup import (
            start_web_push_cleanup_worker,
        )

        start_web_push_cleanup_worker()
        logger.info("✅ Web Push cleanup worker started")
    except Exception as e:
        logger.warning(f"Web Push cleanup worker init warning: {e}")

    # Task #72 — Online check-in kimlik fotoğrafları temizlik worker'ı
    try:
        from domains.guest.checkin_id_photo_cleanup import (
            start_checkin_id_photo_cleanup_worker,
        )

        start_checkin_id_photo_cleanup_worker()
        logger.info("✅ Check-in ID photo cleanup worker started")
    except Exception as e:
        logger.warning(f"Check-in ID photo cleanup worker init warning: {e}")

    # CapX Availability Scheduler (Faz 2: periodic snapshot push)
    try:
        from integrations.capx import availability_scheduler as capx_avail_sched
        from integrations.capx import get_capx_client

        env_ok = get_capx_client(refresh=True).configured
        tenant_ok = bool(await _raw_db["capx_tenant_credentials"].find_one({}, {"_id": 1}))
        if env_ok or tenant_ok:
            _capx_int = int(os.getenv("CAPX_AVAIL_INTERVAL", "900"))
            _capx_lookahead = int(os.getenv("CAPX_AVAIL_LOOKAHEAD_DAYS", "30"))
            await capx_avail_sched.start(
                interval_seconds=_capx_int,
                lookahead_days=_capx_lookahead,
            )
            app.state.capx_availability_scheduler = capx_avail_sched
            logger.info(f"✅ CapX availability scheduler started ({_capx_int}s, lookahead={_capx_lookahead}d, source={'env' if env_ok else 'tenant'})")
        else:
            logger.info("ℹ️ CapX not configured (env+tenant boş); availability scheduler not started")
    except Exception as e:
        logger.warning(f"CapX Availability Scheduler init warning: {e}")

    # Availability Reconciliation Worker
    try:
        has_channels = await _raw_db.exely_connections.find_one({"is_active": True}, {"_id": 1}) or await _raw_db.hotelrunner_connections.find_one({"is_active": True}, {"_id": 1})
        if has_channels:
            from domains.channel_manager.availability_reconciliation_worker import availability_reconciliation_worker

            await availability_reconciliation_worker.start(interval_seconds=900)
            app.state.availability_reconciliation_worker = availability_reconciliation_worker
            logger.info("✅ Availability Reconciliation Worker started (15min interval)")
        else:
            logger.info("ℹ️ No active channel connections; reconciliation worker not started")
    except Exception as e:
        logger.warning(f"Availability Reconciliation Worker init warning: {e}")
