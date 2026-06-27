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
        # Task #312 — payment_intents: tahsilat akisinin pending/reconcile kaydi.
        # Webhook conversationId -> intent lookup'i SUNUCU-URETIMI conversation_token
        # uzerinden yapilir (client-controlled idempotency_key DEGIL); cross-tenant
        # yanlis eslemeyi onlemek icin token GLOBALLY UNIQUE. Indekssiz collection
        # scan public webhook yuzeyinde DoS riski oldugundan ayrica indekslenir.
        ("payment_intents", [("conversation_token", 1)],
         "idx_payment_intents_conv_token", {"unique": True}),
        # Idempotency lookup'lari tenant'a kapali (client key tenant'lar arasi cakisabilir).
        ("payment_intents", [("tenant_id", 1), ("idempotency_key", 1)],
         "idx_payment_intents_tenant_idem", {}),
        ("payment_intents", [("tenant_id", 1), ("status", 1), ("created_at", -1)],
         "idx_payment_intents_tenant_status", {}),
        # Task #315 — Otonom tahsilat (no-show + VCC check-in) deploy-ani indeks
        # garantisi. Bu IKI index bir optimizasyon DEGIL, exactly-once cekirdegin
        # ZORUNLU invariant'i:
        #   - autonomous_collection_runs (tenant_id) UNIQUE: coklu-beat yarisinda
        #     gunluk dispatch'in per-tenant tek-kazanan CAS claim'i bu unique
        #     constraint'e dayanir (yoksa iki state dokumani -> cift dispatch ->
        #     cift-charge zinciri). Beat dispatcher ayrica bu index'i runtime'da
        #     fail-closed olarak ensure eder; burada deploy/boot aninda garanti
        #     altina alinir ki fail-closed yol kural degil ISTISNA olsun.
        #   - autonomous_collection_jobs (tenant_id, booking_id, charge_kind)
        #     UNIQUE: is kuyrugunun (tenant, booking, kind) basina TEK satir
        #     invariant'i; upsert/$inc attempts bu eszamansiz-guvenli olur.
        # Adlar celery_tasks.py (autonomous_collection_runs_tenant_uq) ve
        # core/autonomous_collection.py (autocollect_jobs_uq) ile BIREBIR ayni —
        # runtime ensure ile boot ensure ASLA duplicate index uretmez (name drift
        # yok). scripts/index_apply.py'de de ayni adlarla yer alir (operator
        # immediate apply, bos koleksiyonlari Atlas limiti icin atlar).
        ("autonomous_collection_runs", [("tenant_id", 1)],
         "autonomous_collection_runs_tenant_uq", {"unique": True}),
        ("autonomous_collection_jobs",
         [("tenant_id", 1), ("booking_id", 1), ("charge_kind", 1)],
         "autocollect_jobs_uq", {"unique": True}),
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
        # Atlas Query Targeting (2026-06-17): monitoring/aggregator.py
        # collect_reconciliation_health() is a BY-DESIGN cross-tenant
        # (platform-wide ops health) function with NO tenant_id filter:
        #   - {status: {$in: ["open","acknowledged"]}}  (case_type + severity
        #     $group aggregates), and
        #   - count_documents({created_at: {$gte: <24h ago>}})  (growth rate).
        # Every OTHER recon site is tenant-scoped (idx_recon_cases_tenant_created
        # above + unified_repository.py runtime indexes), and all of those lead
        # with tenant_id — so these two global shapes COLLSCANned the whole
        # ~7.3k collection every ~5 min, tripping "Scanned/Returned > 1000".
        # These NON-tenant indexes serve the global shapes directly: the status
        # index turns the open/ack aggregates into a ~13-key scan, and the
        # created_at index (ISO-8601 string; lexicographic == chronological)
        # turns the 24h growth count into a small range scan. The function stays
        # intentionally cross-tenant; do NOT add a tenant_id filter.
        ("channel_reconciliation_cases", [("status", 1)],
         "idx_recon_cases_status_global", {}),
        ("channel_reconciliation_cases", [("created_at", 1)],
         "idx_recon_cases_created_global", {}),
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
        # Task #645 — Contact Center Faz 1 (omnichannel WhatsApp MVP).
        #   - contact_center_messages (tenant_id, channel, provider_message_id):
        #     Meta retry inbound + status callback aynı provider_message_id'yi
        #     tekrar iletir; ingest upsert'i bu key'le idempotent. PARTIAL on
        #     provider_message_id string → henüz id atanmamış (None) giden
        #     taslaklar collision'a girmez (fake-green'i önler). Race-free
        #     garanti için unique.
        ("contact_center_messages",
         [("tenant_id", 1), ("channel", 1), ("provider_message_id", 1)],
         "ux_cc_messages_provider_msg_id",
         {"unique": True,
          "partialFilterExpression": {"provider_message_id": {"$type": "string"}}}),
        #   - contact_center_conversations (tenant_id, channel, caller_id_hash):
        #     ingest'in arayan başına AÇIK konuşmayı bul-veya-oluştur
        #     find_one_and_update'i bu shape ile sorgular (blind-index hash).
        #     PARTIAL-UNIQUE {status: "open"}: bir arayanın aynı kanalda yalnızca
        #     BİR açık konuşması olabilir → eşzamanlı ilk-mesaj / Meta-retry
        #     yarışında upsert ÇİFT açık konuşma üretemez (kaybeden taraf
        #     DuplicateKeyError alır, ingest mevcut konuşmayı okur). Kapalı
        #     konuşmalar partial filtre dışında kalır → arayan tarih boyunca
        #     birden çok KAPALI konuşmaya sahip olabilir. Sorgu status:"open"
        #     içerdiğinden planlayıcı bu partial index'i kullanır.
        ("contact_center_conversations",
         [("tenant_id", 1), ("channel", 1), ("caller_id_hash", 1)],
         "ux_cc_conv_open_caller",
         {"unique": True,
          "partialFilterExpression": {"status": "open"}}),
        #   - contact_center_conversations (tenant_id, last_message_at desc):
        #     liste ucu son mesaja göre azalan sıralar.
        ("contact_center_conversations",
         [("tenant_id", 1), ("last_message_at", -1)],
         "idx_cc_conv_tenant_lastmsg", {}),
        # Task #648 — Contact Center Faz 2 (sesli softphone, Twilio Voice).
        #   - contact_center_calls (tenant_id, provider_call_sid): Twilio inbound +
        #     status + recording callback'leri aynı CallSid'i retry eder; durum
        #     makinesi (record_inbound_call / update_call_status / attach_recording)
        #     bu key'le idempotent. PARTIAL on provider_call_sid string → SID henüz
        #     atanmamış (None) satırlar collision'a girmez. Eşzamanlı ilk-inbound
        #     yarışında upsert ÇİFT çağrı üretemez (kaybeden DuplicateKeyError alır,
        #     mevcut çağrıyı okur). Race-free garanti için unique.
        ("contact_center_calls",
         [("tenant_id", 1), ("provider_call_sid", 1)],
         "ux_cc_calls_provider_sid",
         {"unique": True,
          "partialFilterExpression": {"provider_call_sid": {"$type": "string"}}}),
        #   - contact_center_calls (tenant_id, started_at desc): çağrı listesi ucu
        #     başlangıca göre azalan sıralar.
        ("contact_center_calls",
         [("tenant_id", 1), ("started_at", -1)],
         "idx_cc_calls_tenant_started", {}),
        #   - contact_center_voice_numbers (to_number): public inbound webhook'ta
        #     çağrılan numaradan kiracıyı sunucu-tarafı eşler (istemci tenant geçemez).
        ("contact_center_voice_numbers",
         [("to_number", 1)],
         "ux_cc_voice_number", {"unique": True}),
        # Task #647 — Legacy messaging recipient PII at-rest sealing.
        #   - messaging_consents (tenant_id, recipient_hash, channel):
        #     consent opt-out enforcement now looks the recipient up by its HMAC
        #     blind-index (recipient_hash) instead of plaintext. This is the
        #     exact-equality lookup shape in _check_consent + the upsert key in
        #     the /consent endpoint and WhatsApp auto-opt-in, so the index keeps
        #     it from collection-scanning. NOT unique: the gateway's
        #     guest_id-keyed consent shape (no recipient_hash) shares this
        #     collection and would collide on a null-key unique index.
        ("messaging_consents",
         [("tenant_id", 1), ("recipient_hash", 1), ("channel", 1)],
         "idx_msg_consent_recipient_hash", {}),
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
        # Task #360 — POS create-order atomic + idempotent folio posting.
        #   - pos_orders (tenant_id, idempotency_key): a retry / double-tap /
        #     network replay carrying the same client key must NOT create a
        #     second order. PARTIAL on idempotency_key string so legacy orders
        #     (no key) are exempt — otherwise a unique index over a missing
        #     field collapses them all into one collision (fake-green).
        #   - folio_charges (tenant_id, source_pos_order_id, line_no): DB-level
        #     guard so a partial-failure re-post of the same POS order can't
        #     double-post the same charge line. PARTIAL on source_pos_order_id
        #     string so legacy / non-POS charges are exempt.
        # These are also lazily ensured per-request (fail-closed) in
        # pos_core._ensure_pos_atomicity_indexes; this entry covers cold start.
        ("pos_orders",
         [("tenant_id", 1), ("idempotency_key", 1)],
         "ux_pos_orders_tenant_idemp",
         {"unique": True,
          "partialFilterExpression": {"idempotency_key": {"$type": "string"}}}),
        ("folio_charges",
         [("tenant_id", 1), ("source_pos_order_id", 1), ("line_no", 1)],
         "ux_folio_charges_pos_source",
         {"unique": True,
          "partialFilterExpression": {"source_pos_order_id": {"$type": "string"}}}),
        # Misafir Oda Talepleri sohbet thread'i (guest_room_messages):
        #   - (tenant_id, room_id, created_at): oda thread'i kronolojik getirme
        #     + booking-scoped misafir GET + okunmamış sayımı için.
        #   - (tenant_id, created_at): personel akışındaki oda-gruplama
        #     aggregate'i (en son etkinliğe göre) için.
        ("guest_room_messages",
         [("tenant_id", 1), ("room_id", 1), ("created_at", -1)],
         "ix_grm_tenant_room_created",
         {}),
        ("guest_room_messages",
         [("tenant_id", 1), ("created_at", -1)],
         "ix_grm_tenant_created",
         {}),
        # Atlas Performance Advisor (2026-06-14): folios & folio_charges were
        # missing the (tenant_id, id) companion that every other hot collection
        # already has (bookings idx_booking_tenant_id, guests idx_g_tid_id).
        # Single-doc lookups by the app-level `id` fell back to a tenant-wide
        # COLLSCAN:
        #   - folios: ~51.5 queries/hour, 13k scanned / 1 returned (376ms) —
        #     the single most frequent advisor finding.
        #   - folio_charges: ~1.2 q/h, 92k scanned / 1 returned (3.6s); the
        #     collection is very large (stress/E2E residue inflates it), so the
        #     scan is expensive.
        # `id` is an equality predicate, so (tenant_id, id) fully serves the
        # tenant-scoped find_one({tenant_id, id}). NON-unique on purpose: the
        # collections carry legacy/stress rows and uniqueness is enforced on the
        # write paths, not here — a unique build could fail on a stray dup.
        # NAME = the Mongo default "tenant_id_1_id_1" so this declaration stays
        # idempotent with scripts/index_apply.py (which the operator runs to
        # apply immediately when a full boot is unavailable, and which creates
        # with the default name). Same key + a different name would raise an
        # IndexOptionsConflict on every boot (caught, but noisy).
        ("folios", [("tenant_id", 1), ("id", 1)], "tenant_id_1_id_1", {}),
        ("folio_charges", [("tenant_id", 1), ("id", 1)], "tenant_id_1_id_1", {}),
        # POS F&B sicak okuma yollari (2026-06-18): pos_orders ve
        # pos_transactions koleksiyonlarinda simdiye kadar yalnizca
        # idempotency/atomicity index'leri (ux_pos_orders_tenant_idemp,
        # ux_folio_charges_pos_source) vardi; operasyonel OKUMA sorgulari hicbir
        # tenant-prefix compound index kullanamiyor, tenant capinda COLLSCAN'e
        # dusuyordu. POS en yuksek es-zamanlilik + yazma-yogun yuzey oldugundan
        # gecmis buyudukce bu taramalar dogrudan latency'ye yansir. Her index
        # gercek bir cagri yerine baglidir (spekulatif degil, fake-green degil):
        #   - pos_orders (tenant_id, status, created_at): get_active_orders
        #     status {$in:[pending,preparing,ready]} + sort created_at -> aktif
        #     siparis panosu (polled). status'lu sorgu icin status-prefix sart.
        #   - pos_orders (tenant_id, created_at): get_fnb_dashboard / fnb_reports
        #     {tenant_id, created_at: range} .to_list(10000..20000) -> tarih
        #     araligi raporlari (en pahali taramalar). status'suz sorgu oldugu
        #     icin status-prefix'li index KULLANILAMAZ -> ayri index gerekir.
        #   - pos_orders (tenant_id, id) / pos_transactions (tenant_id, id):
        #     find_one({id, tenant_id}) tek-dokuman getirme (split-check,
        #     complete, void, refund). folios/folio_charges ile ayni desen;
        #     default ad "tenant_id_1_id_1" -> index_apply.py 2-tuple ile birebir
        #     ayni ad (name drift yok). NON-unique: legacy/stress satirlarinda
        #     olasi cift kayitta build patlamasin.
        #   - pos_transactions (tenant_id, order_id): complete_order akisinda
        #     find_one({order_id, tenant_id}) (pos_fnb_service_v2).
        #   - pos_transactions (tenant_id, outlet_id, table_number) PARTIAL
        #     {status:"open"}: open_tab her cagrida "ayni masada acik adisyon var
        #     mi" guard'i {tenant_id, outlet_id, table_number, status:"open"}
        #     tarar. Partial index yalnizca acik adisyonlari tutar -> kucuk
        #     kalir; sorgudaki literal status:"open" partialFilter'i karsiladigi
        #     icin planner index'i kullanir.
        ("pos_orders", [("tenant_id", 1), ("status", 1), ("created_at", 1)],
         "idx_pos_orders_status_created", {}),
        ("pos_orders", [("tenant_id", 1), ("created_at", 1)],
         "idx_pos_orders_tenant_created", {}),
        ("pos_orders", [("tenant_id", 1), ("id", 1)], "tenant_id_1_id_1", {}),
        ("pos_transactions", [("tenant_id", 1), ("id", 1)], "tenant_id_1_id_1", {}),
        ("pos_transactions", [("tenant_id", 1), ("order_id", 1)],
         "idx_pos_txn_tenant_order", {}),
        ("pos_transactions",
         [("tenant_id", 1), ("outlet_id", 1), ("table_number", 1)],
         "idx_pos_txn_open_tab",
         {"partialFilterExpression": {"status": "open"}}),
        # B2B agency auto-provisioning (Seçenek B / connect-request approval).
        #   - b2b_connect_codes.code_hmac UNIQUE: fast tenant resolution from a
        #     hashed connect code (lookup must be O(1), not a scan).
        #   - b2b_connection_requests partial-unique (tenant, agency_name_lower)
        #     {status:pending}: at most one open pending request per agency name.
        #   - expires_at TTL: 30-day request record retention sweep.
        ("b2b_connect_codes", [("code_hmac", 1)],
         "ux_b2b_connect_code_hmac", {"unique": True}),
        ("b2b_connect_codes", [("tenant_id", 1), ("is_active", 1)],
         "idx_b2b_connect_code_tenant", {}),
        ("b2b_connection_requests",
         [("tenant_id", 1), ("status", 1), ("created_at", -1)],
         "idx_b2b_conn_req_tenant_status", {}),
        ("b2b_connection_requests", [("tenant_id", 1), ("agency_name_lower", 1)],
         "ux_b2b_conn_req_pending",
         {"unique": True, "partialFilterExpression": {"status": "pending"}}),
        ("b2b_connection_requests",
         [("tenant_id", 1), ("agency_platform_request_id", 1)],
         "idx_b2b_conn_req_idem",
         {"partialFilterExpression": {"agency_platform_request_id": {"$exists": True}}}),
        ("b2b_connection_requests", [("expires_at", 1)],
         "idx_b2b_conn_req_ttl", {"expireAfterSeconds": 0}),
        # At most one ACTIVE API key per (tenant, agency): a DB-level backstop so
        # two concurrent approvals for the same brand-new agency can never both
        # mint an active key. The approve handler catches the DuplicateKeyError and
        # connects without minting a second key. Best-effort build (legacy dup
        # actives won't crash boot); the in-handler claim is the primary guard.
        ("agency_api_keys", [("tenant_id", 1), ("agency_id", 1)],
         "ux_b2b_agency_api_key_active",
         {"unique": True, "partialFilterExpression": {"is_active": True}}),
        # Exely reservations (#649): partial-unique on (tenant, external_id) so two
        # concurrent first-deliveries of the same reservation can't both insert.
        # With a unique index, MongoDB auto-retries the upsert's duplicate-key once
        # → update, making concurrent first-delivery race-free. The partial filter
        # keeps legacy rows without a string external_id out of the constraint
        # (best-effort build; no fake-green).
        ("exely_reservations", [("tenant_id", 1), ("external_id", 1)],
         "ux_exely_reservations_tenant_extid",
         {"unique": True, "partialFilterExpression": {"external_id": {"$type": "string"}}}),
        # Agency v1 (ADR docs/adr/2026-06-agency-pms-integration.md) — Adim 1 DB
        # temeli. idempotency_cache = Karar 4 SOGUK katmani: cozulen rezervasyon
        # yanitlari (POST create / PATCH modify / DELETE cancel) Mongo'ya offload
        # edilir ve 48h sonunda TTL ile otomatik silinir (sicak Redis katmani
        # ayri, 15-30dk; bu DB foundation degil). Iki index:
        #   - ux_idempotency_cache_scope: ADR'de DONMUS scope
        #     (tenant_id, agency_id, method, path, idempotency_key). Yalniz key
        #     ile scope YETERSIZ — ayni anahtar farkli uclarda (POST create vs
        #     PATCH modify) yanlis 409/422 uretebilir; method+path baglama bunu
        #     engeller, cross-tenant gorunmez. PARTIAL on idempotency_key string:
        #     henuz key atanmamis (None) satirlar collision'a girmez (fake-green
        #     onlenir). UNIQUE → ayni scope iki kez yazilamaz (replay/dedup
        #     race-free, DuplicateKeyError ile cozulur).
        #   - ttl_idempotency_cache: expires_at (BSON Date) yazici tarafindan
        #     now+48h set edilir; expireAfterSeconds=0 → suresi gecince Mongo
        #     siler. 48h, acente retry penceresinden (Karar 6 webhook backoff
        #     ~24h) marjli buyuk. PII govdesi soguk katmanda sifreli/referans
        #     tutulur (yazici sorumlulugu, Adim 3); index sadece scope+TTL.
        # background=True ortak donguden gelir → boot'ta indeks basimi worker'i
        # kilitlemez (502/503 yok), zero-downtime.
        ("idempotency_cache",
         [("tenant_id", 1), ("agency_id", 1), ("method", 1), ("path", 1),
          ("idempotency_key", 1)],
         "ux_idempotency_cache_scope",
         {"unique": True,
          "partialFilterExpression": {"idempotency_key": {"$type": "string"}}}),
        ("idempotency_cache", [("expires_at", 1)],
         "ttl_idempotency_cache",
         {"expireAfterSeconds": 0}),
        # Agency v1 Adim 3 — HMAC replay-cache (Karar 2). `_id = "{key_id}:{nonce}"`
        # zaten otomatik unique → ayni nonce ikinci insert DuplicateKeyError verir
        # (replay race-free); ek unique index GEREKMEZ. Tek index: expires_at TTL.
        # Yazici expires_at = now+600s set eder (>= etkin kabul penceresi 360s;
        # DEGISMEZ kural: TTL >= pencere, yoksa nonce suresi dolup timestamp hala
        # gecerliyken replay penceresi acilir). expireAfterSeconds=0 → suresi
        # gecince Mongo siler (depo hijyeni; dogruluk _id benzersizliginden gelir).
        ("agency_nonces", [("expires_at", 1)],
         "ttl_agency_nonces",
         {"expireAfterSeconds": 0}),
        # Agency v1 Adim 3 — POST create TOCTOU zirhi (Karar 5 dayanikliligi).
        # router.py create'teki domain-guard (read-then-insert: ayni (tenant,
        # agency, external_id) icin aktif booking var mi) tek basina race-safe
        # DEGILDIR: acente mukerrer Idempotency-Key ile ayni external_id'yi
        # milisaniyeler icinde iki kez gonderirse iki istek de "yok" okuyup ikisi
        # de yazabilir (cifte booking + overbooking). Bu kismi-unique index DB
        # seviyesinde tek dogruluk kaynagidir: yarisi kaybeden insert
        # DuplicateKeyError alir -> DuplicateReservation -> kazananin IDEMPOTENT
        # yaniti. partialFilterExpression $ne desteklemez; bu yuzden "aktif=
        # iptal-edilmemis" semantigi `agency_external_active` alani ile tasinir:
        # create'te external_id'ye set edilir, cancel'da $unset edilir -> iptal
        # sonrasi ayni external_id ile yeniden olusturma serbest (domain-guard
        # status!=cancelled ile bire bir). $type:string -> alan yoksa (acente-disi
        # booking veya iptal edilmis) kisitlamaya girmez (fake-green onlenir).
        ("bookings",
         [("tenant_id", 1), ("agency_id", 1), ("agency_external_active", 1)],
         "ux_agency_booking_external_active",
         {"unique": True,
          "partialFilterExpression": {"agency_external_active": {"$type": "string"}}}),
    ]
    for coll_name, keys, name, kwargs in indexes:
        try:
            await _raw_db[coll_name].create_index(keys, name=name, background=True, **kwargs)
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning(f"Index {name} on {coll_name} failed: {e}")
