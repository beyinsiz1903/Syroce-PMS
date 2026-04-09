# Syroce PMS - Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS with unified channel manager. Build a unified Rate & Availability Manager that handles both HotelRunner and Exely. Syroce B2B API infrastructure for agency automation system integration — agencies can authenticate via API key and access hotel content, availability, rates, create/manage reservations through the same channel manager architecture.

## User Language
Turkish (All responses must be in Turkish)

## Core Architecture
- Frontend: React (Vite) + Shadcn UI
- Backend: FastAPI + MongoDB
- Channel Integrations: HotelRunner v2 API, Exely SOAP API, Syroce B2B API
- Encryption: AES-256-GCM for credentials
- B2B Auth: API Key (SHA256 hashed, X-API-Key header)
- Tenant Isolation: TenantAwareDBProxy with STRICT_TENANT_MODE=true

## What's Been Implemented

### Unified Rate Manager (DONE)
### Role-Based Delete Protection on Content Distribution (DONE - 2026-04-08)
### Syroce B2B API (DONE - 2026-04-08)
### B2B API Documentation Page (DONE - 2026-04-08)
### Webhook System (DONE - 2026-04-08)
### Deployment Fixes (DONE - 2026-04-08)
### CI Test Fixes — TenantViolationError (DONE - 2026-04-09)
### RMS Module — Backend Endpoint Fixes (DONE - 2026-04-08)
### Advanced Menu Icon Fix (DONE - 2026-04-08)
### Advanced Module Consolidation (DONE - 2026-04-08)

### RMS Module — Complete Rewrite to Internal-Data-Driven System (DONE - 2026-04-08)
- **Motivation**: User decided not to rely on competitor pricing (web scraping is fragile, OTA rate shopping services cost $75-400/mo). RMS now uses only internal hotel data.
- **7-Factor Pricing Algorithm**:
  1. Doluluk Orani (Occupancy) — 25% weight
  2. Rezervasyon Hizi / Pickup — 20% weight
  3. Lead Time (Days to arrival) — 15% weight
  4. Haftanin Gunu & Mevsimsellik — 15% weight
  5. Iptal Orani (Cancellation Rate) — 10% weight
  6. Kanal Bazli Performans (Channel Performance) — 10% weight
  7. Gecmis Yil Karsilastirma (YoY) — 5% weight
- **New Backend Endpoints**:
  - `GET /api/rms/dashboard-kpis` — Comprehensive KPIs (doluluk, ADR, RevPAR, pickup, cancel rate, channels, daily trend)
  - `POST /api/rms/generate-pricing` — New 7-factor pricing engine
  - `GET/POST/PUT/DELETE /api/rms/yield-rules` — Yield rules CRUD
  - `GET/POST/PUT/DELETE /api/rms/seasonal-calendar` — Seasonal calendar CRUD
  - `GET /api/rms/channel-performance` — Monthly channel breakdown
- **New Frontend Components**:
  - `RMSModule.jsx` — Complete rewrite: KPI cards (TRY), doluluk trendi chart, kanal dagilimi doughnut, oda tipi performansi bar chart, fiyat onerileri table, kanal detay tablosu
  - `YieldRulesPanel.jsx` — Yield rules CRUD UI with priority, conditions, actions
  - `SeasonCalendarPanel.jsx` — Seasonal calendar with visual timeline + CRUD
  - `GelirYonetimiPage.jsx` — 4 tabs: Dashboard, Yield Kurallari, Sezon Takvimi, Autopilot
- **Seed Data**: auto_seed.py updated with:
  - TRY prices (Standard: 4500, Deluxe: 6800, Superior: 9200, Suite: 14000)
  - 265 bookings (6 months history with channel distribution)
  - 6 room types, 5 yield rules, 6 seasonal calendar entries
- **Test Result**: Backend 16/16, Frontend 100% — iteration_200.json

### Messaging Dashboard Layout Fix (DONE - 2026-04-08)
- Fixed missing Layout wrapper on MessagingDashboard — top navigation was disappearing when navigating to `/messaging-dashboard`
- Wrapped component in `<Layout>` to match other consolidated page patterns

### Messaging Center — Email (SMTP) & WhatsApp (Meta Business API) Integration (DONE - 2026-04-08)
- **No third-party intermediaries** — Direct SMTP for email, Meta WhatsApp Business Cloud API for WhatsApp
- **Backend**: SMTPEmailProvider + WhatsAppProvider with sandbox/live modes, settings API, template CRUD, send, delivery logs, metrics
- **9 Pre-built Templates**: 5 WhatsApp (Hos Geldiniz, Yol Tarifi, Tesis Bilgileri, Puan/Degerlendirme, Iletisim) + 4 Email (Rezervasyon Onay, Fatura, Kampanya, Check-out Tesekkur)
- **Frontend**: 6-tab dashboard (Mesaj Gonder, Sablonlar, Otomasyon, Loglar, Metrikler, Ayarlar)
- **Settings Panel**: SMTP (host, port, user, pass, from_email, TLS) + WhatsApp (access_token, phone_number_id) configuration
- **Sandbox Mode**: Demo providers auto-seeded, simulated send — ready for real credentials
- **New Endpoints**: `/api/messaging-center/settings`, `/api/messaging-center/settings/email`, `/api/messaging-center/settings/whatsapp`, `/api/messaging-center/send`, `/api/messaging-center/seed-demo`

### Messaging Automation — Event-Triggered Messaging (DONE - 2026-04-08)
- **Booking event hooks**: check-in/check-out/confirm status changes trigger automatic messages to guests
- **5 Default Rules**: Rez Onay (email), Check-in Oncesi Yol Tarifi (WhatsApp), Hos Geldiniz (WhatsApp), Check-out Tesekkur (email), Degerlendirme Linki (WhatsApp)
- **Automation Engine**: `fire_booking_event()` hooked into `UpdateReservationService` and `approve_booking`
- **Frontend**: Otomasyon tab with rule CRUD, enable/disable toggle, test trigger, summary cards, "Nasil Calisir?" guide
- **New Endpoints**: `/api/messaging-center/automation/triggers`, `/api/messaging-center/automation/rules` (CRUD), `/api/messaging-center/automation/test/{id}`
- **Test Result**: Backend 12/13 (1 skipped - no pending bookings), Frontend 100% — iteration_202.json

### Pre-Arrival Daily Scheduler (DONE - 2026-04-08)
- **Background Worker**: `PreArrivalScheduler` runs every 6h (configurable), scans confirmed bookings with tomorrow's check-in date
- **Deduplication**: Checks `delivery_logs` to avoid re-sending `pre_arrival` messages for same booking
- **In-App Notifications**: Creates notifications on successful/failed automation sends (visible in NotificationBell)
- **Frontend**: Scheduler card at bottom of Otomasyon tab with Start/Stop/Simdi Tara controls and metrics
- **New Endpoints**: `/api/messaging-center/scheduler/status`, `/scheduler/start`, `/scheduler/stop`, `/scheduler/run-now`
- **Test Result**: Backend 13/13, Frontend 100% — iteration_203.json

### Real-time Messaging Activity Feed (DONE - 2026-04-08)
- **Unified Activity Feed**: Combines automation notifications + delivery logs into single timeline
- **Auto-Refresh**: Frontend polls every 10 seconds for near-real-time updates
- **7-Tab Dashboard**: Added "Aktivite" tab showing color-coded delivery statuses
- **Automation Notifications**: Every automation trigger (success/failure) creates in-app notification
- **New Endpoint**: `/api/messaging-center/activity?limit=N`
- **Test Result**: Backend 13/13, Frontend 100% — iteration_203.json

### i18n (Internationalization) Fix — Dashboard & Navigation (DONE - 2026-04-09)
- **Problem**: Selecting any language other than Turkish still showed Turkish text everywhere
- **Root Causes Fixed**:
  1. `navGroups` translations were completely missing from all locale files — navigation groups fell back to hardcoded Turkish labels
  2. Many `navKeys` were missing from en.json/tr.json — 30+ keys added
  3. `CommandCenter.jsx` had all text hardcoded in Turkish — converted to use `useTranslation()` with 15+ translation keys
  4. `PushSubscriptionManager.jsx` had hardcoded Turkish status labels and toast messages — converted to i18n
  5. `Dashboard.jsx` Migration Observability card had hardcoded Turkish — converted to `t()` calls
  6. AI Briefing endpoint (`/ai/dashboard/briefing`) always generated Turkish content — added `lang` query parameter, updated AI service prompts and fallback text to be language-aware
- **Files Modified**: CommandCenter.jsx, PushSubscriptionManager.jsx, Dashboard.jsx, navItems.jsx (labels used as fallback), endpoints.py, service.py, all 10 locale JSON files
- **Test Result**: Frontend 100% — iteration_204.json


### Comprehensive Report Center (DONE - 2026-04-09)
- **Motivation**: User requested 5-star hotel quality reporting center with easy navigation and access to every possible report
- **Complete redesign of BasicReports.jsx** as professional Report Center with categorized sidebar
- **19 report sections across 11 categories**:
  1. Genel Bakış (Executive Overview) — KPI summary, daily movement, mini charts, period comparison
  2. Gelir Raporu — Revenue trend (30 days), room type revenue, daily/weekly/monthly KPIs
  3. ADR & RevPAR Analizi — ADR/RevPAR detail cards, 14-day performance chart
  4. Dönem Karşılaştırma — Period cards (7d/30d/prev30d/YoY), revenue change metrics
  5. Doluluk Raporu — Occupancy trend with dual-axis chart (% + rooms)
  6. Oda Tipi Analizi — Room type distribution pie, occupancy bar chart, detail table
  7. Misafir Listesi — Full guest list with search functionality
  8. Milliyet Dağılımı — Nationality pie chart + country details list
  9. Giriş / Çıkış — Today's arrivals/departures tables, in-house guest count
  10. No-Show & İptaller — No-show and cancellation lists with KPIs
  11. Oda Durumu — Live room status pie chart with colored stat boxes
  12. Housekeeping — HK performance bars (completed/pending/in-progress)
  13. Kanal Dağılımı — Channel source pie + revenue bar + detail table
  14. Kaynak Analizi — Source comparison cards and chart
  15. Ödemeler — Payment method pie chart + payment details
  16. Maliye Listesi — Official guest list with TC/Passport column
  17. Polis Bildirimi — Police report list with ID details
  18. Departman Özeti — Multi-department summary (Front Office, HK, Technical, Finance)
  19. F&B Raporu — Food & Beverage revenue and share metrics
- **New shared component library**: `/app/frontend/src/pages/reports/ReportHelpers.jsx`
  - KPICard, StatBox, SectionHeader, EmptyState, CustomTooltip components
  - formatCurrency, formatNumber, formatPercent, calcChange utilities
- **Professional sidebar navigation** with category headers, active state highlighting, mobile dropdown fallback
- **Test Result**: Frontend 95% pass — iteration_205.json (all 19 sections navigable and functional)

### Reports Navigation Cleanup & Maliye Raporu Consolidation (DONE - 2026-04-09)
- **Problem**: Reports dropdown had 3 confusing tabs (Reports, Advanced Reports, Report Builder) with duplicate Maliye Raporu appearing in both BasicReports sidebar and the Excel download page (Reports.jsx)
- **Solution**: 
  1. Removed "Advanced Reports" (Reports.jsx) from navigation — it was a redundant Excel download page with confusing naming
  2. Simplified navigation to just 2 items: "Raporlar" (BasicReports) + "Rapor Oluşturucu" (ReportBuilder)
  3. Old /app/gelismis-raporlar URL now redirects to BasicReports
- **Files Modified**: navItems.jsx, BasicReports.jsx (renderOfficial), routeDefinitions.jsx
- **Test Result**: Frontend 8/8 tests passed (100%) — iteration_206.json

### Maliye Listesi Inline Entegrasyon (DONE - 2026-04-09)
- **Problem**: Maliye Listesi bölümü ayrı bir sayfaya yönlendiriyordu. Kullanıcı tüm işlevselliğin aynı rapor sayfasında inline olarak görünmesini istedi.
- **Solution**: 
  1. `renderOfficial()` fonksiyonu tamamen yeniden yazıldı — artık tarih seçimi, veri çekme, filtreleme, CSV indirme, yazdırma ve tam tablo doğrudan inline olarak gösteriliyor
  2. Özet kartları (Toplam Kayıt, Toplam Kişi, Toplam Tutar, Seçili Tarih) veri yüklendikten sonra görünüyor
  3. Ayrı sayfa yönlendirmesi kaldırıldı, OfficialGuestList.jsx'deki tüm işlevsellik BasicReports.jsx içine taşındı
- **Files Modified**: BasicReports.jsx (renderOfficial, state variables, fetch/export/print functions)
- **Test Result**: Frontend 8/8 tests passed (100%) — iteration_207.json

## Pending / Known Issues
- litellm CVE-2026-35030: Suppressed in `.trivyignore`. Upgrade to >=1.83.0 blocked by emergentintegrations dependency chain.

### Guest Search Input Visibility Fix (DONE - 2026-04-09)
- Fixed search input in Misafir Listesi (Guest List) section of Reports module - added `bg-white`, `border-gray-300`, `text-gray-900` for clear visibility
- Resolved duplicate `data-testid` issue caused by dual mobile/desktop rendering - added `data-testid="reports-mobile-content"` and `data-testid="reports-desktop-content"` wrappers
- Search filtering verified working (tested with "Deniz" query, correctly returned 6 filtered results)

### Infrastructure Tab Audit & Consolidation (DONE - 2026-04-09)
- **Audit**: All 11 Infrastructure tabs analyzed — live data connectivity, completeness, API status, functional overlap
- **Bug Fix 1**: Security Hardening backend HTTP 500 — `tenant_scoped_queries.py` used tenant-proxied `db` for admin isolation check → `TenantViolationError`. Fixed with `_raw_db`.
- **Bug Fix 2**: PII Strict Mode frontend URL bug — missing `/api` prefix and base URL in axios calls. Fixed.
- **Consolidation**: Removed 3 overlapping tabs from nav:
  - `Observability` → System Health already covers it
  - `PII Strict Mode` → Merged as "PII Koruma" tab in Security Hardening
  - `Infrastructure Hardening` → Merged as "Altyapı" tab in Security Hardening
- **Result**: Infrastructure dropdown: 11 → 8 items. Direct URLs still work standalone.
- **Test Result**: Backend 7/7, Frontend 100% — iteration_208.json

### Enterprise Live & Platform Scaling Overlap Resolution (DONE - 2026-04-09)
- **Problem 1**: Enterprise Live had a "Mesajlasma" tab (simple provider health + quick send) that overlapped with the full MessagingDashboard (7 tabs: send, templates, automation, activity, logs, metrics, settings).
- **Solution 1**: Removed MessagingPanel and messaging tab from EnterpriseLiveDashboard.jsx. Enterprise Live now has 3 tabs: Canli Operasyon, Oto-Fiyatlama, Entegrasyonlar.
- **Problem 2**: Platform Scaling had a "Revenue ML" tab (demand forecast, price optimization, conversion rates, at-risk bookings) that overlapped with Analitik & Raporlar (ML scheduler + report export).
- **Solution 2**: Extracted RevenueMLPanel into standalone component (RevenueMLPanel.jsx). Added as 1st tab in AnalitikRaporlarPage. Removed Revenue ML tab from PlatformScalingDashboard. Platform Scaling now has 4 tabs: Genel Bakis, Event Mimari, Multi-Property, CompSet Analiz. Analitik & Raporlar now has 3 tabs: Revenue ML, Rapor Disa Aktarma, ML Zamanlayici.
- **Files Modified**: EnterpriseLiveDashboard.jsx, PlatformScalingDashboard.jsx, AnalitikRaporlarPage.jsx, RevenueMLPanel.jsx (new)
- **Test Result**: Frontend 7/7 (100%) — iteration_209.json

### Operational Reliability — Webhook Retry + Ops Telemetry + Channel Ops Dashboard (DONE - 2026-04-09)
- **Program 1: Delivery Reliability**
  - **Webhook Automatic Retry**: Replaced fire-and-forget `_deliver_webhook` with exponential backoff retry (max 5 attempts: 2s, 4s, 8s, 16s, 32s)
  - **DLQ (Dead Letter Queue)**: Terminal failures → `webhook_dlq` collection for manual retry
  - **Delivery Tracking**: Each delivery records `attempt_count`, `next_retry_at`, `last_error`, `idempotency_key`, full attempt history
  - **Idempotency Key**: SHA256-based deduplication per webhook+event+delivery
  - **New Service**: `webhook_retry_service.py` — `deliver_webhook_with_retry()`, `fire_webhooks_with_retry()`, `retry_dlq_item()`
- **Program 2: Operational Observability**
  - **Ops Event Model**: `ops_events` collection stores all operational lifecycle events
  - **Event Types**: `webhook.delivery.started/succeeded/retrying/terminal_failure/dlq`, `push.started/queued/throttled/succeeded/failed_terminal`, `rate_limit.active/cooldown`, `import.started/completed/failed`, `channel.health_changed`
  - **In-App Notifications**: Critical/warning ops events auto-create notifications (appear in NotificationBell)
  - **HotelRunner 429 Visibility**: Rate limit status endpoint exposes throttle state, events count, last 429 timestamp, impacted pushes
  - **Channel Health**: Per-connector health calculation (healthy/degraded/critical) based on push success rate and import failures
- **Thin Channel Ops Dashboard v1** — 4-tab frontend (`/channel-ops`):
  - **Genel Bakış**: KPI cards (total/succeeded/failed/retrying/DLQ/throttle), channel status grid, recent failures, last successful pushes, recent imports
  - **Webhook Teslimat**: DLQ with manual retry buttons, full delivery history table
  - **Kanal Sağlığı**: HotelRunner rate limit status panel, per-connector health detail cards
  - **Olay Akışı**: Operational event timeline with severity badges, expandable details, correlation IDs
  - Auto-refresh every 15 seconds
- **New Backend Files**: `ops_event_emitter.py`, `webhook_retry_service.py`, `ops_events_router.py`
- **Modified**: `b2b_api.py` (webhook delivery replaced with retry service), `server.py` (router registration), `NotificationBell.jsx` (ops_event icon), `navItems.jsx`, `routeDefinitions.jsx`, locale files
- **New Endpoints**:
  - `GET /api/ops-events/list` — Query ops events with severity/type/channel filters
  - `GET /api/ops-events/webhook-deliveries` — Delivery status with summary stats
  - `GET /api/ops-events/webhook-dlq` — DLQ items with counts
  - `POST /api/ops-events/webhook-dlq/{id}/retry` — Manual DLQ retry
  - `GET /api/ops-events/rate-limit-status` — HotelRunner rate limit info
  - `GET /api/ops-events/channel-health` — Per-connector health summary
  - `GET /api/ops-events/dashboard-summary` — Full dashboard data in single call
- **Test Result**: Backend 8/8 (100%)

## Future / Backlog (P2+)
- ~~Automatic retry mechanism with exponential backoff for failed webhook deliveries~~ → DONE (2026-04-09)
- B2B Analytics Dashboard (agency API key usage, booking rates, top queries)
- ~~Channel Manager Dashboard (reservations, failed imports, push queue, health)~~ → DONE (2026-04-09)
- Admin UI Panel for encryption management
- Make unassigned reservations more prominent in calendar
- Improve Auto Room Mapping (capacity + base price matching)
- Refactor: BasicReports.jsx (>1200 lines) — component extraction
- Refactor: hotelrunner_sync.py (~1000 lines)
- Refactor: Evaluate deprecation of legacy hr_rate_manager_router.py and rate_manager_router.py
- Real competitor price integration via SerpApi or OTA Insight (when budget allows)
- Automated Email Scheduler for Reports (daily/weekly report dispatch)
- Similar audit/consolidation for Operations, Channels Admin navigation groups

## Key DB Collections
- `cm_connectors` — Encrypted channel credentials
- `hotel_content` — Agency data and rates mapping
- `users` — User accounts with roles
- `agency_api_keys` — B2B API keys (SHA256 hashed)
- `agency_rate_calendar` — Agency-specific rate data
- `room_types` — Room type definitions with TRY base/min/max rates
- `yield_rules` — Automatic pricing rules (condition-action pairs)
- `seasonal_calendar` — Season definitions with rate multipliers
- `rms_pricing_recommendations` — Generated pricing recommendations
- `bookings` — Reservations with channel, room_type, base_rate fields
- `ops_events` — Operational telemetry events (webhook lifecycle, push status, rate limits)
- `webhook_deliveries` — Webhook delivery records with retry state and attempt history
- `webhook_dlq` — Dead letter queue for terminal webhook delivery failures

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/unified-rate-manager/push-providers`
- `POST /api/b2b/api-keys` / `GET /api/b2b/api-keys/{agency_id}`
- `GET /api/b2b/content` / `GET /api/b2b/availability` / `GET /api/b2b/rates`
- `POST /api/b2b/reservations` / `GET /api/b2b/reservations`
- `POST /api/b2b/webhooks` / `GET /api/b2b/webhooks` / `DELETE /api/b2b/webhooks/{id}`
- `GET /api/rms/dashboard-kpis` / `GET /api/rms/channel-performance`
- `POST /api/rms/generate-pricing` / `POST /api/rms/apply-recommendations`
- `GET/POST/PUT/DELETE /api/rms/yield-rules`
- `GET/POST/PUT/DELETE /api/rms/seasonal-calendar`
- `GET /api/messaging-center/settings` / `POST .../settings/email` / `POST .../settings/whatsapp`
- `GET/POST/PUT/DELETE /api/messaging-center/templates`
- `POST /api/messaging-center/send` / `GET /api/messaging-center/delivery-logs`
- `GET /api/messaging-center/metrics` / `POST /api/messaging-center/seed-demo`
- `GET/POST /api/messaging-center/scheduler/status` / `/scheduler/start` / `/scheduler/stop` / `/scheduler/run-now`
- `GET /api/messaging-center/activity`
- `GET /api/ops-events/list` / `GET .../webhook-deliveries` / `GET .../webhook-dlq`
- `POST /api/ops-events/webhook-dlq/{id}/retry`
- `GET /api/ops-events/rate-limit-status` / `GET .../channel-health` / `GET .../dashboard-summary`
