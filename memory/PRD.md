# Multi-Tenant SaaS PMS + Channel Manager — PRD

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager with canonical data models, multi-tenant isolation, PII strict mode tracking, and comprehensive multi-language support.

## Architecture
- **Backend:** FastAPI + MongoDB (MONGO_URL from .env)
- **Frontend:** React + i18n (10 locales, 1640 keys each)
- **Channel Manager:** HotelRunner v2 (LIVE MODE), Exely (SOAP)
- **Security:** PII Strict Mode, AES-256-GCM field encryption

## What's Been Implemented

### Core Platform
- Multi-tenant isolation with tenant-scoped data
- JWT authentication system
- Role-based access control
- Subscription/module management

### i18n System (100% Complete)
- 10 locales: en, tr, ar, de, es, fr, it, ru, pt, zh
- All 1640 keys synchronized across all languages
- pt.json and zh.json fully translated to native languages
- Static imports for guaranteed translation availability

### Channel Manager
- HotelRunner v2 connector (LIVE MODE — shadow_mode=false, write_enabled=true)
- HotelRunner v1 deprecated (warnings added to all files)
- Exely SOAP API integration
- Wire failure tracking system
- ARI Push (availability, rate, min_stay, stop_sell) working via query params
- **Rate limit protection**: Adaptive backoff for polling, capped retry for pushes, fail-fast strategy

### Security & PII — Field Encryption (100% Complete)
- PII Strict Mode middleware/router
- **Guest collection: 100% encrypted** (email, phone, id_number, passport, address, etc.)
- **Users collection: 100% encrypted** (email, phone)
- **Bookings collection: 100% encrypted** (guest_email, guest_phone, billing_address, billing_tax_number)
- Hash-based search indexes for encrypted fields
- Dual-read pattern: auth/search works with both encrypted and plaintext data
- Auto-encryption on new inserts
- AES-256-GCM with HMAC-SHA256 search hashes

### HotelRunner Live Integration
- Shadow Mode disabled, Live Mode active
- Room/rate mappings created
- **30-second polling** with adaptive backoff (optimized from 300s)
- **Phase A.5**: Real-time modification detection via `from_last_update_date` — every cycle
- **Phase A.5 Cancellation Fix**: Detects `state=cancelled` and uses `reservation_cancel_pull` event_type to bypass deduplication
- **Phase A.5 Pagination**: Tüm sayfalar dolaşılıyor (sadece page 1 değil), 50+ modifikasyonda da tespit çalışıyor
- **Exploder Leak Fix**: `explode_multi_room_reservation` üst seviye `state/cancel_reason` sızmasını temizliyor — kısmi iptalde kademeli yayılma ÖNLENDI
- **Phase B Cascade Fix**: `timestamp_changed` yolunda aktif odalar korunuyor, üst seviye iptal yayılmıyor
- **Phase A.6**: Auto-sync detected modifications to PMS bookings — every cycle
- **Phase B**: Full catch-up every 10th cycle (~5 min) — safety net
- **Unified Callback**: `/api/channel-manager/hotelrunner/callback` — single endpoint for HotelRunner "Dönüş adresi"
- Unassigned imports, notifications
- **Bildirim Sistemi (Apr 2026)**:
  - `read` alan normalizasyonu (is_read → read uyumluluk)
  - `mark-all-read` endpoint (toplu okundu)
  - `dedup_key` ile tekrarlayan bildirim önleme
  - Stale update guard ile ping-pong önleme
  - Pipeline'da iptal bildirimi oluşturma
  - NotificationBell: dialog açılınca otomatik okundu
  - Rezervasyon detayında sisteme düşme zamanı ve giriş/çıkış saatleri
- End-to-end verified webhook pipeline
- Per-room cancellation detection for multi-room reservations
- ARI push via query params (fix Apr 2026)
- Three-tier global/partial cancellation detection
- Auto-un-cancel guard: cancelled reservations never auto-revert to confirmed
- effective_state uses only state field + cancel_reason (not next_states)
- Rate limit aware push with 30s-capped retry and fail-fast polling (fix Apr 2026)
- **Push Retry Queue**: Automatic retry mechanism for failed pushes — enqueue, background worker, adaptive backoff. Manuel retry kaldırıldı, "Tümünü İptal Et" butonu eklendi (Apr 2026)
- **Rate Limit Cooldown & Auto-Retry System** (Apr 2026)
- **Background Push (Exely tarzı)** (Apr 2026)
- **Gün Filtrelemeli Push (Apr 2026)**
- **Otomatik Polling Yeniden Aktif (Apr 2026)**: 300s aralikla otomatik reservation pull
- **403 Fix + Connection Pooling** (Apr 2026)

### Calendar Vibrant Color Update (Apr 2026)
- Vibrant booking bar colors by status
- Blue-tinted room type headers
- Compact grid with bold reservation names and three-state occupancy dots

### VCC (Virtual Credit Card) Secure View (Apr 2026) — DONE
- OTA/Acente sanal kart bilgileri AES-256-GCM ile şifreli saklanıyor
- Otelci kart bilgilerini maksimum 3 kez görüntüleyebilir (API seviyesinde zorunlu)
- Atomic view counter ($lt koşulu ile race condition koruması)
- Rezervasyon detayında "Online Ödeme" sekmesi
- Kart ekleme formu, kart görsel kartı, kalan hak gösterimi
- 3 hak dolunca kalıcı kilitleme + kırmızı uyarı
- Her görüntüleme activity log'a yazılıyor (audit trail)

### Rate Manager Provider Toggle (Apr 2026) — DONE
- Exely ve HotelRunner rate manager sayfaları arasında hızlı geçiş toggle'ı
- Her iki sayfanın üst kısmında segmented control tarzı toggle
- Aktif provider beyaz arka plan + gölge, inaktif provider gri metin
- React Router ile SPA navigasyonu
- data-testid ile test edilebilir

### Rate Manager Oda Tipi Sil Butonu Kaldırma (Apr 2026) — DONE
- Fiyat/müsaitlik panelindeki oda tipi silme (Trash2) butonu her iki provider ekranından kaldırıldı
- BulkUpdatePanel.jsx, HRRateManager.jsx temizlendi

## Prioritized Backlog

### P2 (Medium)
- Real-time UI notifications for channel push results

### P3 (Low)
- Legacy HR v1 connector removal (after full verification)
- Channel Manager Dashboard — recent reservations, failed imports, connection health metrics
- Admin UI Panel for encryption management (view status, trigger migrations, check audit logs)
- Make unassigned reservations more prominent in calendar

### Refactoring
- hotelrunner_sync.py (~1000 satır) Phase A/Phase B bölünmesi
- hr_rate_manager_router.py (>1100 satır) bölünmesi

## Completed Refactoring
- hotelrunner_webhook.py monolith split DONE (Apr 2026)

## Key API Endpoints
- POST /api/channel-manager/hr-rate-manager/bulk-grid-update
- GET /api/channel-manager/hr-rate-manager/grid
- GET /api/channel-manager/hr-rate-manager/queue-status
- POST /api/channel-manager/hr-rate-manager/queue-retry
- DELETE /api/channel-manager/hr-rate-manager/queue-cancel/{item_id}
- POST /api/channel-manager/hotelrunner/sync/reservations/pull
- GET /api/channel-manager/hotelrunner/sync/status
- POST /api/channel-manager/hotelrunner/webhooks/reservations
- GET /api/security/pii/strict-mode/config
- GET /api/ops/field-encryption/status

## Key API Endpoints (VCC)
- POST /api/pms/reservations/{id}/vcc — Kart kaydet (şifreli)
- GET /api/pms/reservations/{id}/vcc/status — Durum sorgula (görüntüleme harcamaz)
- POST /api/pms/reservations/{id}/vcc/reveal — Kart detay aç (1/3 hak harcar)
- DELETE /api/pms/reservations/{id}/vcc — Kart sil

## 3rd Party Integrations
- AWS KMS (Encryption) — optional for production key management
- HotelRunner v2 — User Token active, LIVE MODE
- Exely (SOAP) — Provider credentials required

## Dependency Notes
- `emergentintegrations==0.1.0` requires `openai==1.99.9` and pulls `litellm` as transitive dep
- `litellm==1.83.2` installed with `--no-deps` to fix CVE-2026-35029 and CVE-2026-35030
- CI/CD: `bash backend/scripts/post_install.sh` after `pip install -r requirements.txt`

## Critical Constraints
- All responses in Turkish
- Latest test report: /app/test_reports/iteration_187.json
