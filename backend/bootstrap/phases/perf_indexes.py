"""PERF-001: Compound indexes for hot query patterns + R5 audit augmentations."""
import logging

from core.database import _raw_db

logger = logging.getLogger(__name__)


async def ensure_performance_indexes():
    indexes = [
        # Bookings
        ("bookings", [("tenant_id", 1), ("status", 1), ("check_in", 1)], "idx_booking_status_checkin", {}),
        ("bookings", [("tenant_id", 1), ("room_id", 1), ("check_in", 1), ("check_out", 1)], "idx_booking_room_dates", {}),
        ("bookings", [("tenant_id", 1), ("guest_id", 1), ("status", 1)], "idx_booking_guest_status", {}),
        # Global guest_id index (TENANT'SIZ, BİLİNÇLİ): Guest App "tüm
        # otellerimdeki rezervasyonlarım" akışı (guest_app.py:285,
        # operations_router.py:535) `find({guest_id: {$in: [...]}})` yapıyor;
        # tenant_id dahil değil (cross-tenant guest deneyimi). idx_booking_*
        # tenant-prefixli compound'lar bu sorguda seçilemiyor — collection
        # scan'e düşüyordu. 2026-05-07 audit'te tespit edildi (architect
        # NEEDS_FIXES'ı kapatır).
        ("bookings", [("guest_id", 1)], "idx_booking_guest_global", {}),
        ("bookings", [("tenant_id", 1), ("created_at", -1)], "idx_booking_created", {}),
        # Rooms
        ("rooms", [("tenant_id", 1), ("is_active", 1), ("room_type", 1)], "idx_room_type_active", {}),
        ("rooms", [("tenant_id", 1), ("status", 1)], "idx_room_status", {}),
        # Folios
        ("folios", [("tenant_id", 1), ("booking_id", 1), ("status", 1)], "idx_folio_booking_status", {}),
        ("folio_charges", [("folio_id", 1), ("tenant_id", 1), ("voided", 1)], "idx_charge_folio", {}),
        ("payments", [("folio_id", 1), ("tenant_id", 1), ("voided", 1)], "idx_payment_folio", {}),
        ("guests", [("tenant_id", 1), ("name", 1)], "idx_guest_name", {}),
        ("outbox_events", [("status", 1), ("event_type", 1), ("created_at", 1)], "idx_outbox_queue", {}),
        ("housekeeping_tasks", [("tenant_id", 1), ("status", 1), ("room_id", 1)], "idx_hk_status_room", {}),
        ("pms_audit_trail", [("tenant_id", 1), ("entity_id", 1), ("timestamp", -1)], "idx_audit_entity", {}),
        # R5 audit ek index'ler
        ("bookings", [("tenant_id", 1), ("status", 1), ("check_out", 1)], "idx_booking_status_checkout", {}),
        # idx_booking_room_status: REDUNDANT — Atlas Advisor (Mayıs 2026):
        # `idx_booking_overlap_check` (tenant_id, room_id, status, check_in,
        # check_out) prefix'i ile tamamen kapsanıyor. Kaldırıldı.
        ("guests", [("tenant_id", 1), ("vip", 1)], "idx_guest_vip", {}),
        ("folios", [("tenant_id", 1), ("status", 1), ("balance", 1)], "idx_folio_status_balance", {}),
        ("folios", [("tenant_id", 1), ("folio_type", 1), ("status", 1)], "idx_folio_type_status", {}),
        ("users", [("tenant_id", 1), ("email", 1)], "idx_user_email", {}),
        ("users", [("tenant_id", 1), ("role", 1), ("is_active", 1)], "idx_user_role_active", {}),
        ("folio_charges", [("tenant_id", 1), ("folio_id", 1), ("voided", 1)], "idx_charge_tenant_folio", {}),
        ("folio_charges", [("tenant_id", 1), ("voided", 1), ("date", 1)], "idx_charge_voided_date", {}),
        ("folio_charges", [("tenant_id", 1), ("charge_category", 1), ("date", 1)], "idx_charge_category_date", {}),
        ("housekeeping_tasks", [("tenant_id", 1), ("status", 1), ("assigned_to", 1)], "idx_hk_status_assigned", {}),
        ("housekeeping_tasks", [("tenant_id", 1), ("completed_at", -1)], "idx_hk_completed", {}),
        ("payments", [("tenant_id", 1), ("folio_id", 1), ("voided", 1)], "idx_payment_tenant_folio", {}),
        ("payments", [("tenant_id", 1), ("voided", 1), ("payment_date", -1)], "idx_payment_voided_date", {}),
        ("payments", [("tenant_id", 1), ("booking_id", 1)], "idx_payment_booking", {}),
        # Night-audit daily revenue (financial_service.py): payments pipeline
        # matches `{tenant_id, status:{$ne:"voided"}, $or:[{date:bd},
        # {payment_date:bd}]}` plus `date` range scans in the daily/period
        # report. `payment_date` is partially covered by idx_payment_voided_date,
        # but the legacy `date` field had NO index, so the $or's date branch fell
        # back to a tenant-wide scan (high scanned/returned query-targeting on
        # the `payments` collection). This indexes the date branch directly.
        ("payments", [("tenant_id", 1), ("date", 1)], "idx_payment_tenant_date", {}),
        # Sibling of idx_payment_tenant_date for the SAME night-audit daily
        # revenue $or branch `{payment_date: bd}` (financial_service.py) and the
        # payment_date range scans. idx_payment_voided_date is (tenant_id,
        # voided, payment_date): the night-audit query filters on `status` (NOT
        # the `voided` boolean), so that index's middle key is unconstrained and
        # only a less-efficient skip-scan is possible. A clean (tenant_id,
        # payment_date) serves the $ne-status query directly. Both $or branches
        # run on every daily-revenue call, so both legs need direct coverage.
        ("payments", [("tenant_id", 1), ("payment_date", 1)], "idx_payment_tenant_paydate", {}),
        ("audit_logs", [("tenant_id", 1), ("timestamp", -1)], "idx_audit_log_timestamp", {}),
        ("audit_logs", [("tenant_id", 1), ("action", 1), ("timestamp", -1)], "idx_audit_log_action", {}),
        ("tenants", [("chain_id", 1), ("parent_tenant_id", 1)], "idx_tenant_chain", {}),
        ("hotelrunner_connections", [("tenant_id", 1), ("status", 1)], "idx_hr_status", {}),
        ("cm_imported_reservations", [("tenant_id", 1), ("source_property_id", 1), ("channel", 1)], "idx_cm_source_channel", {}),
        ("outbox_events", [("processed", 1), ("created_at", 1)], "idx_outbox_processed_created", {}),
        ("task_queue", [("tenant_id", 1), ("status", 1), ("scheduled_for", 1)], "idx_task_queue_poll", {}),
        ("night_audit_runs", [("tenant_id", 1), ("business_date", -1)], "idx_night_audit_date", {}),
        # R5 follow-up audit (2026-05-03): 7 yoğun koleksiyonda tenant_id'li
        # bileşik index eksikti — kapsama tamamlandı.
        # idx_exely_sync_tenant_created: KALDIRILDI (2026-05-10) — collection
        # `created_at` alanı kullanmıyor (`log_sync` `timestamp` yazıyor),
        # 6024/6024 doc'ta `created_at` YOK. Yerine
        # idx_exely_sync_tenant_timestamp (aşağıda) eklendi.
        ("hotelrunner_sync_logs", [("tenant_id", 1), ("created_at", -1)], "idx_hr_sync_tenant_created", {}),
        ("idempotency_keys", [("tenant_id", 1), ("created_at", -1)], "idx_idempotency_tenant_created", {}),
        # Task #81 — TTL sweep on `idempotency_keys`. Every protected request
        # (folio charge/payment, housekeeping create, KBS submit, reservation
        # acquire, …) writes one document per (tenant, scope, key); without a
        # janitor the collection grows without bound and the DuplicateKeyError
        # lookup that gates every retry slows down. `expires_at` is a BSON
        # Date set explicitly by the writers in shared_kernel/idempotency.py
        # and the per-module repositories:
        #   - processing rows: now + 5 min  (releases ghost locks left by
        #     crashed workers so retries aren't blocked forever)
        #   - completed/failed rows: now + 24 h  (replay window for clients
        #     retrying the same Idempotency-Key)
        # expireAfterSeconds=0 means Mongo deletes the row as soon as
        # `expires_at` is in the past. Retention window is documented in
        # docs/GOTCHAS.md.
        ("idempotency_keys", [("expires_at", 1)], "idx_idempotency_expires_at_ttl",
         {"expireAfterSeconds": 0}),
        ("audit_exceptions", [("tenant_id", 1), ("created_at", -1)], "idx_audit_exc_tenant_created", {}),
        ("agencies", [("tenant_id", 1), ("status", 1)], "idx_agencies_tenant_status", {}),
        ("night_audit_logs", [("tenant_id", 1), ("business_date", -1)], "idx_night_audit_logs_tenant_date", {}),
        ("currency_rates", [("tenant_id", 1), ("base_currency", 1), ("date", -1)], "idx_currency_rates_tenant", {}),
        # R-split 2026-05-03 follow-up: invoices koleksiyonu R5'te atlanmıştı.
        ("invoices", [("tenant_id", 1), ("created_at", -1)], "idx_invoices_tenant_created", {}),
        ("invoices", [("tenant_id", 1), ("status", 1), ("issue_date", -1)], "idx_invoices_tenant_status", {}),
        # R5 final pass 2026-05-04: monitoring_metrics_history (~2.6k docs)
        # tek index'siz top-25 koleksiyondu — time-series query coverage.
        ("monitoring_metrics_history", [("tenant_id", 1), ("metric_name", 1), ("timestamp", -1)],
         "idx_monitoring_metrics_tenant_name_ts", {}),
        ("monitoring_metrics_history", [("timestamp", -1)],
         "idx_monitoring_metrics_ts", {}),
        # Atlas Performance Advisor (2026-05-10):
        #   - channel_reconciliation_cases: rollout_framework + cockpit_snapshot
        #     worker'ları `find({tenant_id, ...}).sort(created_at)` yapıyor;
        #     7336 docs scan / 100 returned (targeting 73, 147ms).
        #   - exely_sync_logs: wire_failure_router (`_bump` ve `find`) gerçek
        #     sorgu alanı `timestamp` (created_at değil); mevcut
        #     idx_exely_sync_tenant_created bu pattern'i karşılamıyor.
        #     5745 scan / 101 returned (targeting 57, 256ms).
        ("channel_reconciliation_cases", [("tenant_id", 1), ("created_at", -1)],
         "idx_recon_cases_tenant_created", {}),
        ("exely_sync_logs", [("tenant_id", 1), ("timestamp", -1)],
         "idx_exely_sync_tenant_timestamp", {}),
        # WhatsApp inbound idempotency — Meta retry'larda duplicate önler.
        # Webhook upsert'i (tenant_id, wa_message_id) key'iyle yapıyor;
        # concurrency altında race-free garanti için unique index gerekli.
        ("wa_inbound_messages", [("tenant_id", 1), ("wa_message_id", 1)],
         "idx_wa_inbound_unique", {"unique": True}),
        # WhatsApp webhook tenant lookup — phone_number_id'den config'e.
        ("messaging_provider_configs",
         [("provider_type", 1), ("credentials_encrypted.phone_number_id", 1)],
         "idx_msg_provider_phone_lookup", {}),
        # Task #184 — record-payment idempotency: bir misafir tekrar tıkladığında
        # ya da frontend/network retry yaptığında aynı (tenant_id, booking_id,
        # reference) anahtarıyla iki kez yazılan ödeme satırı misafiri çift
        # kreditler ve folio bakiyesini sessizce kaydırır. Partial unique index
        # `reference` string olduğunda ve `voided=false` iken benzersizlik
        # zorlar; void edilen satırlar index dışında kalır → aynı reference
        # void sonrası yeniden kullanılabilir. Application-level fast-path
        # (find_one + DuplicateKeyError yakala) bu index'in race-free
        # garantisine dayanır.
        ("payments",
         [("tenant_id", 1), ("booking_id", 1), ("reference", 1)],
         "uniq_payment_reference_active",
         {"unique": True,
          "partialFilterExpression": {
              "reference": {"$type": "string"},
              "voided": False,
          }}),
    ]
    for coll_name, keys, name, kwargs in indexes:
        try:
            await _raw_db[coll_name].create_index(keys, name=name, background=True, **kwargs)
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning(f"Index {name} on {coll_name} failed: {e}")
