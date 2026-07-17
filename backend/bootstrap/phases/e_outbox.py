"""Phase E — Outbox + Event Bus + Persistence."""

import logging

from core.database import _raw_db

logger = logging.getLogger(__name__)


async def phase_e_outbox_and_eventbus(app):
    # OTA-002: Outbox Pattern indexes
    try:
        from core.outbox_service import ensure_outbox_indexes

        await ensure_outbox_indexes(_raw_db)
        logger.info("Outbox pattern indexes ensured (OTA-002)")
    except Exception as e:
        logger.warning(f"Outbox index creation error: {e}")

    # OTA-002: Start production outbox worker
    try:
        from core.outbox_worker import outbox_ota_worker

        await outbox_ota_worker.start()
        app.state.outbox_ota_worker = outbox_ota_worker
        logger.info("OTA Outbox Worker started (guaranteed delivery)")
    except Exception as e:
        logger.warning(f"OTA Outbox Worker startup warning: {e}")

    # DATA-001: Import bridge indexes + worker
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

    # Legacy outbox lifecycle worker
    try:
        from shared_kernel.outbox_lifecycle import outbox_lifecycle_worker

        await outbox_lifecycle_worker.start()
        app.state.outbox_lifecycle_worker = outbox_lifecycle_worker
        logger.info("Legacy outbox lifecycle worker started")
    except Exception as e:
        logger.warning(f"Outbox lifecycle worker startup warning: {e}")

    # Af-sadakat outbound dispatcher loop
    try:
        import asyncio as _asyncio_afs

        from core.afsadakat_outbound import dispatch_pending_loop as _afs_loop

        app.state.afsadakat_dispatcher_task = _asyncio_afs.create_task(_afs_loop(), name="afsadakat-outbound-dispatcher")
        logger.info("✅ Af-sadakat outbound dispatcher started")
    except Exception as e:
        logger.warning(f"Af-sadakat outbound dispatcher warning: {e}")

    # Nilvera Dispatch Worker
    try:
        from core.integrations.invoice_dispatch_worker import invoice_dispatch_worker

        await invoice_dispatch_worker.start()
        app.state.invoice_dispatch_worker = invoice_dispatch_worker
        logger.info("✅ Nilvera Invoice Dispatch Worker started")
    except Exception as e:
        logger.error(f"❌ Nilvera Invoice Dispatch Worker failed to start: {e}. Application running in DEGRADED mode for this worker.")

    # Nilvera Status Worker
    try:
        from core.integrations.invoice_status_worker import invoice_status_worker

        await invoice_status_worker.start()
        app.state.invoice_status_worker = invoice_status_worker
        logger.info("✅ Nilvera Invoice Status Worker started")
    except Exception as e:
        logger.error(f"❌ Nilvera Invoice Status Worker failed to start: {e}. Application running in DEGRADED mode for this worker.")

    # Nilvera Invoice Lifecycle Worker
    try:
        from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker

        invoice_lifecycle_worker = InvoiceLifecycleWorker()
        invoice_lifecycle_worker.start()
        app.state.invoice_lifecycle_worker = invoice_lifecycle_worker
        logger.info("✅ Nilvera Invoice Lifecycle Worker started")
    except Exception as e:
        logger.error(f"❌ Nilvera Invoice Lifecycle Worker failed to start: {e}. Application running in DEGRADED mode for this worker.")

    # Channel Manager v2 indexes
    try:
        from channel_manager.infrastructure.indexes import create_cm_indexes

        await create_cm_indexes()
        logger.info("✅ Channel Manager v2 indexes created")
    except Exception as e:
        logger.warning(f"Channel Manager v2 indexes warning: {e}")

    # Event Bus
    try:
        from modules.event_bus.abstraction import event_bus

        await event_bus.initialize()
        logger.info(f"✅ Event Bus initialized in {event_bus.mode.upper()} mode")
    except Exception as e:
        logger.warning(f"Event Bus initialization warning: {e}")

    # Persistence indexes
    try:
        from modules.persistence_repositories import ensure_all_indexes

        await ensure_all_indexes()
        logger.info("✅ Persistence repository indexes ensured")
    except Exception as e:
        logger.warning(f"Persistence indexes warning: {e}")
