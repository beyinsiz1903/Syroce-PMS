"""Phase C — Domain indexes + early workers + R5 audit indexes."""
import logging

logger = logging.getLogger(__name__)


async def phase_c_domain_indexes_and_workers(app):
    # Booking overbooking prevention indexes
    try:
        from core.atomic_booking import ensure_booking_indexes
        await ensure_booking_indexes()
        logger.info("Booking overlap prevention indexes ensured")
    except Exception as e:
        logger.warning(f"Booking index creation error: {e}")

    # Room-Type Inventory indexes + worker (ADR-003, Phase C.1)
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

    # Booking hold sweeper (TTL auto-release)
    try:
        from core.booking_hold_service import start_hold_sweeper
        start_hold_sweeper()
        logger.info("Booking hold sweeper started")
    except Exception as e:
        logger.warning(f"Booking hold sweeper start error: {e}")

    # Mailing automation worker
    try:
        from workers.mailing_automation import start as start_mailing_automation
        start_mailing_automation()
        logger.info("Mailing automation worker started (600s interval)")
    except Exception as e:
        logger.warning(f"Mailing automation worker start error: {e}")

    # Marketplace subscription expiry worker (saatlik)
    try:
        import asyncio as _asyncio

        from workers.subscription_expiry import run_loop as _sub_loop
        _asyncio.create_task(_sub_loop(3600), name="subscription-expiry")
        logger.info("Subscription expiry worker started (3600s interval)")
    except Exception as e:
        logger.warning(f"Subscription expiry worker start error: {e}")

    # Task #105 — KVKK kimlik fotoğrafı görüntüleme uyarı işçisi.
    # Resepsiyonun tek vardiyada olağandışı sayıda kimlik fotoğrafı
    # açması durumunda yöneticiye yüksek-öncelikli audit + bildirim
    # gönderir. Eşik/pencere `kvkk_id_photo_alert_config` ile kiracı
    # bazında özelleştirilebilir.
    try:
        import asyncio as _asyncio

        from workers.id_photo_view_alert import (
            DEFAULT_INTERVAL_SECONDS as _IDP_INTERVAL,
        )
        from workers.id_photo_view_alert import (
            run_loop as _idp_loop,
        )
        _asyncio.create_task(
            _idp_loop(_IDP_INTERVAL), name="kvkk-id-photo-alert"
        )
        logger.info(
            "KVKK ID photo view alert worker started (%ss interval)",
            _IDP_INTERVAL,
        )
    except Exception as e:
        logger.warning(f"KVKK ID photo view alert worker start error: {e}")

    # V3 — Syroce mobil push scheduler (VIP arrivals + no-show risk).
    # Polling endpoints already surface these but only while the app is
    # open; this worker fans them out as real OS-level push notifications.
    try:
        from workers.mobile_push_scheduler import start as _start_mobile_push
        if _start_mobile_push():
            logger.info("Mobile push scheduler started (VIP + no-show)")
    except Exception as e:
        logger.warning(f"Mobile push scheduler start error: {e}")

    # TGA Tesis Entegrasyon scheduler — son 7 günü periyodik gönderir.
    try:
        from core.tga_outbound import ensure_indexes as _tga_indexes
        await _tga_indexes()
        from workers.tga_scheduler import start as _start_tga
        if _start_tga():
            logger.info("TGA scheduler started")
    except Exception as e:
        logger.warning(f"TGA scheduler start error: {e}")

    # Report Scheduler — kullanıcı tanımlı periyodik rapor e-postaları.
    try:
        from workers.report_scheduler_worker import start as _start_report_sched
        if _start_report_sched():
            logger.info("Report scheduler worker started")
    except Exception as e:
        logger.warning(f"Report scheduler worker start error: {e}")

    # Konaklama Vergisi Auto-Finalize + Email Scheduler (v95.9)
    # Ay başında önceki ayın beyannamesini otomatik kilitler ve
    # konfigüre edilmiş alıcılara PDF eki ile e-posta atar.
    try:
        from workers.konaklama_vergisi_scheduler import start as _start_kvb_sched
        if _start_kvb_sched():
            logger.info("Konaklama Vergisi scheduler started")
    except Exception as e:
        logger.warning(f"Konaklama Vergisi scheduler start error: {e}")

    # Marketplace indexes + product seed
    try:
        from core.subscriptions import ensure_indexes as _ms_indexes
        await _ms_indexes()
        logger.info("Marketplace indexes ensured")
    except Exception as e:
        logger.warning(f"Marketplace index creation error: {e}")

    # Check-in/Check-out transaction indexes
    try:
        from core.atomic_checkin_checkout import ensure_checkin_checkout_indexes
        await ensure_checkin_checkout_indexes()
        logger.info("Check-in/check-out indexes ensured")
    except Exception as e:
        logger.warning(f"Check-in/check-out index creation error: {e}")

    # Folio Ledger indexes
    try:
        from core.folio_ledger_service import ensure_folio_ledger_indexes
        await ensure_folio_ledger_indexes()
    except Exception as e:
        logger.warning(f"Folio ledger index creation error: {e}")

    # Learning Loop indexes
    try:
        from core.learning_loop import ensure_learning_loop_indexes
        await ensure_learning_loop_indexes()
    except Exception as e:
        logger.warning(f"Learning loop index creation error: {e}")

    # PERF-001: Compound indexes for hot queries
    try:
        from bootstrap.phases.perf_indexes import ensure_performance_indexes
        await ensure_performance_indexes()
        logger.info("Performance indexes ensured")
    except Exception as e:
        logger.warning(f"Performance index creation error: {e}")

    # R5: Audit-derived missing indexes (top-25 koleksiyon kapsama)
    try:
        from bootstrap.phases.audit_indexes import ensure_audit_indexes
        added = await ensure_audit_indexes()
        if added:
            logger.info(f"R5 audit indexes ensured ({added} created)")
    except Exception as e:
        logger.warning(f"R5 audit index creation error: {e}")

    # Encrypted-PII search: sparse indexes on the _hash_<field> blind-index
    # tokens (HMAC-SHA256) that back searchable encrypted fields (guests.email,
    # phone, id_number, passport_number, …). Without these, the encrypted-search
    # branch of build_search_query (_hash_<field> equality) falls back to a
    # tenant-wide collection scan — high Atlas query-targeting. ensure_hash_
    # indexes was previously reachable ONLY via the admin field-encryption
    # router (manual trigger); wiring it into startup makes the indexes
    # always-present and idempotent. PII-safe: indexes only the HMAC tokens,
    # never plaintext.
    try:
        from core.database import _raw_db
        from security.field_encryption import get_field_encryption_service
        created = await get_field_encryption_service().ensure_hash_indexes(_raw_db)
        if created:
            logger.info(f"Encrypted-PII hash indexes ensured ({len(created)} created)")
    except Exception as e:
        logger.warning(f"Hash index creation error: {e}")
