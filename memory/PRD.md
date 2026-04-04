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
- 120-second polling with adaptive backoff (was 30s)
- Unassigned imports, notifications
- End-to-end verified webhook pipeline
- Per-room cancellation detection for multi-room reservations
- ARI push via query params (fix Apr 2026)
- Three-tier global/partial cancellation detection
- Auto-un-cancel guard: cancelled reservations never auto-revert to confirmed
- effective_state uses only state field + cancel_reason (not next_states)
- Rate limit aware push with 30s-capped retry and fail-fast polling (fix Apr 2026)
- **Push Retry Queue**: Automatic retry mechanism for failed pushes — enqueue, background worker, adaptive backoff. Manuel retry kaldırıldı, "Tümünü İptal Et" butonu eklendi (Apr 2026)
- **Rate Limit Cooldown & Auto-Retry System** (Apr 2026): 429 hatası alındığında:
  - Veriler yerel olarak kaydedilir
  - Push kuyruğa eklenir ve Retry-After süresine göre cooldown başlar
  - Otomatik retry planlanır (progressive backoff ile max 5 deneme)
  - UI'da countdown timer gösterilir
  - "Şimdi Dene" butonu cooldown sırasında devre dışı
  - Cooldown bitmeden API'ye istek gitmez (gereksiz 429'ları önler)
- **Background Push (Exely tarzı)** (Apr 2026): Tüm push'lar arka planda gönderilir
  - Kullanıcı anında yanıt alır (~0.15 saniye)
  - Push'lar arka planda sıralı olarak 2sn aralıklarla denenir (Exely ile aynı mantık)
  - HİÇ denenmeden kuyruğa atma kaldırıldı — önce gerçek push denenir
  - Sadece gerçek 429 rate limit alanlar kuyruğa eklenir ve otomatik retry planlanır
  - Rate limit alınca kalan push'lar da kuyruğa eklenir (gereksiz 429 önlenir)
- **Gün Filtrelemeli Push (Apr 2026)**: selected_days aktifken, HotelRunner API'nin `days[]` parametresi kullanılarak tek bir API çağrısında tüm seçili günler güncellenir
  - Eski: Her non-consecutive gün ayrı push → Nisan-Aralık arası 74+ API çağrısı
  - Yeni: Tek push + days[]=[0,6] → 1 API çağrısı per oda tipi (~74x hız artışı)
  - `update_room` provider metodu days[] query param desteği eklendi
  - Push kuyruğu (retry) da days bilgisini saklıyor
- **Otomatik Polling Devre Disi**: Surekli 120s polling yerine event-driven + manuel senkronizasyon mimarisi (Apr 2026). Booking olusturuldugunda outbox uzerinden otomatik push, diger zamanlarda sadece kullanici tetikli islemler.
- **Otomatik Polling Yeniden Aktif (Apr 2026)**: 300s (5 dakika) aralikla otomatik reservation pull. Adaptive backoff ile rate limit korunmasi. Push Queue Worker 120s aralikla otomatik retry.
- **403 Fix + Connection Pooling** (Apr 2026): Accept: application/json header + HTTP connection pooling (max 5 conn, 3 keepalive) ile WAF/rate limit engelleri çözüldü

### Calendar Vibrant Color Update (Apr 2026)
- Vibrant booking bar colors by status
- Blue-tinted room type headers
- Compact grid with bold reservation names and three-state occupancy dots

## Prioritized Backlog

### P1 (High)
- None critical at this time

### P3 (Low)
- Rate Manager quick toggle (Exely/HotelRunner)
- Legacy HR v1 connector removal (after full verification)
- Channel Manager Dashboard — recent reservations, failed imports, connection health metrics
- Admin UI Panel for encryption management (view status, trigger migrations, check audit logs)
- Make unassigned reservations more prominent in calendar

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

## 3rd Party Integrations
- AWS KMS (Encryption) — optional for production key management
- HotelRunner v2 — User Token active, LIVE MODE
- Exely (SOAP) — Provider credentials required

## Dependency Notes
- `emergentintegrations==0.1.0` requires `openai==1.99.9` and pulls `litellm` as transitive dep
- `litellm==1.83.2` installed with `--no-deps` to fix CVE-2026-35029 and CVE-2026-35030
- CI/CD: `bash backend/scripts/post_install.sh` after `pip install -r requirements.txt`
- Dockerfile: `python -m pip` kullanılmalı (`pip` değil) — `--prefix=/install` ile pip kendini upgrade edince PATH'ten silinir
- Never run plain `pip freeze > requirements.txt` — it will re-add dev tool dependencies

## Critical Constraints
- All responses in Turkish
- Latest test report: /app/test_reports/iteration_184.json
- Latest change: HotelRunner otomatik polling yeniden aktif edildi (300s aralik, adaptive backoff) (Apr 2026)
