# Syroce PMS - Hotel Property Management System

## Project Overview

Enterprise-grade multi-tenant Hotel Property Management System (PMS) with AI-powered features for hotel operations, reservations, housekeeping, financial folios, and OTA channel management. Features a **Property Type Profiling System** that adapts the entire PMS for any accommodation type — from 1-room pensions to 1000-room luxury resorts.

## Architecture

### Frontend (Primary - Running on Port 5000)
- **Framework**: React 19 + Vite 8
- **Styling**: Tailwind CSS + shadcn/ui
- **State**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **i18n**: i18next (10 languages: EN, TR, DE, FR, ES, IT, AR, PT, RU, ZH) with RTL support for Arabic. Full i18n coverage on all PMS components + Migration Observability panel.
- **Package Manager**: Yarn 1.22.22
- **Testing**: Vitest + @testing-library/react + jsdom (vitest.config.js, `yarn test`)

### Backend (FastAPI - Port 8000)
- **Framework**: FastAPI (Python 3.11+)
- **Database**: MongoDB 7.0+ (motor for async, local mongod on /tmp/mongodb-data)
- **Cache**: Redis (local redis-server on port 6379)
- **Tasks**: Celery with Redis
- **Testing**: pytest + pytest-asyncio (tests/ directory, `python -m pytest`)
- **Auth**: JWT + AES-256-GCM + RBAC
- **Startup**: `bash backend/start.sh` (starts MongoDB, Redis, then uvicorn)

## Directory Structure

```
frontend/          - React + Vite frontend application
backend/           - FastAPI Python backend
  bootstrap/       - App wiring and DI
  channel_manager/ - OTA adapters (Exely, HotelRunner)
  controlplane/    - Operational monitoring
  core/            - Entitlements, metering, crypto
  domains/         - DDD modules (pms, guest, revenue, ai, hr)
  modules/         - Business logic (folio, inventory, reservations)
  workers/         - Background tasks
infra/             - Prometheus/Grafana/K8s config
deploy/            - Deployment scripts and Nginx configs
docs/              - ADRs and playbooks
```

## Running the App

Two workflows:
1. **Start application** — Frontend dev server on port 5000 (`cd frontend && yarn run start`)
2. **Backend API** — MongoDB + Redis + FastAPI on port 8000 (`bash backend/start.sh`)

Vite proxies `/api` requests to backend at `http://localhost:8000`.

Demo login: `demo@hotel.com` / `demo123` (super_admin role)

JWT_SECRET is set as a persistent environment variable (shared). Tokens survive backend restarts and last 7 days (168 hours). Users stay logged in until they explicitly log out or the token expires.

## Deployment

Configured as a static deployment:
- Build: `cd frontend && yarn install && yarn build`
- Public dir: `frontend/build`

## API Call Conventions

Two URL patterns coexist in frontend code:

1. **axios calls** (via `axiosConfig.js` with `baseURL="/api"`): Use relative paths WITHOUT `/api/` prefix.
   - Example: `axios.get('/notifications/list')` → resolves to `/api/notifications/list`
   - Channel manager tabs using `${API}` (= `/channel-manager/v2`): `axios.get(`${API}/delivery/channels`)` → `/api/channel-manager/v2/delivery/channels`

2. **fetch calls** (native, no baseURL): Must include `/api/` prefix explicitly.
   - Example: `fetch('/api/security/summary', ...)` 
   - Helper wrappers like `fetchAPI` in some files construct the full URL

**Common mistake**: Using `/api/xxx` with axios → double prefix `/api/api/xxx`. Using `/xxx` with fetch → misses `/api/` prefix entirely.

## Key Features

- Front desk management and reservations (overstay warnings, no-show list, walk-in quick form, group batch check-in)
- Housekeeping module
- Financial folios (direct charge posting, folio print, proforma invoice)
- **Cashier Module** (`CashierTab.jsx`) — shift open/close, cash count, Z-report, shift history, secure handover with credential verification
- **Upsell & Gelir Optimizasyonu** (`UpsellTab.jsx`) — AI-powered upsell offers (room upgrade, early check-in, late checkout, transfer), booking-based offer generation, accept/reject with folio posting, revenue insights with real KPIs (occupancy, ADR, RevPAR), offer history with filtering
- **Mesaj Merkezi** (`MessagingTab.jsx`) — Email/WhatsApp messaging with guest search, template selection, delivery logs history from backend, automation rules (toggle/test/delete), KPI cards (total sent, email, whatsapp, automation count), demo data seeding; backend endpoints: `/messaging-center/templates`, `/send`, `/delivery-logs`, `/metrics`, `/automation/rules`, `/seed-demo`
- **Raporlar & Analiz** (`ReportsTab.jsx`) — 4 KPI cards (Doluluk/ADR/RevPAR/Toplam Gelir in TL), 4 sub-tabs: Günlük Özet (daily flash + summary + gelir dağılımı pie chart), Tahmin (7-gün bar+line, 30-gün area chart from forecast API), Pazar Segmenti (segment tablosu + fiyat tipi dağılımı), Kat Hizmetleri (görev KPIs + personel performans horizontal bar chart + detaylı tablo). Uses recharts (BarChart, LineChart, AreaChart, PieChart). All 9 backend report endpoints mapped correctly.
- **Flash Rapor** (`FlashReportPanel.jsx`) — Günlük flash rapor: 4 KPI kartı (Doluluk/ADR/RevPAR/Toplam Gelir ₺), 7 operasyonel kart (Giriş/Çıkış/In-House/No-Show/Walk-In/İptal/Overstay), Departman Bazlı Gelir (renk kodlu bar + PieChart), Tahsilat Durumu (toplam/tahsil/açık bakiye + progress bar), yazdırma desteği. Backend `/reports/flash-report` endpoint düzeltildi (değişken atama + return eklendi). Fallback: API başarısız olursa props'tan hesaplar.
- **Room Timeline** (`RoomTimelineView.jsx`) — Gantt/timeline view with rooms on Y-axis, booking bars colored by status
- **Laundry Management** (`LaundryTab.jsx`) — order tracking, status updates, room-based laundry orders
- **Meeting Room Booking** (`MeetingRoomTab.jsx`) — room inventory, reservations, setup types, equipment tracking
- **Print Templates** (`PrintTemplates.jsx`) — registration card, folio print, proforma invoice with hotel header
- **Room Features** (`RoomFeaturesPanel.jsx`) — DND toggle, connecting rooms, minibar quick entry, early/late checkout rules
- **Guest Management** — Turkish UI, multi-field search (name/phone/email/ID), guest merge, preference editing
- **Complaint Management** (Service Recovery) — full CRUD + resolve/escalate, integrated with rooms/guests/bookings
- Channel Manager (OTA sync with Exely, HotelRunner)
- Control Plane for operational monitoring
- **Displacement Analysis** (`DisplacementAnalysis.jsx`) — 4-tab UI: Market Overview (occupancy forecast, channel mix, risk indicators), Scenario Builder (group booking analysis with displaced/proposed/ancillary revenue, ROI, RevPAR delta, daily breakdown), Compare Scenarios (side-by-side up to 5 scenarios), History (saved analyses). Backend: `displacement_engine.py` (live MongoDB queries for occupancy, ADR, cancellation rate, DOW pricing) + `displacement_analysis.py` router (5 endpoints: `/analyze`, `/market-overview`, `/compare`, `/save`, `/history`). 72 i18n keys across all 10 languages.
- **Travel Agent AR/AP** (`TravelAgentARAP.jsx`) — 4-tab UI: Overview (KPIs: total receivable/payable/paid, collection rate, overdue counts, agency summary table), Agency Ledger (expandable per-agency view with commission entries, payment history, record payment, account statement, create payment plan), Payment Plans (installment tracking with mark-paid), Aging Report (current/30/60/90/90+ day buckets). Backend: `travel_agent_arap.py` router (6 endpoints: `/summary`, `/aging`, `/transactions/{id}`, `/payment`, `/payment-plans`, `/statement/{id}`). Demo seed: 5 agencies with ~50 bookings and payment transactions. 83 i18n keys across all 10 languages.
- **Syroce Open API** (`B2BApiDocs.jsx` + `b2b_api.py`) — Comprehensive REST API with 19 module groups (22 doc sections): Content, Availability, Rates, Reservations, Guest/Loyalty, Housekeeping, KBS/Police Notification, Passport/ID Scanning, Lost & Found, Wake-up Calls, Guest Journey, Concierge, Spa, MICE/Groups, Folio/Billing, Webhooks + Quick Start (5-step guide, Python/JS SDK), Auth (key lifecycle table, best practices), Error Codes (HTTP 200–500 table), Rate Limits (per-type: Read 120/min, Write 30/min, Delete 10/min, Bulk 5/min + retry pattern), Pagination (limits/filters/date-time reference). All behind API key auth (X-API-Key header, SHA-256 hashed). Frontend docs page at `/b2b/docs` with EN/TR bilingual support (1070 lines). Input validation with Pydantic Field constraints on financial writes.
- AI-driven dynamic pricing and forecasting
- WebSocket real-time updates
- Multi-tenant architecture
- 10-language internationalization (EN, TR, DE, FR, ES, IT, AR, PT, RU, ZH)

- **Concierge Desk** (`ConciergeDesk.jsx`) — restoran rez., transfer, tur, bilet, vale parking, paket takibi, kasa kiralama, uyandırma servisi
- **Banquet & Event Order** (`BanquetEventOrder.jsx`) — BEO oluşturma/yazdırma, salon seçimi, menü, AV ekipman, dekorasyon, faturalama
- **Guest Preferences** (`GuestPreferences.jsx`) — yastık tipi, oda sıcaklığı, diyet, alerji, VIP seviye, doğum günü/yıldönümü
- **Routing Instructions** (`RoutingInstructions.jsx`) — otomatik masraf yönlendirme kuralları (oda→şirket, ekstra→misafir), percentage-based split validation
- **Manager Daily Report** (`ManagerDailyReport.jsx`) — yazdırılabilir günlük rapor, milliyet dağılımı, konaklama süresi analizi
- **Revenue Controls** (`RevenueControls.jsx`) — engel fiyat (BAR), gün bazlı fiyatlandırma matrisi, overbooking yönetimi, walk-out tazminat
- **KBS/GIKS** (`KBSNotification.jsx`) — emniyet/jandarma misafir bildirimi, toplu gönderim, eksik bilgi takibi
- **KVKK/GDPR** (`KVKKManager.jsx`) — saklama politikaları, veri talepleri (erişim/silme/düzeltme), rıza yönetimi, denetim izi

## PMS Module (PMSModule.jsx — 800 lines)
Reduced from 2499 lines via dialog extraction. 22 tab layout with lazy-loaded tabs.

### Extracted PMS Dialogs (in `frontend/src/components/pms/`)
- `FolioDialog.jsx` — Guest folio charges/payments
- `FolioViewDialog.jsx` — Full folio management with post-charge/post-payment sub-dialogs
- `RoomCreateDialog.jsx` — Room creation form
- `RoomImageUploadDialog.jsx` — Room photo upload
- `GuestCreateDialog.jsx` — Guest registration form
- `BulkDeleteRoomsDialog.jsx` — Bulk room deletion with confirmation

### Invoice Module (InvoiceModule.jsx — 427 lines)
Reduced from 1309 lines via dialog extraction.

### Extracted Invoice Dialogs (in `frontend/src/components/invoice/`)
- `InvoiceFormDialog.jsx` — Invoice creation with line items and additional tax calculations
- `AccountingDialogs.jsx` — ExpenseDialog, SupplierDialog, BankAccountDialog, InventoryDialog

## Authentication Overhaul (Apr 2026 — hotel_id + username)
- **Login model**: Hotel staff now authenticate with `hotel_id` (6-digit unique numeric string) + `username` (unique within tenant) + `password`. Guests still use email + password (legacy path retained in `/api/auth/login`).
- **Demo credentials**: `hotel_id=100001`, `username=demo`, `password=demo123` (tenant `57986e4f-7977-44c9-bed9-05aadf38853b`). Shown in an info banner on the login form with a "Demo bilgileri otomatik doldur" button.
- **Schemas** (`backend/models/schemas/identity.py`): `Tenant.hotel_id`, `User.username`, `UserLogin` (hotel_id|username|email + password), `ChangePasswordRequest`.
- **Migration**: `backend/scripts/migrate_hotel_id_username.py` — idempotent backfill (assigns hotel_id and derives username from email local-part). Unique indexes: `tenants.hotel_id` (sparse), `users.(tenant_id, username)` partial.
- **New endpoints**:
  - `POST /api/auth/change-password` — authenticated; verifies current, updates hash, invalidates login cache, audit-logged.
  - `POST /api/auth/reset-password-by-token` — link-based reset; consumes one-time token from `password_reset_codes`.
- **Email** (`backend/core/email.py`): Generic `send_email(to, subject, html)` helper using **Resend** SDK (`RESEND_API_KEY` secret). Falls back to console logging when key missing or send fails. `render_password_reset_email` produces branded TR-localized HTML with both a clickable reset link and a 6-digit code as backup. Forgot-password endpoint generates a 30-min token, stores it alongside the legacy code, and emails it.
  - **Resend caveat**: while using the default sender (`onboarding@resend.dev`), Resend's test mode only delivers to the account owner's verified address. To enable delivery to any guest/staff email, verify a custom domain at resend.com/domains and set `RESEND_FROM` env var (e.g. `Syroce <noreply@yourdomain.com>`).
- **Frontend pages**:
  - `frontend/src/pages/AuthPage.jsx` — 3-field login (Otel ID / Kullanıcı Adı / Şifre), demo banner with autofill, register form now collects username + shows generated hotel_id on success.
  - `frontend/src/pages/ProfilePage.jsx` (route `/app/profile` and `/profile`) — displays name/username/email/phone/role/hotel_id, includes change-password form. Linked from user dropdown in `Layout.jsx`.
  - `frontend/src/pages/ResetPasswordPage.jsx` (public route `/auth/reset-password?token=...`) — set new password from email link.

## Major Refactors (Apr 2026)
- **`backend/models/schemas.py`** (1671 satır) → `backend/models/schemas/` paketi (16 alan modülü: identity, rooms, companies, maintenance, fnb, frontoffice, revenue, guests, bookings, folio, audit, channels, services, invoicing, loyalty, requests). `__init__.py` her şeyi re-export ediyor — 135 import noktası dokunulmadı.
- **`backend/routers/finance.py`** (4628 satır, ~90 endpoint) → `backend/routers/finance/` paketi (7 alt-router: integrations, folio, invoices, accounting, mobile, dashboards, cashiering). `__init__.py` `APIRouter(prefix='/api')` altında `include_router()` ile birleştiriyor; `router_registry.py` import yolu (`routers.finance:router`) değişmedi. `cashiering.py` içine eksik `CityLedgerAccount` import'u eklendi (orijinal dosyada da eksikti).
- **`frontend/src/pages/IntegrationHub.jsx`** (1896 → 1183 satır) → 7 sekme bileşeni `frontend/src/components/integration-hub/tabs/` altına taşındı (DashboardTab, ConnectorsTab, MappingsTab, SyncTab, ReservationsTab, ReconciliationTab, AuditTab). Paylaşılan rozetler `badges.jsx`'te (HealthBadge, StatusBadge, AckBadge). Ebeveyn tüm state/handler'ı `ctx` nesnesi olarak spread ile çocuklara geçiriyor.
- **N+1 optimizasyonu** 5 hot endpoint'te (bookings, operational-alerts, demand-heatmap, occupancy-prediction, inhouse).
- **2026-04 Performans dalgası**: 
  - `cache_manager.py` artık in-memory TTL fallback + TenantContext aware (tenant/tenant_ctx/ctx kwargs).
  - 4 yavaş endpoint micro-cache'lendi: production-golive/summary, ml/dashboard, pii-strict-mode/encryption-status, security-hardening/tenant-scope/check.
  - **8+ N+1 düzeltildi** (batch `$in` lookup pattern): housekeeping rooms, dashboard (VIP+frontdesk arrivals), pms_reservations (double-booking), pms_bookings (search), finance/mobile pending-receivables, mobile_router overbookings, pos_router cleaning_delay, pos_fnb floor-plan, messaging auto-messages.
  - **23 tenant-prefixed compound MongoDB indeksi** eklendi (`infra/database_optimizer.create_tenant_compound_indexes`): bookings/rooms/guests/folios/folio_charges/housekeeping_tasks/users/notifications/communication_logs/booking_guests/deposits/room_notes — hepsi `tenant_id` prefix'iyle. Tenant-scoped sorgular artık index plan'a girer.

## Cleanup & Refactor Pass-2 (Apr 2026)
- **`backend/domains/revenue/pricing_router.py`** (2962 satır, 43 endpoint) → `pricing_router/` paketi: 7 alt-modül (rms, rates, ai_pricing, contracted_rates, revenue_mobile, revenue_analysis, anomaly).
- **`backend/domains/revenue/rms_router.py`** (2773 satır, 46 endpoint) → `rms_router/` paketi: 9 alt-modül (comp_set, pricing_strategy, demand_forecast, sales, revenue_reports, security_mobile, housekeeping_inventory, notifications_mobile, dashboards).
- **`frontend/src/pages/NightAuditDashboard.jsx`** (1586 → 670 satır) → 5 sekme bileşeni `frontend/src/components/night-audit/tabs/` (Overview/Financial/Reconciliation/Integrity/Report) + paylaşılan `badges.jsx` (StatusBadge, SeverityBadge, StatCard, IntegrityBadge, statusConfig, severityConfig, kategoriler/ödeme yöntemleri sözlükleri).
- **`frontend/src/pages/MobileFinance.jsx`** (1814 → 775 satır) → 8 dialog bileşeni `frontend/src/components/mobile-finance/dialogs/` (Payment, Reports, Invoices, PlDetail, CashierShift, CashFlow, Risk, FolioExtract).
- **Logger geçişi**: 209 `print()` → `logger.info()` (28 üretim dosyası), test/scripts dokunulmadı; frontend için Vite zaten `oxc.drop: ['console','debugger']` ile production build'de log temizliyor.
- **Quick-ID API workflow** restart ile düzeltildi (artık 200 dönüyor).

## Backend Endpoints - New Modules
- `GET/POST /api/cashier/current-shift|open-shift|close-shift|shift-history` — Cashier management
- `GET/POST/PATCH /api/laundry/orders` — Laundry order management
- `GET /api/meeting-rooms` + `GET/POST /api/meeting-rooms/reservations` — Meeting room management
- `GET/POST/PATCH /api/concierge/requests` — Concierge desk operations
- `GET/POST /api/banquet/events` — Banquet event order management
- `POST /api/kbs/send` + `POST /api/kbs/send-batch` — KBS police notification
- `GET/POST /api/kvkk/requests` — KVKK/GDPR data requests
- `PATCH /api/pms/guests/{id}/preferences` — Guest preferences update
- `POST /api/frontdesk/booking/{id}/routing-rules` — Charge routing rules (with % split validation)
- `PATCH /api/pms/rooms/{id}/features` — Room features (DND, connecting)
- `POST /api/pms/bookings/{id}/complimentary-approval` — Complimentary room approval workflow
- `GET /api/pms/dayuse-bookings` + `POST /api/pms/dayuse-auto-checkout` — Day-use booking management
- `GET /api/pms/loyalty/tiers` + `GET /api/pms/guest/{id}/loyalty` — Loyalty tier system (auto-seeds Silver/Gold/Platinum/Diamond)
- `GET /api/pms/commission/export` — Commission report with date filtering
- `GET/POST /api/pms/group-blocks` + `POST .../cutoff` — Group block CRUD and cutoff/wash processing
- `DELETE /api/concierge/requests/{id}` + `DELETE /api/banquet/events/{id}` + `DELETE /api/kvkk/requests/{id}` — Resource deletion
- All endpoints require authentication (`Depends(get_current_user)`)
- All write endpoints enforce `tenant_id` scoping in MongoDB filters to prevent cross-tenant access (IDOR)
- Numeric inputs validated via `_safe_int`/`_safe_float` helpers (return 400 on bad input)
- BEO print HTML uses textContent-based escaping to prevent stored XSS
- KBS "Bilgi Guncelle" uses `guest_id` (not booking ID) for guest preference updates
- Routers: `backend/domains/pms/cashier_router.py`, `backend/domains/pms/operations_router.py`

## Complaint Management (Service Recovery)

- **Route**: `/service-recovery` — accessible from Operasyon menu in navigation
- **Backend Endpoints** (all in `backend/domains/pms/misc_router.py` + `backend/domains/sales/router.py`):
  - `GET /api/service/complaints` — list with filters (status, category, severity, room_number) + stats
  - `GET /api/service/complaints/{id}` — detail with room/guest/booking joins (tenant-scoped)
  - `POST /api/service/complaints` — create (field-whitelisted, tenant injection protected)
  - `PUT /api/service/complaints/{id}` — update
  - `POST /api/service/complaints/{id}/resolve` — resolve with compensation
  - `POST /api/service/complaints/{id}/escalate` — escalate to management
  - `DELETE /api/service/complaints/{id}` — delete
  - `GET /api/service/complaints-rooms` — rooms dropdown data
  - `GET /api/service/complaints-guests` — guests dropdown data
  - `GET /api/service/complaints-bookings` — active bookings for auto-fill
- **Seed Data**: `_ensure_complaints_seeded()` in `auto_seed.py` creates 15+ complaints linked to real bookings/rooms/guests
- **DB Collection**: `service_complaints`
- **Frontend**: `frontend/src/pages/ServiceRecovery.jsx` — stats, filters, create/detail/resolve dialogs
- **Integration**: Selecting a booking auto-fills guest, room, room_type; rooms and guests also selectable independently

## Property Type Profiling System

Adapts the PMS for any accommodation type. 15 property types across 4 categories.

### Property Types (backend/domains/admin/property_profiles.py)
- **Small Properties** (Basic tier): Pension, Villa, Hostel, Motel, Camping
- **Mid-Scale** (Professional tier): Apart Hotel, Boutique Hotel, 3-Star Hotel, City Hotel
- **Large Properties** (Enterprise tier): Business/Conference Hotel, 4-Star Hotel, 5-Star/Luxury Hotel
- **Resorts** (Enterprise tier): Summer/Beach, Winter/Ski, Thermal/Wellness

### How It Works
- Each property type defines: enabled modules, hidden nav groups/items, dashboard layout, special settings
- When creating a new tenant (POST /api/admin/tenants), `property_type` determines module configuration
- Subscription tier is auto-recommended but can be overridden
- `hidden_nav_groups` and `hidden_nav_items` stored on tenant doc → Layout.jsx filters navigation
- `features` dict stores property-specific settings (e.g., `quick_reservation_mode`, `show_spa`, `all_inclusive`)
- Dashboard layouts: simple, standard, advanced, full

### Key Files
- `backend/domains/admin/property_profiles.py` — 15 property type definitions with full module maps
- `frontend/src/pages/admin/CreateTenantModal.jsx` — 2-step wizard: type selection → tenant details
- `frontend/src/components/Layout.jsx` — Nav filtering by `hiddenNavGroups` + `hiddenNavItems`
- `backend/domains/admin/router.py` — GET /api/admin/property-types, property-aware create_tenant

### API Endpoints
- `GET /api/admin/property-types` — List all 15 property types (public)
- `GET /api/admin/property-types/{type}` — Get detail profile with modules, settings, nav config
- `POST /api/admin/tenants` — Now accepts `property_type` and `total_rooms` fields

## Channel Manager Connection State & Sandbox Mode

### Connector Flags (`connector_flags` collection)
- Controls provider mode: `shadow_mode: False + write_enabled: True` = LIVE mode
- `shadow_mode: True` = Shadow mode (default if no entry exists)
- Seeded by `auto_seed.py` for both `hotelrunner` and `exely` providers
- Push providers endpoint (`/push-providers`) reads flags from `connector_flags` collection for each provider independently

### HotelRunner Connection (Dual Collection Model)
- **Two collections**: `hotelrunner_connections` (legacy, used by `_get_provider()` helper and overview endpoint) AND `provider_connections` (CM 9-collection model, used by CM v2 dashboard)
- `_get_provider()` falls back to `provider_connections` when `hotelrunner_connections` is empty
- `auto_seed.py` includes `_ensure_hr_legacy_connection()` that auto-creates legacy doc from `provider_connections` even when full seed is skipped (DB already has users)
- `/test` endpoint returns mock success only when `environment` is explicitly `sandbox` or `mock`; connections without an `environment` field go through real API validation

### OTA Room Type Mapping (Real Data)
- **HotelRunner** has 3 room types: Standart Oda (`HR:1271568`), Deluxe Oda (`HR:1271569`), Corner Süit (`HR:1271567`)
- **Exely** has 3 room types: Standart (`5001574`), Deluxe (`5001575`), Suite (`5001576`)
- **Exely** has 5 rate plans: Base rate USD (`10003870`), Dynamic Rate USD (`10003541`), Non-ref rate USD (`10003869`), Mixed rate USD (`10003186`), Best daily rate (`10003182`)
- PMS has 6 room types: Standard (STD), Deluxe (DLX), Superior (SUP), Suite (SUI), Junior Suite (JSU), Family (FAM)
- Only STD, DLX, SUI are mapped to OTAs; SUP, JSU, FAM are PMS-only
- Seed data in `auto_seed.py` matches real OTA room types and rate plans
- `hotelrunner_connections.cached_rooms` stores PMS code → HR `inv_code` mapping (e.g. STD → HR:1271568)
- Push converts PMS codes to HR `inv_code` via `cached_rooms[].pms_code` → `cached_rooms[].inv_code`

### Connection Modes (Live vs Sandbox)
- `hotelrunner_connections.environment`: `live` for real API, `sandbox` for mock
- `exely_connections.mode`: `sandbox` for test SOAP API
- Push credential fallback: Exely push reads from `exely_connections` doc when vault is empty
- Exely credentials: `PMSConnect.501694` / hotel_code `501694` — test environment via HopenAPI PMSConnect
- Exely endpoint: `https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc?HotelCode=501694`
- Exely rates are in **USD** (not TRY)

### ARI Push Status
- **HotelRunner**: ✅ Working — rate, availability, restrictions push successfully via real API (`app.hotelrunner.com`), parallelized
- **Exely**: ✅ Working — rate + availability push successfully via HopenAPI PMSConnect SOAP API (test environment)
- `bulk-grid-update` accepts optional `provider` field to force target provider (otherwise auto-detects)
- Frontend `UnifiedRateManager.jsx` sends detected `provider` in bulk update requests
- Both providers push in parallel (asyncio.gather) for fast execution
- **Per-provider tabs (Apr 2026)**: UnifiedRateManager UI now has a HotelRunner | Exely tab pill above the main view. Each tab loads only its own grid (`/grid?provider=...`) and saves only push to that single provider — eliminates HR/Exely mix-up.
- Backend `/detect-provider` returns an `available[]` list of all active connections so the UI can render one tab per active provider.
- `/grid?provider=` is **strict**: explicit "hotelrunner"/"exely" without an active connection returns an empty grid instead of falling back to the other side.
- `/bulk-grid-update`: when `request.provider` is "hotelrunner" or "exely", **strictly** restricts the push to that single provider (was previously a fan-out hint only).
- **Exely native-code push (Apr 2026)**: `_push_to_exely` now detects when `room_type_code` is already a native Exely code (matches `conn.room_types[].code` or any value in `pms_to_exely_codes`) and pushes directly without HR→PMS→Exely translation. Previously, requests originating from the Exely tab (which sends native Exely codes like `5001574`) silently dropped because the function assumed HR-format codes. Also now respects rate plans selected in the grid (filtered against the connection's known plans) instead of pushing to all 5 plans.

### Push Providers Endpoint
- `/api/channel-manager/unified-rate-manager/push-providers` lists ALL active providers independently
- Each provider's mode derived from `connector_flags` (preferred) or connection doc's `push_mode` field
- Previously only showed single detected provider; now shows both HotelRunner and Exely when both active

## Sprint 14 Changes (Channel Onboarding + Go-Live Readiness Cockpit)

### Frontend — GoLiveReadinessCockpit.jsx
- **Route**: `/go-live-readiness`, nav item "Go-Live Hazirlik" in channels group
- **Data sources**: Aggregates 3 existing endpoints (no new backend):
  - `GET /api/channel-manager/connections/overview` — connection status
  - `GET /channel-manager/v2/dashboard/overview` — KPIs, mapping visibility, connectors
  - `GET /api/validation/golive-score` — 7-category readiness score, blockers, go_live_ready boolean
- **Onboarding Checklist** (5 items): Credential/Connection, Provider Validation, Mapping Conflicts, Review Queue, Recent Failures — each with pass/fail/warn status + corrective action CTA
- **Test & Validation Panel**: "Test Connection" (POST /connectors/{id}/test), "Dry Run" (POST dry-run/ari-push), "Mapping Wizard" navigation
- **Blockers Panel**: Lists categories scoring <50 from GoLiveReadinessScorer with issues
- **Readiness Score Sidebar**: Large circular score, maturity name, 7 category bars (runtime_validation, provider_validation, incident_response, observability, pilot_checklist, tenant_isolation, audit_timeline) with weight display
- **Connector Summary Sidebar**: Quick status for each connector with inline test button
- **Go-Live Button**: Enabled only when `go_live_ready === true` (score ≥75 + no blockers); disabled state shows blocker count

### Nav Changes
- "Go-Live Hazirlik" added in channels group after CM Dashboard, before Channel Manager

## Sprint 13 Changes (Surface Consolidation + Cross-Module UX Audit)

### Nav Structure Cleanup (`navItems.jsx`)
- **B2B Analytics**: Moved from `reports` navGroup → `channels` navGroup (moduleKey was already `channel_manager`)
- **Channel Ops**: Added `requireSuperAdmin: true` — deep ops tooling, not for regular hotel staff
- **Channels group reordered**: CM Dashboard → user-facing items (Channel Manager, Rate Manager, Mapping, Agencies, B2B) → admin-only section (Ops, Connections, Wire Failures, ARI Push, Lockdown)
- **Infrastructure group slimmed**: 11 → 6 visible items. Hidden (still accessible via direct URL): Data Pipeline, Event Bus, Runtime Infrastructure, Platform Scaling, Enterprise Live
- **Visible infrastructure items**: Control Plane, Runtime Cockpit, Incident Panel, System Health, Security Hardening, Encryption Management, Production Go-Live

### Cross-Surface CTAs (CM Dashboard → Channel Ops → Mapping Wizard)
- **CM Dashboard header**: Added "Operasyon Merkezi" button → navigates to `/channel-ops` (super_admin only)
- **CM Dashboard alert strip**: Review queue + DLQ alerts clickable → `/channel-ops` (super_admin only). Mapping conflicts → `/room-mapping-wizard` (all users)
- **CM Dashboard mapping sidebar**: Conflict card clickable → `/room-mapping-wizard` (all users)
- **CM Dashboard ops summary card**: "Detayli Operasyon Gorunumu" CTA → `/channel-ops` (super_admin only)
- **Channel Ops header**: Added "CM Dashboard" button → navigates to `/cm-dashboard`
- All Channel Ops CTAs gated by `user.role === 'super_admin'` — non-admin users see alerts but cannot navigate
- Both pages use `useNavigate` from react-router-dom

### Surface Boundary Summary
| Surface | Audience | Focus | API |
|---|---|---|---|
| CM Dashboard | Hotel staff | Business continuity: connectors, reservations, mappings | `/channel-manager/v2/dashboard/...` |
| Channel Ops | SuperAdmin | System stability: webhooks, DLQ, rate limits, incidents | `/api/ops-events/...` |
| B2B Analytics | Hotel staff | Channel revenue & booking analytics | channels navGroup |
| Report Scheduler | All users | Automated report delivery | reports navGroup |

## Sprint 12 Changes (v1_ Module Migration / Cleanup)

### Backend — Module Renaming
- **`v1_client.py` → `hr_client.py`**: HotelRunnerClient HTTP connector (XML/OTA + REST/JSON). Updated docstring. Internal import changed from `v1_errors` → `connector_errors`.
- **`v1_errors.py` → `connector_errors.py`**: ConnectorError hierarchy (17 exception classes). No content changes.
- **`v1_mapper.py` → `reservation_mapper.py`**: HotelRunnerMapper (reservation to canonical model transformation). No content changes.
- All files live in `backend/channel_manager/connectors/hotelrunner_v2/`
- Existing v2 files (`client.py`/`errors.py`/`mapper.py`) untouched — different classes (HRv2Client, HRv2Error) for the newer v2 adapter pattern

### Compatibility Aliases
- `v1_client.py`, `v1_errors.py`, `v1_mapper.py` retained as thin re-export stubs
- Any external code importing from old paths will continue working

### Import Path Updates (14 files)
- **Application services** (6): `connector_service.py`, `auto_mapping_service.py`, `inventory_sync_service.py`, `sandbox_validation_service.py`, `provider_adapters.py`, `reservation_import_service.py`
- **Internal modules** (3): `retry_policy.py`, `xml_parser.py`, `auth.py`
- **Test files** (3): `test_hr_reservation_adapter.py`, `test_production_hardening_v3.py`, `test_legacy_hr_removal.py`
- Legacy test file updated with both new-path tests and compatibility-alias tests

### Verification
- Zero `v1_` imports remain in production `channel_manager/` package
- All 14 changed files pass `py_compile`
- Compatibility aliases verified: old import paths still resolve correctly

## Sprint 11 Changes (Channel Manager Dashboard)

### Backend
- **`backend/channel_manager/interfaces/routers/dashboard_router.py`** — Unified CM Dashboard API:
  - `GET /channel-manager/v2/dashboard/overview` — Single aggregation endpoint returning:
    - KPIs: total/healthy/degraded/error/paused connectors, recent reservations (24h), failed imports, review queue, push queue depth, wire failures (24h), DLQ count
    - Connector details: display name, provider, status, sync timestamps, errors, consecutive failures
    - Recent reservations: last 10 imported reservations with guest name, dates, status
    - Mapping visibility: connectors with mappings, total review-pending, total conflicts, per-provider summaries (mapped/auto/review/unmatched/conflicts)
  - `GET /channel-manager/v2/dashboard/connector/{connector_id}` — Connector drilldown:
    - Sync stats (total syncs, total errors, consecutive failures)
    - Queue status (pending/retry/dead_letter items)
    - Reservation stats grouped by status
    - Mapping summary + conflicts for that connector
    - Recent failure log entries
  - Registered in `router_registry.py`

### Frontend
- **`frontend/src/pages/ChannelManagerDashboardV2.jsx`** — Full operational dashboard:
  - 6 KPI cards: total connectors, healthy, degraded+error, recent reservations (24h), failed imports, push queue depth
  - Alert strip: review queue warnings, DLQ alerts, mapping conflict notices
  - Connector health table: display name, provider badge, status badge, consecutive failure count, last sync time-ago, last error with truncation, drilldown button
  - Recent imported reservations list with status badges and check-in/out dates
  - Mapping visibility sidebar: matched/review counts, conflict alerts, per-provider breakdown
  - Operations summary sidebar: push queue, wire failures, DLQ, review queue counts
  - Connector drilldown slide-over panel: sync stats grid, queue status (pending/retry/DLQ), reservation stats, mapping summary with conflicts, recent failure log
  - Route: `/cm-dashboard`, nav: "channels" group as "CM Dashboard"

## Sprint 10 Changes (Auto Room Mapping v2)

### Backend
- **`backend/channel_manager/application/auto_mapping_service.py`** — Multi-signal matching engine v2:
  - `_compute_match_score_v2()` — Weighted scoring with 4 signals: name similarity, alias boost, capacity match, price proximity
  - `_capacity_similarity()` — Compares PMS vs external room max occupancy (0-100%)
  - `_price_proximity()` — Compares PMS vs external base price using average ratio (0-100%)
  - `_PROVIDER_WEIGHTS` — Provider-aware weighting profiles:
    - HotelRunner: name 50%, capacity 25%, price 15%, alias 10%
    - Exely: name 60%, capacity 15%, price 10%, alias 15%
    - Default: name 55%, capacity 20%, price 15%, alias 10%
  - Graceful degradation when capacity/price data unavailable (redistributes weights)
  - Per-suggestion `score_breakdown` with individual signal percentages
  - Per-suggestion `warnings` array for capacity mismatches and price gaps
  - Conflict detection: identifies when same external type is suggested for multiple PMS types
  - Status categories: `auto` (≥60% + no warnings), `review` (30-60% or has warnings), `unmatched`
  - `conflicts` array in response with duplicate-mapping details
  - PMS room data now fetches `capacity` and `base_price` fields alongside `room_type`

### Frontend
- **`frontend/src/pages/RoomMappingWizard.jsx`** — Enhanced wizard UI:
  - `ScoreBar` component: horizontal bar visualizing each signal score
  - `ConfidenceBadge` v2: click-to-expand score breakdown popup showing name/alias/capacity/price bars + final score + warnings
  - Sectioned suggestion layout: "Otomatik Eslestirmeler" (auto-apply), "Inceleme Gerektiren" (review queue), "Eslesmedi" (unmatched)
  - Review items default to disabled (operator must explicitly enable)
  - Conflict warnings panel with `ShieldAlert` icon at top of suggestions
  - Per-row warning display for capacity/price mismatches
  - PMS metadata inline: capacity (K:X) and base price (₺) shown per room type
  - External room dropdown shows capacity info (K:X) per option
  - Summary badges include conflict count with pulse animation

## Sprint 9 Changes (Calendar Assignment Clarity)

### Frontend
- **`frontend/src/pages/calendar/calendarHelpers.jsx`** — New urgency helpers:
  - `getUnassignedUrgency(booking)` — Returns `{ level, label, daysUntil }` where level is overdue/today/tomorrow/future
  - `getUrgencyBarColors(level)` — Tailwind color classes for urgency-colored booking bars
  - `sortByUrgency(bookings)` — Sorts bookings by urgency (overdue first → today → tomorrow → future)
- **`frontend/src/pages/calendar/CalendarGrid.jsx`** — Enhanced unassigned rows:
  - Urgency-colored booking bars (red=overdue, orange-pulse=today, amber=tomorrow, blue=future)
  - Left priority stripe on each bar
  - Countdown badge ("Gecikmiş!", "Bugün!", "Yarın", "2 gün")
  - Ring highlights for overdue/today bookings
  - Row background tinted by urgency level
- **`frontend/src/pages/calendar/CalendarHeader.jsx`** — Enhanced unassigned button:
  - Urgency breakdown text ("3 atanmamis (1 gecikmiş!)" or "(2 bugün)")
  - AlertTriangle icon when urgent bookings exist
  - Pulse animation when overdue bookings present
  - Color shifts: red border for overdue, orange for today
- **`frontend/src/pages/ReservationCalendar.jsx`** — Enhanced UnassignedPanel:
  - Summary cards: 4-column grid showing Gecikmiş/Bugün/Yarın/Gelecek counts with color coding
  - Filter tabs: Tümü/Gecikmiş/Bugün/Yarın/Gelecek (uses showUnassignedPanel state as filter key)
  - Bookings sorted by urgency within each filter
  - Left border color stripe per urgency level + urgency badge per card
  - Quick room assign: inline dropdown showing available rooms matching booking's room type
  - Room availability check against existing bookings on check-in date
  - No-show button retained per card

## Sprint 8 Changes (Automated Email Scheduler for Reports)

### Backend
- **`backend/routers/report_scheduler.py`** — Report Email Scheduler API with 11 endpoints:
  - `GET /api/report-scheduler/report-types` — Available report types, frequencies, formats
  - `POST /api/report-scheduler/schedules` — Create new schedule
  - `GET /api/report-scheduler/schedules` — List all schedules (tenant-scoped)
  - `GET /api/report-scheduler/schedules/{id}` — Get schedule detail
  - `PUT /api/report-scheduler/schedules/{id}` — Update schedule
  - `DELETE /api/report-scheduler/schedules/{id}` — Delete schedule + history
  - `POST /api/report-scheduler/schedules/{id}/toggle` — Enable/disable schedule
  - `POST /api/report-scheduler/schedules/{id}/send-now` — Manual trigger
  - `GET /api/report-scheduler/history` — Send history with status/schedule filters
  - `GET /api/report-scheduler/history/{id}` — Single send detail
  - `POST /api/report-scheduler/history/{id}/retry` — Retry failed sends
  - Manager+ role required for create/update/delete/toggle/send/retry
  - Staff+ role for read-only (list, history)
  - Uses existing `email_service.py` for SMTP/mock delivery
  - 11 report types: daily_summary, revenue, occupancy, reservations, guest_analytics, adr_revpar, channel_performance, b2b_analytics, housekeeping, financial, flash_report
  - Registered in `bootstrap/router_registry.py`

### Frontend
- **`frontend/src/pages/ReportScheduler.jsx`** — Full scheduler dashboard:
  - 4 KPI cards (total, active, sent, failed)
  - 2 tabs: Schedules list + Send History
  - Schedule cards with status badges, toggle, edit, delete, send-now actions
  - Create/Edit modal with report type, frequency, recipients, format, schedule params
  - Send history table with status icons, retry for failed, detail modal
  - History filter by status (all/sent/failed/partial)
  - Route: `/report-scheduler`, nav: "Raporlar" group as "Rapor Zamanlayici"

## Sprint 7 Changes (Navigation / Surface Consolidation)

### Channels Group (21 → 10 visible)
- **Hidden (7)**: `hr_rate_manager`, `rate_manager`, `hotelrunner`, `exely`, `data_model`, `integration_hub`, `admin_control_panel` — superseded by unified Channel Manager / Control Plane
- **Kept visible (5 admin)**: Channel Connections, Wire Failures, ARI Push, Lockdown Dashboard, Channel Ops
- **Kept visible (5 user-facing)**: Channel Manager, Unified Rate Manager, Room Mapping Wizard, Agency Manager, Early Warning

### Infrastructure Group (gained 3 items)
- **Moved from channels**: Control Plane, Runtime Cockpit, Incident Panel — these are platform-level ops, not channel-specific
- **moduleKey fix**: `platform_scaling` + `enterprise_live` changed from `"pms"` to `"advanced_analytics"` for consistency

### Operations Group
- **Hidden**: `pms_operations` (duplicate of PMS dashboard)

### Backward Compatibility
- All hidden items retain routes in `routeDefinitions.jsx` — direct URLs still work
- `hidden: true` flag filtered by `Layout.jsx` line 130: `if (item.hidden) return;`

## Audit Fix: Router Import Corrections

### Backend
- **`backend/domains/pms/cashier_router.py`** — Fixed broken import (`from db import get_db` → `from core.database import db`). This router was not loading at all, causing 404s for: `/api/cashier/*`, `/api/meeting-rooms/*`, `/api/laundry/*` endpoints.
- **`backend/domains/pms/operations_router.py`** — Same import fix. Was blocking: `/api/concierge/*`, `/api/banquet/*`, `/api/kbs/*`, `/api/kvkk/*`, `/api/revenue/settings`, guest preferences, room features, complimentary approvals, day-use bookings, loyalty tiers, and routing rules endpoints.
- **`backend/domains/pms/housekeeping_router.py`** — Added missing `from domains.guest.schemas import LinenInventoryItem` import. The linen-inventory endpoint was returning 500 (NameError) when no inventory data existed and it tried to create defaults.
- **`backend/routers/reports.py`** — Fixed `get_daily_flash_report_data is not defined` error in PDF and email endpoints. Both now call the existing `get_daily_flash_report()` function with correct response field names (`occupied_rooms`, `total_rooms`, `occupancy_rate` instead of `occupied`, `total`, `percentage`).

## Turkish Localization Sweep (Comprehensive)

All frontend PMS modules systematically fixed for proper Turkish character encoding and English-to-Turkish translation:

### Fixes Applied Across 60+ Files
- **Broken Turkish characters**: All ASCII approximations fixed (basarisiz→başarısız, bulunamadi→bulunamadı, guncellendi→güncellendi, yapildi→yapıldı, istediginize→istediğinize, yuklenemedi→yüklenemedi, etc.)
- **English error messages**: All `Failed to ...` toast/alert messages translated to Turkish
- **window.confirm dialogs**: All confirmation dialogs use proper Turkish characters (ş, ç, ğ, ı, ö, ü, İ)
- **Currency**: All monetary displays use ₺ (TRY), no $ symbols
- **Key files fixed**: ServiceRecovery, ReservationDetailModal, GovernancePanel, OperationTabs, OnlinePaymentTab, PMSModule, ReservationCalendar, EnhancedFolioManager, TemplateManager, all admin tabs, rate managers, channel manager modules, housekeeping, POS, and many more

### Session Plan T001-T006 (All Pre-completed)
- T001: StaffTaskManager — Full Turkish UI with KPI cards, Dialog components
- T002: POSTab — Turkish UI, ₺ currency, correct API mappings
- T003: FeedbackSystem — Turkish UI, Dialog instead of window.prompt
- T004: AllotmentGrid — Turkish UI, validation, Dialog components
- T005: KBSNotification — Dialog, XML escaping, Turkish UI
- T006: ConciergeDesk, RevenueControls, ManagerDailyReport, KVKKManager — All complete

## Sprint 7 Changes (Marketplace v1 — Cross-tenant B2B)

- **`backend/routers/marketplace_b2b.py`** (~750L) — Cross-tenant marketplace API enabling external apps (e.g. Syroce Agent at github.com/beyinsiz1903/acenta-uygulama) to search & book across many Syroce-PMS hotels with a single API key.
  - **Auth**: System-level (tenant-independent) API keys in `sysdb.marketplace_api_keys`. `get_marketplace_agency` does NOT call `set_tenant_context`; each endpoint resolves the target tenant per-request from the path/body and sets context inline.
  - **Admin endpoints** (gated by `X-Marketplace-Admin-Token` env-secret): create/list/disable agencies, regenerate API keys.
  - **Hotel admin endpoints** (JWT): `POST/GET/PUT/DELETE /listings/me` to opt-in / update / opt-out of the marketplace, with per-listing commission override, allowed_room_types whitelist and blocked_dates.
  - **Agency endpoints** (X-API-Key, cross-tenant): `GET /hotels` discovery (city/country/q filter), `GET /hotels/{tenant_id}` detail, `POST /search` multi-hotel availability with capacity + max_price filters, `GET /hotels/{tid}/availability|rates`, full reservation lifecycle (`POST/GET/DELETE /reservations`).
  - **Bookings pipeline reuse**: cross-tenant bookings drop into the existing `db.bookings` collection with `channel="marketplace"`, `marketplace_agency_id`, `agency_commission_rate/_amount`, `net_to_hotel`, `external_reference` (agency PNR), `origin="syroce_marketplace"`. Mirror summary written to `sysdb.marketplace_bookings` for cross-tenant ledger / reconciliation.
  - **Webhooks**: reuses `routers.b2b_api.fire_webhooks` (retry + DLQ) — fires `marketplace.reservation.created` and `marketplace.reservation.cancelled` to the booking's tenant.
  - **Reconciliation**: `GET /reconciliation/agency` (cross-tenant rollup by hotel) and `GET /reconciliation/hotel` (rollup by agency) for period-based commission/net reports.
  - **Env**: `MARKETPLACE_ADMIN_TOKEN` secret required (passed via `X-Marketplace-Admin-Token` header on `/admin/*` routes).
  - **Collections created on first use**: `sysdb.marketplace_agencies`, `sysdb.marketplace_api_keys`, `sysdb.marketplace_listings`, `sysdb.marketplace_bookings`.
  - Mounted in `bootstrap/router_registry.py` after b2b_analytics. Smoke-tested end-to-end (agency create → hotel opt-in → multi-hotel search → cross-tenant booking → hotel reconciliation → cancel).
  - **Out of scope this sprint**: client SDK on the acenta-uygulama side (separate repo), invoice generation from reconciliation totals, agency self-service portal UI on PMS, payouts.

## Sprint 6 Changes (B2B Analytics Dashboard)

### Backend
- **`backend/routers/b2b_analytics.py`** — B2B Analytics API with 6 endpoints:
  - `/api/b2b-analytics/summary` — KPI overview (bookings, revenue, active agencies, API calls)
  - `/api/b2b-analytics/agency-breakdown` — Per-agency metrics table
  - `/api/b2b-analytics/booking-trends` — Time-series booking data for charts
  - `/api/b2b-analytics/api-usage` — API call volume by event type
  - `/api/b2b-analytics/top-endpoints` — Most-used event types ranked
  - `/api/b2b-analytics/export` — CSV download (bookings/agencies/usage)
  - All endpoints require hotel staff role (403 for agency users)
  - Date range filtering with proper end-of-day boundary handling
  - Registered in `bootstrap/router_registry.py`

### Frontend
- **`frontend/src/pages/B2BAnalyticsDashboard.jsx`** — Full analytics dashboard:
  - 6 KPI cards (bookings, approved, conversion %, revenue, active agencies, API calls)
  - 4 tab sections: Booking Trends, Agency Performance, API Usage, Top Endpoints
  - Recharts visualizations (BarChart, AreaChart, PieChart, LineChart)
  - Date range selector (7d/30d/90d/6mo/1y), agency filter dropdown
  - Agency breakdown table with sortable columns
  - 3 CSV export buttons (bookings, agencies, usage)
  - Error state handling with user-visible warning banner
  - Route: `/b2b-analytics`, nav: "Raporlar" group as "B2B Analitik"

## Sprint 5 Changes (Technical Debt + Hardening)

### Backend
- **`backend/domains/channel_manager/rate_utils.py`** — Shared rate manager utilities: Pydantic models (RoomTypeValuesItem, BulkGridUpdateRequest, StopSaleScheduleCreate/Update, PricingSettingItem/Request, RoomTypeSelection), `group_consecutive_dates()`, `get_holiday_periods()`. Used by both hr_rate_manager_router.py and rate_manager_router.py.
- **`backend/routers/early_warning_engine.py`** — `EarlyWarningConfig` class with 21 configurable thresholds, per-connector overrides via `ew_config.register_connector_override()`, configurable dedup window.
- **`backend/domains/channel_manager/providers/sync_engine.py`** — Extracted sync phases from hotelrunner_sync.py
- **`backend/domains/channel_manager/providers/sync_scheduler.py`** — Extracted ReservationPullScheduler

### Frontend
- **`frontend/src/pages/reports/`** — Extracted 11 report section components from BasicReports.jsx:
  - OverviewSection, RevenueSection, AdrRevparSection, PeriodSection, OccupancySection
  - RoomTypesSection, GuestSection, NationalitySection, FrontOfficeSection
  - OperationsSection (NoShow, RoomStatus, Housekeeping, Payments, Departments, FnB)
  - ChannelsSection (Channels, Sources), OfficialSection (Official, Police)
- **`frontend/src/pages/reports/ReportHelpers.jsx`** — Shared constants, formatters, and reusable UI atoms

## E2E Testing Bug Fixes (April 2026)

### Flash Report Field Mapping (FlashReport.jsx)
- Fixed `occupancy.occupancy_pct` → `occupancy.rate`
- Fixed `guest_flow.*` → `operations.*` (arrivals, departures, inhouse, no_shows, cancellations)
- Fixed `revenue.adr`/`revenue.revpar` → `kpi.adr`/`kpi.revpar`
- Fixed `revenue.rooms_revenue`/`fnb_revenue`/`other_revenue`/`total_revenue` → `revenue.room`/`fb`/`other`/`total`
- Computed TRevPAR from `revenue.total / occupancy.total` (not a backend field)
- Revenue breakdown percentages now computed dynamically

### GM Dashboard (GMDashboard.jsx)
- Fixed RevPAR: `revenue.revpar` → `revenue.revpar || revenue.rev_par` (daily-flash uses `rev_par`)

### Folio Management (FolioManagementPage.jsx)
- Fixed create endpoint: `POST /api/folio` → `POST /api/folio/create` with `Idempotency-Key` header
- Fixed folio lookup: uses `/api/folio/booking/{bookingId}` to resolve folio ID instead of treating booking ID as folio ID
- Fixed charge posting: `POST /api/folio/charge` → `POST /api/folio/{folioId}/charge`; field `unit_price` → `amount`
- Fixed payment posting: `POST /api/folio/payment` → `POST /api/folio/{folioId}/payment`; added required `payment_type` field; fixed `payment_method` → `method`; removed invalid `check` option, added `online`
- Payment method enum: `cash`, `card`, `bank_transfer`, `online`
- Payment type enum: `prepayment`, `deposit`, `interim`, `final`

### Housekeeping (Backend + Frontend)
- Fixed `enterprise_router.py`: rooms query used `hk_status` field but DB stores `housekeeping_status` — now queries both
- Fixed tenant isolation: `start`/`complete` endpoints now include `tenant_id` in query filter (IDOR fix)
- Fixed `HousekeepingMobileApp.jsx`: endpoint `/housekeeping/rooms` → `/pms/housekeeping/rooms` with `status_filter` param
- Fixed `HousekeepingDashboard.jsx`: reads `status_counts.*` from API (was looking for `summary.*`)

## Quick-ID Microservice Integration (April 2026)

### Architecture
- **Service**: `quick-id/` — bağımsız FastAPI uygulaması, port **8099**, Atlas DB `syroce-kimlik`
- **Workflow**: `Quick-ID API` (`bash quick-id/start.sh`) — `MONGO_ATLAS_URI` + `QUICKID_SERVICE_KEY` env'lerini okur, PYTHONPATH izolasyonu sağlar
- **OCR Sağlayıcılar**: GPT-4o, GPT-4o-mini, Gemini Flash, Tesseract (yerel) — `OPENAI_API_KEY` veya `GEMINI_API_KEY` ile etkinleştirilir

### PMS ↔ Quick-ID Bridge
- **Service-to-service auth**: `X-Service-Key: $QUICKID_SERVICE_KEY` header (`X-Acting-User` ile birlikte)
  - **Whitelist'li**: yalnızca `/api/scan`, `/api/scan/*`, `/api/health`, `/api/providers` path'lerinde geçerli (auth.py `SERVICE_ALLOWED_PATHS`)
  - **`role: service`** atanır — admin yetkisi YOK
- **PMS Proxy**: `backend/routers/quick_id_proxy.py` → endpoint'ler `/api/quick-id/{health,scan,providers}`
  - PMS JWT ile korunur, Quick-ID'ye servis anahtarıyla iletir
  - **Demo fallback fail-closed**: yalnızca `ENABLE_QUICKID_DEMO=true` ise OCR yokken sahte veri döner; production'da 503 fırlatır
- **Frontend**: `frontend/src/components/QuickIdScanDialog.jsx` — dosya yükle/kamera, base64'e çevir, `/quick-id/scan`'e POST, sonucu `onExtracted(doc)` callback'iyle döner
- **Entegrasyon noktası**: `frontend/src/pages/reservation-detail/InfoTabs.jsx` GuestsTab → her misafirde **"Kimlik Tara"** butonu, çıkarılan veri (ad, soyad, kimlik no, doğum tarihi, uyruk, cinsiyet, belge tipi) düzenleme formuna otomatik dolar

### Önemli Env Vars
- `QUICKID_SERVICE_KEY` (secret) — PMS↔quick-id bridge anahtarı
- `QUICKID_URL` — varsayılan `http://localhost:8099`
- `ENABLE_QUICKID_DEMO` — `true` ise OCR yokken sahte veri (sadece dev)
- `OPENAI_API_KEY` / `GEMINI_API_KEY` — gerçek OCR için (quick-id okur)

## Security Notes

### Dependency Vulnerabilities (Resolved)
- **python-multipart**: Upgraded 0.0.22 → 0.0.26 (CVE-2026-40347 — DoS via crafted multipart/form-data with large preamble/epilogue). Fixed in `backend/requirements.txt`.

### Security Practices
- JWT + AES-256-GCM encryption for auth tokens
- RBAC role-based access control (super_admin, admin, staff, etc.)
- Tenant-scoped MongoDB queries prevent cross-tenant data access (IDOR protection)
- API key auth for B2B API: SHA-256 hashed keys stored in DB, never plaintext
- Input validation: `_safe_int`/`_safe_float` helpers, Pydantic Field constraints on financial writes
- BEO print uses textContent-based escaping (XSS prevention)
- Field-whitelisted POST bodies prevent mass assignment
- `emergentintegrations` package skipped by pip-audit (internal package, not on PyPI — expected)

## Room QR Requests Module (Oda QR Talepleri) — Native

### Özellikler
- Her odaya **benzersiz QR kod** — misafir tarar, giriş yapmadan talep gönderir
- **15 önceden tanımlı kategori** (temizlik, teknik, F&B, çamaşır, minibar, ulaşım, SPA, vb.) — her biri doğru departmana otomatik yönlendirilir
- **Kanban staff dashboard**: Yeni / Atandı / İşlemde / Tamamlandı sütunları, 30 sn'de bir tazeleme, istatistik kartları
- **5-dil misafir arayüzü** (tr/en/de/ru/ar) — RTL desteği, hotel branding (renk/logo)
- **Aktif rezervasyon otomatik bağlanır** — booking_id + misafir adı (maskeli) otomatik eklenir
- **QR yazdırma sayfası** — her oda için PNG indir, URL kopyala, toplu yazdırma (A4'e sığacak şekilde)
- **Gerçek-zamanlı websocket event'i** (`room_request:new`, `room_request:update`) — tenant-scoped odaya emit
- **Durum geçmişi (history)** — kim ne zaman hangi statüye aldı, notlar ile

### Veri Modeli (MongoDB `room_qr_requests`)
`tenant_id, room_id, room_number, category, department (DepartmentType enum), title, description, priority (low/normal/high/urgent), status (new/assigned/in_progress/completed/cancelled), language, guest_name, guest_phone, booking_id, assigned_to, created_at, updated_at, completed_at, status_history[]`

### QR Token (Tokensız Akış)
- **HMAC-SHA256(tenant_id|room_id, ROOM_QR_SECRET)** — tam 64 char digest (constant-time compare)
- **DB'de state yok** — token kayıt gerektirmez, doğrulama pure math
- **Fail-closed**: `ROOM_QR_SECRET` yoksa JWT_SECRET'a düşer; ikisi de yoksa 503
- **Rate limit**: public submit endpoint'i — 10 dk / 20 talep / (oda + IP)
- **Misafir adı public meta'da maskelenir** (`"J*** D***"`) — QR'ı gören 3. kişi gerçek adı göremez

### Endpoint'ler
**Public (auth yok)**:
- `GET  /api/public/room-qr/{tenant}/{room}?t=TOKEN` → hotel/oda bilgileri + kategori listesi
- `POST /api/public/room-qr/{tenant}/{room}/submit?t=TOKEN` → talep oluştur

**Staff (JWT)**:
- `GET   /api/room-requests?status=&department=&room_id=` → liste (filtreli)
- `GET   /api/room-requests/{id}` → detay (history dahil)
- `PATCH /api/room-requests/{id}` → status/priority/department/assigned_to + note (history'ye eklenir)
- `GET   /api/room-requests/stats/summary` → dashboard istatistikleri

**QR Üretimi (staff)**:
- `GET /api/rooms/{room_id}/qr-code` → URL + PNG base64 + token
- `GET /api/rooms/qr-codes/bulk` → tüm odaların URL listesi (toplu yazdırma için)

### Frontend Sayfalar
- `frontend/src/pages/guest/RoomRequestPage.jsx` — public, `/g/room/:tenantId/:roomId?t=TOKEN`
- `frontend/src/pages/RoomRequests.jsx` — staff kanban, `/app/room-requests`
- `frontend/src/pages/admin/RoomQrCodes.jsx` — QR yazdırma, `/admin/room-qr-codes`
- Nav: Operasyon > "Oda QR Talepleri", Yönetim > "Oda QR Kodları"

### Env Vars
- `ROOM_QR_SECRET` *(önerilen)* — HMAC secret; yoksa `JWT_SECRET` kullanılır
- `PUBLIC_APP_URL` — QR URL'leri için; yoksa `REPLIT_DEV_DOMAIN` veya request header'dan türetilir

## Faz: Af-sadakat Entegrasyon Hazırlığı (Faz 1 — DONE)

Af-sadakat (github.com/beyinsiz1903/Af-sadakat) — sadakat programı, AI yorum
yönetimi, birleşik mesaj kutusu, misafir servisleri, QR misafir paneli — Modül
Pazarı'ndan satılabilir hale getirildi. Mimari: ayrı servis + Syroce köprüsü.

### Eklenen
- **Marketplace ürünü**: `af_sadakat` (₺1499/ay, 14 gün ücretsiz deneme,
  `external: true`, `sso_path: /integrations/afsadakat/launch`)
- **Trial endpoint**: `POST /api/module-store/start-trial` — ödemesiz, tek
  kullanım, otomatik provisioning tetikler
- **Provisioning**: `core/afsadakat_provisioner.py` — `AFSADAKAT_BASE_URL` +
  `AFSADAKAT_ADMIN_TOKEN` env varsa harici sunucuya HTTP, yoksa local-only
  (API key üretip DB'ye yazar). Idempotent.
- **SSO köprüsü**: `POST /api/integrations/afsadakat/launch` — kısa ömürlü
  (120s) HS256 JWT (aud=afsadakat, JWT_SECRET ile imzalı), redirect URL döner
- **Inbound webhook**: `POST /api/integrations/afsadakat/webhook` — Bearer
  API key auth, event'leri `integration_afsadakat_events` koleksiyonuna yazar
- **Outbound PMS API** (Af-sadakat → Syroce, API key auth):
  `GET /api/pms-outbound/rooms`, `/reservations`, `/reservations/{id}`,
  `/guests`, `/guests/{id}`, `POST /folio/charge` (external_ref ile idempotent)
- **Frontend**: `AfsadakatLauncher` sayfası (`/app/afsadakat`), nav'a "Sadakat
  & Inbox" item eklendi (entitlement ile gizli/görünür, `moduleKey: af_sadakat`).
  ModuleStorePage trial butonu + external modüller için "Aç" butonu.
- **MODULE_ALIASES**: `af_sadakat → [af_sadakat, af_sadakat_loyalty]`
- **Platform admin endpointleri**: `/api/integrations/afsadakat/admin/provision`
  (force re-provision), `/admin/tenants/{id}` (api_key gizli, suffix ile)

### Env Vars (opsiyonel — Faz 2'de)
- `AFSADAKAT_BASE_URL` — harici Af-sadakat instance URL'si (örn https://afsadakat.replit.app)
- `AFSADAKAT_ADMIN_TOKEN` — Af-sadakat'ın `/api/admin/integrations/syroce/provision`
  endpointi için bearer token

### Outbound webhook (Syroce → Af-sadakat) — DONE
- **Modül**: `core/afsadakat_outbound.py` — `emit_event(tenant_id, type, payload)`
  outbox'a yazar + fire-and-forget teslim, başarısızlar exponential backoff ile
  yeniden denenir (max 5 deneme: 30s/2dk/8dk/30dk/2sa).
- **İmza**: HMAC-SHA256(per-tenant `pms_api_key`, raw_body) →
  `X-Syroce-Signature: sha256=<hex>` header'ı. Diğer header'lar:
  `X-Syroce-Event`, `X-Syroce-Delivery` (idempotency için event_id).
- **Hedef**: `{AFSADAKAT_BASE_URL}/api/integrations/syroce/webhook`.
- **Hook'lanan olaylar**:
  - `reservation.created` — `CreateReservationService.create` başarısı sonrası
  - `reservation.updated` — `UpdateReservationService.update` (changes varsa)
  - `reservation.cancelled` — yukarıdaki, `status` cancelled/no_show'a geçtiğinde
  - `guest.checked_out` — `atomic_checkin_checkout.check_out_booking_atomic`
    transaction commit sonrası
- **Local mod davranışı**: `AFSADAKAT_BASE_URL` set değilse `emit_event` sessizce
  no-op döner; iş akışı asla bloklanmaz/bozulmaz (try/except sarılmış).
- **Periyodik dispatcher**: `dispatch_pending_loop()` startup'ta task olarak
  başlatılır (`startup.py`), dakikada bir pending event'leri yeniden dener.
- **Koleksiyon**: `db.integration_afsadakat_outbox`
  (`status: pending|sent|failed`, `attempts`, `next_attempt_at`, `last_error`).

### Veritabanı koleksiyonları (platform-wide)
- `integration_afsadakat_tenants` — { tenant_id (uniq), api_key, ext_tenant_id,
  status, mode (local|external), base_url }
- `integration_afsadakat_events` — webhook event log

### Sonraki Faz (Faz 2 — bekliyor)
- Af-sadakat repo'su fork edilip Syroce adapter eklenecek (mevcut
  `pms_integration.py` adapter pattern'ine `SyroceAdapter` sınıfı ekle —
  outbound API'leri çağıracak)
- Ayrı Replit projesi olarak Af-sadakat deploy + env'leri PMS'e set

## Wake-up Call Alerts (Apr 2026)

**Amaç**: Resepsiyon/operatör için sesli alarm + tarayıcı bildirimi + zil
merkezi (`/api/notifications/list`) entegrasyonu — uyandırma saati gelen
bekleyen çağrılar otomatik tetiklenir.

### Backend (`backend/routers/hotel_services.py`)
- `GET /api/pms/wake-up-calls` artık her cevapta:
  - `_fire_due_wake_up_alerts(tid, calls)`: tüm `pending` + `wake_date+wake_time
    <= Europe/Istanbul now` çağrıları için **önce** `db.notifications`'a
    `(tenant_id, source_type=wake_up_call, source_id=call.id)` üzerinde
    upsert (idempotent), **sonra** `wake_up_calls.alert_fired_at` set eder.
    Sıralama önemli: notification yazımı başarısız olursa call un-fired
    kalır → bir sonraki poll yeniden dener.
  - `_annotate_due(calls)`: her item'a `is_due=true/false` damgalar
    (frontend görsel ve ses tetikleyicisi).
  - `stats.due_now` eklendi; `stats.today` artık Istanbul tarihiyle
    hesaplanıyor (UTC değil — gece yarısı sınırında doğru "today").

### Frontend (`frontend/src/pages/WakeUpCallsPage.jsx`)
- 30 sn polling (sadece `filterDate === todayInIstanbul()` iken).
- Tek uzun ömürlü `AudioContext` (modül-scope `_alarmCtx`) — kullanıcı
  "Sesli Alarmı Aç" butonuyla `resume()` eder; sonraki timer-tetikli
  alarmlarda autoplay policy bypass'lı çalar.
- Web Audio API ile 3 ardışık bip (880-880-1100 Hz, ~1.3 s) — asset yok.
- `Notification` API ile masaüstü bildirimi (`requireInteraction: true`,
  `tag: wakeup-{id}` → duplicate önler); izin reddedilirse sadece toast.
- Süresi gelmiş `is_due` çağrılar kırmızı pulsing ring + "ŞİMDİ ARA!"
  badge ile vurgulanır.
- `sessionStorage[wakeup-alerted-{istanbul-date}]`: günlük "alarmı
  çalındı" cache — sayfa reload'da aynı çağrı için tekrar bip atmaz.
- `armedRef` + state ayrımı: `fireAlertsFor` callback'i `alertsArmed`
  değişimine bağlı değil → poller yeniden kurulmaz, duplicate fetch yok.

### Bell Center entegrasyonu
- `db.notifications` doc şeması: `{id, tenant_id, source_type=wake_up_call,
  source_id, type=alert, severity=warning, title, message, link, icon,
  read=false, created_at}` — mevcut `/api/notifications/list`
  normalizasyonuyla (legacy `is_read` → `read`) uyumlu.

## Grup Rezervasyonu — Toplu Oluşturma (Apr 2026)

`/group-bookings-manage` sayfasındaki "Yeni Grup Oluştur" dialogu artık iki
modda çalışır: **mevcut rezervasyonları grupla** (eski davranış) **veya
aynı dialog'tan N adet yeni rezervasyon yaratıp gruba bağla**. Bu sayede
tur/MICE grupları için önce N tane bireysel rezervasyon açma adımı
gerekmiyor.

### Backend (`backend/routers/reservation_detail.py`)
- `GroupBookingCreate` şemasına `new_bookings: list[NewGroupBookingRow]`
  eklendi (`guest_name, room_id, check_in, check_out, total_amount,
  adults, children`).
- POST `/api/pms/group-bookings` iki aşamalı işliyor:
  1. **Pre-validate**: tüm satırlar (ad/tutar/tarih) + odalar (tek `$in`
     sorgusu, tenant scope) + mevcut `booking_ids` (tenant guard) yazma
     yapmadan doğrulanır. Hatada hiçbir şey yazılmaz.
  2. **Create + compensate**: misafir (placeholder e-posta) +
     `CreateReservationService.create()` ile rezervasyon. Servis
     idempotency-key gerektirdiği için her satır için
     `_request_with_idempotency_key(req, uuid4())` ile yeni `Request`
     üretilir (scope headers'ı klonlanır). Herhangi bir satır
     başarısız olursa önceden yaratılmış misafir+rezervasyonlar
     `delete_many` ile geri alınır.
- Yanıtta `created_booking_ids` listesi döner — UI bunu kullanıcıya
  bildirim olarak gösterir.

### Frontend (`frontend/src/pages/GroupBookings.jsx`)
- Tab toggle: "Mevcut Rezervasyonları Grupla" | "Yeni Rezervasyonlar
  Oluştur".
- Yeni mod tablosu: misafir adı, oda dropdown (`/pms/rooms`'tan), giriş
  tarihi, çıkış tarihi, tutar; +Satır Ekle, sıra silme.
- "Tarihleri Eşitle" — ilk satırın tarihlerini tüm satırlara uygular
  (turist grubu senaryosu).
- Canlı toplam tutar.
- Submit: istemci-tarafı pre-check + tek `POST /pms/group-bookings`.

### Veri sözleşmeleri
- Grup placeholder misafirleri `email = group-{uuid8}@placeholder.local`
  pattern'iyle damgalanır (sonradan misafir bilgileri rezervasyon
  detayından güncellenebilir).
- Yaratılan rezervasyonlar `origin = ui-group` ile etiketlidir.

## Misafir Yorumları & NPS Yönetimi (Apr 2026)

Müşteri ilişkileri ekibinin oda bazlı yorum + puan girip raporlayabilmesi
için `/guest-journey` sayfasına tam CRUD + analiz katmanı eklendi.

### Backend (`backend/domains/guest/operations_router.py`)
- `POST /api/nps/survey` — `room_number`, `guest_name`, `nps_score (0-10)`,
  `feedback`, `source` alır; `recorded_by` + `recorded_by_id` otomatik
  damgalanır. **Kritik**: `nps_score=0` falsy tuzağı `if 'nps_score' in
  data` kontrolüyle kapatıldı (eski `or` davranışı 0'ı 5'e çeviriyordu).
  Score 0-10 arası tam sayı doğrulaması + 400 hatası.
- `DELETE /api/nps/survey/{id}` — yalnızca aynı tenant.
- `GET /api/nps/recent` — kategori/oda filtreli, son N yorum
  (`limit` 1-200 bounded).
- `GET /api/nps/by-room` — Mongo aggregation pipeline: oda başına
  ortalama puan + yanıt sayısı + kategori dağılımı + son yanıt tarihi,
  **en kötüden iyiye sıralı** (şikayet odaklı).
- `_bounded_days(1..730)` helper — tüm `days` query param'larında.

### Frontend (`frontend/src/pages/GuestJourney.jsx`)
- **Dönem seçici** (7/30/90/365 gün) — tüm endpoint'leri yeniden tetikler.
- **Kategori kartları** tıklanabilir filtre olarak çalışır
  (Destekçi/Nötr/Eleştirmen).
- **Oda bazlı tablo** — ortalama puan rengi (≥9 yeşil, ≥7 amber, <7
  kırmızı), tek tıkla o odanın yorumlarına filtrele.
- **Yeni Yorum dialog**: oda + misafir + 0-10 slider (canlı kategori
  önizleme) + serbest metin yorum. `source: manual` damgalı.
- **Son yorumlar listesi**: skor rozeti + kategori + oda + kim girdi +
  tarih + sil butonu.
- **Optimistik delete**: önce listeden filtrele, sonra await loadAll —
  out-of-order yanıtlarda silinen kayıt geri dönmez.
- Tüm async aksiyonlar `await loadAll()` ile sıralı (race-safe).

### Veritabanı (`db.nps_surveys`)
- Doc: `{id, tenant_id, guest_id?, booking_id?, room_number?, guest_name?,
  nps_score (0-10), category (promoter|passive|detractor), feedback?,
  source (manual|email|qr|api), recorded_by, recorded_by_id, responded_at}`
- Kategori kuralı: ≤6 detractor, 7-8 passive, 9-10 promoter.

## Af-sadakat (Sadakat & Omni Inbox) Marketplace Modülü (Apr 2026)
Müşteri, Modül Pazarı'ndan satın alıp 14 gün ücretsiz deneyebileceği harici
modül. Otomatik provisioning + SSO + Outbound PMS API ile entegre.

### Akış
1. **Katalog**: `marketplace_products` koleksiyonunda `key=af_sadakat`
   (₺1499/ay, trial 14 gün, `external=true`, `sso_path=/integrations/afsadakat/launch`).
2. **Aktivasyon**: `/api/module-store/start-trial` (ödemesiz) veya
   `/api/module-store/purchase` → callback. Her iki yol da aktivasyondan
   sonra `provision_tenant()` çağırır.
3. **Provisioning**: `core/afsadakat_provisioner.py` — `AFSADAKAT_BASE_URL` +
   `AFSADAKAT_ADMIN_TOKEN` env varsa harici Af-sadakat'a HTTP çağrısı yapar;
   yoksa local-only modda 40 char `api_key` üretip
   `integration_afsadakat_tenants` koleksiyonuna yazar. Idempotent
   (`$setOnInsert` + unique index).
4. **SSO Launch**: `POST /api/integrations/afsadakat/launch` → 120 sn ömürlü
   HS256 JWT (`iss=syroce-pms`, `aud=afsadakat`, `sub=tenant_id`) üretir,
   `{base_url}/sso/syroce?token=...` URL'i döner. Frontend yeni sekmede açar.
5. **Webhook**: `POST /api/integrations/afsadakat/webhook` — Bearer
   API key auth, event `integration_afsadakat_events`'e kaydedilir.
6. **Outbound PMS API** (`/api/pms-outbound/*`): Af-sadakat tarafından
   tüketilir. API key bearer auth + her istekte `tenant_has_module()`
   doğrulaması (abonelik biterse anında 403):
   - `GET /rooms`, `GET /reservations[/{id}]`, `GET /guests[/{id}]`
   - `POST /folio/charge` — `external_ref` üzerinden idempotent
7. **Frontend**:
   - `ModuleStorePage.jsx`: trial_days varsa "14 Gün Ücretsiz Dene", sahip
     olunan `external` modüller için "Aç" butonu (launch URL'i window.open).
   - `AfsadakatLauncher.jsx`: `/app/afsadakat` route, launch URL alıp açar.
   - Nav: "Sadakat & Inbox" (`moduleKey: af_sadakat`).

### Koleksiyonlar
- `integration_afsadakat_tenants`: `{tenant_id, api_key, ext_tenant_id,
  status, mode (local|external), base_url, created_at, updated_at}`
  — unique on `tenant_id`.
- `integration_afsadakat_events`: inbound webhook log
  `{tenant_id, event_type, payload, received_at}` — index
  `(tenant_id, received_at desc)`.

### Env (opsiyonel)
- `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`: harici Af-sadakat
  konuşlandırılınca tanımlanır. Yoksa sistem local-only modda kalır,
  UI hata vermez.

### Outbound HMAC Dispatcher (önceden tamamlandı)
`core/afsadakat_outbound.py` — PMS olaylarını (4 tip: rezervasyon
oluştu/değişti/iptal, misafir oluştu) HMAC-SHA256 ile imzalı outbox
üzerinden Af-sadakat'a iletir. Bu modül Af-sadakat env tanımlıyken
otomatik tetiklenir.

## Sprint 14: 8-Borç Audit Temizliği (Apr 2026)

Tüm A-H borçları kapatıldı:

- **A — F821 import errors**: 121 → 0. Eksik Pydantic stub'lar
  (`GuestPersona`, `MaintenanceAlert`) ve helper fonksiyonlar
  (`distribute_tasks`, `generate_scheduling_recommendations`,
  `get_tier_benefits`, `_collect_push_devices`, `_simulate_push_delivery`,
  `_record_push_log`, `has_permission`, `_time_ago`,
  `_calculate_profile_completion`) eklendi. Etkilenen modüller:
  `ai/router.py`, `ai/service.py`, `pms/notification_router.py`,
  `pms/misc_router.py`, `maintenance_router.py`, `pos_fnb_router.py`,
  `guest/operations_router.py`, `guest/messaging/router.py`,
  `readiness_validator.py`, `early_warning_engine.py`. Ayrıca
  `get_folio_details`'te tenant izolasyon bug'ı (folio_charges/payments
  sorgularına `tenant_id` eklendi) düzeltildi.

- **B — Exely vault migration**: `backend/scripts/migrate_exely_vault.py`
  yazıldı (idempotent, `--apply` flag'iyle yazma). Demo tenant'ın
  plaintext credential'ları AES-256-GCM şifreli `_dev_secrets`
  vault'una taşındı, `exely_connections.username/password` alanları
  silindi (`vault_migrated_at` damgalandı). **Bonus fix**:
  `core/secrets/local_provider.py` artık `_raw_db` kullanıyor
  (TenantAwareDBProxy değil) — sistem koleksiyonu olan `_dev_secrets`'e
  otomatik tenant_id enjeksiyonu kaldırıldı; bu bug nedeniyle vault
  okumaları boş dönüyordu.

- **C — Tenant uniqueness indexes**: `backend/startup.py` içine
  `db.tenants.hotel_id` ve `db.users(tenant_id, username)` unique
  index hook'u eklendi (sparse / partialFilterExpression `username:
  string` ile mevcut indexle uyumlu).

- **D — GraphQL strawberry annotations**: `_legacy/graphql_schema.py`
  içindeki tüm resolver'lara `info: strawberry.Info` annotation
  eklendi (`MissingArgumentsAnnotationsError` çözüldü).

- **E — CORS dev default**: `backend/server.py` REPLIT_DEV_DOMAIN
  otomatik algılama + dev için
  `^https://[a-z0-9-]+\.(replit\.dev|replit\.app|riker\.replit\.dev)$`
  regex; `*` + credentials protokol ihlali kaldırıldı.

- **F — Locale parity**: 10 dil dosyası
  (`tr/en/de/fr/es/it/pt/ru/ar/zh.json`) artık 2583 anahtarda eşit;
  TR'de eksik 6 `migrationObs.reason_*` anahtarı Türkçe çevirilerle,
  diğer dillere İngilizce fallback ile dolduruldu.

- **G — RateManager dedup**: `RateManager.jsx` ve `HRRateManager.jsx`
  `frontend/src/_archive/`'a taşındı; `/rate-manager`,
  `/hr-rate-manager`, `/unified-rate-manager` rotaları
  `UnifiedRateManager`'a yönlendiriliyor.

- **H — React.lazy audit**: `routeDefinitions.jsx` 187 lazy import +
  4 kasıtlı eager (AuthPage, Dashboard, LandingPage, PrivacyPolicy).

## Sprint 15: Dashboard Konsolidasyonu (Apr 2026)

GM/Executive ailesindeki 6 dashboard sayfası 2'ye indirildi:

**Hayatta kalanlar:**
- `Dashboard.jsx` (`/app/dashboard`) — **Operations Dashboard**, ana
  nav girişi.
- `ExecutiveDashboard.jsx` (`/executive`) — **Executive Dashboard**,
  `gm_dashboards` modül kontrolü.

**Arşive taşınanlar** (`frontend/src/_archive/dashboards-2026-04/`):
- `GMDashboard.jsx` (1449 satır) → `/gm-classic` artık `/app/dashboard`'a redirect.
- `GMEnhancedDashboard.jsx` (430 satır) → `/gm/enhanced` → `/executive`.
- `EnhancedGMDashboard.jsx` (436 satır) → `/admin/gm-enhanced` → `/executive`.
- `EnterpriseLiveDashboard.jsx` (576 satır) → `/enterprise-live` → `/executive`.

**Altyapı değişikliği:** `App.jsx` dinamik router'a yeni
`type: "redirect"` desteği eklendi (`<Navigate to={rc.to} replace />`).
`routeDefinitions.jsx`'te 4 lazy import kaldırıldı, 4 rota
redirect olarak yeniden yazıldı.

**Sonuç:** ~2891 satır legacy kod canlıdan çıkarıldı, eski URL'ler
hâlâ çalışıyor (yer imleri/derin bağlantılar bozulmuyor).

## Sprint 16: Konaklama Vergisi Otomasyonu (Apr 2026)

Türkiye Konaklama Vergisi (7194 sayılı Kanun, varsayılan %2) için
tam entegre modül.

### Backend
- `backend/routers/finance/konaklama_vergisi.py` (YENİ) — finance
  paketi `__init__.py`'a eklendi, prefix `/api/finance/konaklama-vergisi`.
- Mevcut `db.city_tax_rules` koleksiyonu config olarak yeniden
  kullanıldı (`tax_percentage` alanı `rate_percent`'e alias'landı,
  `auto_post`, `exempt_segments`, `effective_from`, `notes` alanları
  eklendi).
- Posting izi: `db.accommodation_tax_postings` (idempotency anahtarı:
  `tenant_id + folio_id`).
- `ChargeCategory.CITY_TAX` enum değeri folio satırına yazılırken
  kullanıldı.

### Endpoints (tümü tenant-scoped)
- `GET  /api/finance/konaklama-vergisi/config` — yapılandırma oku
- `PUT  /api/finance/konaklama-vergisi/config` — oran/aktif/auto_post
- `POST /api/finance/konaklama-vergisi/calculate` — ad-hoc hesap
- `GET  /api/finance/konaklama-vergisi/report?year=&month=` —
  aylık matrah/vergi/folio listesi
- `GET  /api/finance/konaklama-vergisi/declaration?year=&month=` —
  GİB beyanname özeti (son ödeme: takip ayın 26'sı, otomatik hesap)
- `POST /api/finance/konaklama-vergisi/post-folio/{folio_id}` —
  manuel posting (idempotent; oda satırlarından matrah toplar,
  CITY_TAX satırı atar, folio bakiyesini günceller)
- `GET  /api/finance/konaklama-vergisi/postings?limit=` — geçmiş

### Frontend
- `frontend/src/pages/KonaklamaVergisiModule.jsx` (YENİ) — 4 sekme:
  Yapılandırma · Aylık Rapor · Beyanname · Hesaplayıcı.
- Rapor sekmesi: ay/yıl seçici, KPI kartları (folio/geceleme/matrah/
  vergi), folio bazlı tablo, CSV indir.
- Beyanname sekmesi: yazdırılabilir GİB formatlı özet (işletme,
  vergi no, dönem, son tarih, oran, matrah, vergi).
- Nav: Finance grubunda "Konaklama Vergisi" (`moduleKey: invoices`).
- Route: `/app/konaklama-vergisi` (lazy, `pm()`).

## Sprint 17: Af-sadakat Marketplace Entegrasyonu (Apr 2026)

Af-sadakat (Sadakat & Omni Inbox) modülü Modül Pazarı üzerinden
satın alınabilir, otomatik provisioning + SSO ile bağlanır hale geldi.

### Backend
- `backend/routers/marketplace.py` — `af_sadakat` ürünü kataloga
  eklendi (₺1499/ay, 14 gün trial, `external=true`,
  `sso_path=/integrations/afsadakat/launch`).
  - `ProductIn` şemasına `trial_days, external, sso_path` eklendi.
  - Yeni `POST /api/module-store/start-trial` (ödemesiz, idempotent;
    `(tenant, product, status=active)` partial unique index ile
    yarış koşullarına karşı korunuyor).
  - `_activate_subscription` post-activation hook'u: ürün anahtarı
    `af_sadakat` ise `provision_tenant()` çağrılır (hem ücretli hem
    trial yolunda).
- `backend/core/subscriptions.py` — `MODULE_ALIASES` içinde
  `af_sadakat` mevcut.
- `backend/core/afsadakat_provisioner.py` (YENİ) — iki modlu
  provisioning:
  - `AFSADAKAT_BASE_URL + AFSADAKAT_ADMIN_TOKEN` set ise harici
    Af-sadakat'a HTTP `POST /api/admin/integrations/syroce/provision`
    çağrısı yapılır, `ext_tenant_id` saklanır (mode=external).
  - Set değilse local-only mod: API key (token_urlsafe(40)) üretilir
    ve `integration_afsadakat_tenants` koleksiyonuna yazılır.
  - `mint_sso_token`: HS256 JWT, 120s TTL, aud=afsadakat.
  - `find_tenant_by_api_key`: outbound endpoint'lerin auth'u için.
  - Atomic upsert ile concurrent activation'da api_key churn yok.
- `backend/routers/integrations_afsadakat.py` (YENİ):
  - `GET  /api/integrations/afsadakat/status` — entitled/provisioned/
    mode bilgileri
  - `POST /api/integrations/afsadakat/launch` — SSO token üretip URL
    döner; lazy-provision destekli
  - `POST /api/integrations/afsadakat/webhook` — Bearer API key auth,
    eventleri `integration_afsadakat_events`'a yazar
  - `POST /api/integrations/afsadakat/admin/provision` — platform
    admin için zorla yeniden provisioning
  - `GET  /api/integrations/afsadakat/admin/tenants/{id}` — api_key
    son 6 hane suffix olarak gösterilir, tam key sızdırılmaz
- `backend/routers/pms_outbound.py` (YENİ) — Af-sadakat'ın PMS'e
  okuma/yazma için kullandığı outbound API:
  - `GET /api/pms-outbound/rooms`
  - `GET /api/pms-outbound/reservations[/{id}]`
  - `GET /api/pms-outbound/guests[/{id}]`
  - `POST /api/pms-outbound/folio/charge` — `external_ref` ile
    idempotent folio satırı
  - Auth: API key + canlı `tenant_has_module` kontrolü
    (abonelik bittiyse 403, credentials silinmese de erişim kapanır).
- `backend/bootstrap/router_registry.py` — yeni iki router kayıtlı.

### Frontend
- `frontend/src/pages/ModuleStorePage.jsx` — `trial_days` varsa
  "14 Gün Ücretsiz Dene" butonu, `external` ürünlerde sahip
  olunan abonelik için "Aç" butonu (af_sadakat → `/app/afsadakat`).
- `frontend/src/pages/AfsadakatLauncher.jsx` (YENİ) — bağlantı
  durumu kartı (abonelik / hazırlık / mod), local-only modda
  bilgilendirme uyarısı, "Sadakat & Inbox'ı Yeni Sekmede Aç"
  butonu.
- `frontend/src/config/navItems.jsx` — "Sadakat & Inbox" nav
  öğesi (`moduleKey: af_sadakat`).
- `frontend/src/routes/routeDefinitions.jsx` — `/app/afsadakat`
  rotası (lazy).

### Env
- Mevcut: `AFSADAKAT_ADMIN_TOKEN` (zaten set).
- Eksik: `AFSADAKAT_BASE_URL` — set edilene kadar local-only mod
  (UI uyarı veriyor, abonelik kapatılmıyor).

### Smoke test (PASS, 19 Apr 2026)
- Catalog: af_sadakat ürünü `trial_days=14, external=true`
  doğru görünüyor.
- start-trial: idempotent (`already_existed=true`).
- status: `entitled=true, provisioned=true, mode=local`.
- launch: `external_ready=false` → `/integrations/afsadakat/not-deployed`
  placeholder döndü (beklenen davranış).

## Sprint 18: Onboarding Wizard (Apr 2026)

Yeni kiracılar için 5 adımlı kurulum sihirbazı.

### Backend
- `backend/routers/onboarding.py` (YENİ) — tenant-facing endpoints:
  - `GET    /api/onboarding/progress` — 13 adımlı ilerleme + dismissed flag
  - `POST   /api/onboarding/complete-step` — manuel ✓ işaretle
  - `POST   /api/onboarding/dismiss` — sihirbazı kapat (otomatik
    pop-up'ı engeller, ilerleme korunur)
  - `POST   /api/onboarding/resume` — tekrar aç
  - `PATCH  /api/onboarding/hotel-info` — Tenant alanlarını günceller
    (`property_name, contact_phone, address, location, total_rooms`)
    + `hotel_info_completed` adımını otomatik tamamlar
- `backend/core/onboarding.py` — `DEFAULT_STEPS` listesine yeni adım
  `hotel_info_completed` eklendi (manuel işaretleme).
- `backend/bootstrap/router_registry.py` — yeni router kayıtlı.

### Frontend
- `frontend/src/pages/OnboardingWizard.jsx` (YENİ) — tek sayfada
  5 adımlı sihirbaz:
  1. **Otel Bilgileri** — form (mülk adı, telefon, adres, konum,
     toplam oda) → PATCH ile kaydet
  2. **Odalar** — toplu oda ekleme aracını açar (`pms#rooms`)
  3. **Fiyatlar** — Tarife Yönetimi sayfasına yönlendirir
  4. **Ekip** — Kullanıcı Yönetimine yönlendirir
  5. **Tamamlandı** — panele git
  - Üstte genel ilerleme yüzdesi (Progress bar) + adım strip'i
    (her adım ✓/○ ikonuyla durum gösterir)
  - "Şimdilik Atla" butonu → `/onboarding/dismiss` çağırır,
    panele yönlendirir
  - Adım 2-4 backend tarafından otomatik algılanır (rooms_configured,
    rates_configured, team_members_added) — kullanıcı geri döndüğünde
    ✓ işareti görünür
- `frontend/src/config/navItems.jsx` — Yönetim grubunda
  "Kurulum Sihirbazı" nav öğesi.
- `frontend/src/routes/routeDefinitions.jsx` — `/app/onboarding`
  rotası (lazy).

### Smoke test (PASS, 19 Apr 2026)
- Progress: 13 adım, %46 (mevcut tenant'ta 6 zaten tamamlanmış)
- hotel-info PATCH: tenant doğru güncellendi, `hotel_info_completed`
  adımı otomatik ✓
- dismiss: `dismissed=true` döndü

### Sprint 18 — Architect Güvenlik Düzeltmeleri (PASS)
- `_require_tenant_admin()` — onboarding mutasyon endpointleri
  (`hotel-info`, `complete-step`, `dismiss`, `resume`) artık
  `super_admin / platform_admin / admin / owner` rollerini zorunlu
  kılıyor. Resepsiyon/kat hizmetleri kullanıcıları sadece `progress`
  okuyabilir.
- `MANUAL_STEPS_ALLOWLIST = {"hotel_info_completed"}` — `complete-step`
  artık otomatik algılanan adımları (rooms_configured, rates_configured,
  vb.) kabul etmiyor; geçersiz `step_id` 400 döner.
- Smoke (19 Apr 2026): admin → 200, otomatik adım → 400, bogus → 400,
  allowlist → 200.

### Sprint 18 — Otomatik Yönlendirme (Apr 2026)
- `frontend/src/App.jsx` `handleLogin` içinde: tenant admin
  (`super_admin/platform_admin/admin/owner`) ise ve `postLoginRedirect`
  deep-link YOKSA, `/onboarding/progress` çağrılır.
- `dismissed=false` ve `completed<3` ise `sessionStorage.postLoginRedirect`
  `/app/onboarding` olarak ayarlanır → `PostAuthRedirect` sihirbaza yönlendirir.
- Mevcut kurulu tenant'lar (oda/misafir verisi olan) auto-detect
  sayesinde 3+ adımı tamamlamış sayıldığı için etkilenmez.
- Kullanıcı sihirbazda "Şimdilik Atla" derse `dismiss=true` olur ve
  bir daha otomatik yönlenmez (menüden manuel açılabilir).

## Sprint 19: 2FA / TOTP (Apr 2026) — KURUMSAL ZORUNLULUK ✅

Kurumsal müşteri satın alma zorunluluğu için RFC 6238 TOTP tabanlı
iki adımlı doğrulama.

### Backend
- `backend/core/twofa.py` (YENİ) — TOTP secret üretimi (160-bit base32),
  Fernet ile AES şifreli depolama (JWT_SECRET türevli ayrı domain key),
  10 adet 8-haneli yedek kod üretimi (bcrypt-hash, tek kullanımlık).
- `backend/routers/security_2fa.py` (YENİ):
  - `GET  /api/2fa/status`
  - `POST /api/2fa/setup` → secret + QR data URL + otpauth URI
    (pending slot, henüz aktif değil; tekrar çağırılabilir)
  - `POST /api/2fa/setup/confirm` → kod doğrula → aktifleştir +
    yedek kodları **tek seferlik** döndür
  - `POST /api/2fa/disable` → parola + (TOTP **veya** yedek kod)
  - `POST /api/2fa/regenerate-backup-codes` → TOTP gerekli, eski
    kodlar iptal
  - `GET  /api/2fa/policy` → tenant düzeyinde 2FA zorunluluğu okuma
- `backend/routers/auth.py` — login akışına 2FA gate:
  - `two_factor_enabled=true` ise `access_token=""`,
    `requires_2fa=true`, kısa ömürlü (5dk) `challenge_token` döner
  - **Cache geçerlilik kontrolü**: cached login response 2FA
    aktiveden önce alınmışsa db'den taze flag okunur, eski cache
    eviktedilir
- `POST /api/auth/2fa/verify` (YENİ) — challenge_token + 6-haneli
  kod (TOTP veya yedek kod) → gerçek `access_token`. Yedek kod
  kullanılırsa o kodun bcrypt hash'i listeden silinir
  (tek kullanımlık).
- Audit log eventleri: `2fa_enabled`, `2fa_disabled`,
  `2fa_backup_regenerated`, `login_2fa_required`,
  `login_2fa_failed`, `login_2fa_success` (details: totp/backup_code).

### Frontend
- `frontend/src/pages/AuthPage.jsx` — login response'ta
  `requires_2fa=true` ise tüm tab UI gizlenir, 6 haneli kod giriş
  ekranı gösterilir; submit → `/auth/2fa/verify` → `onLogin(...)`
- `frontend/src/pages/ProfilePage.jsx` — yeni `<TwoFactorSection>`
  bileşeni:
  - Etkin değilse: "2FA Etkinleştir" → QR kod + manuel secret +
    6-haneli doğrulama → backup kodlarını **tek kez** gösterir
    (kopyala butonu)
  - Etkinse: durum (etkinleşme tarihi, son kullanım, kalan yedek
    kod sayısı), yedek kod yenileme, devre dışı bırakma
    (parola + 2FA kodu zorunlu)

### Smoke (PASS, 19 Apr 2026)
1. Setup → secret üretildi, QR base64 PNG döndü
2. Confirm valid TOTP → enabled=true, 10 backup code
3. Login → requires_2fa=true, challenge token üretildi
   (cache invalidation çalıştı)
4. Verify wrong code → 401
5. Verify valid TOTP → real access_token
6. Backup code login → token alındı, kalan=9
7. Disable → 2FA flag kaldırıldı
8. Login plain → eski akışa döndü

### Veri modeli (User dokümanı)
- `two_factor_enabled: bool`
- `two_factor_secret_enc: str` (AES/Fernet)
- `two_factor_backup_codes: list[str]` (bcrypt hashes)
- `two_factor_enabled_at`, `two_factor_last_used_at`
- `two_factor_secret_pending_enc` (geçici, confirm'da silinir)

### Güvenlik notları
- TOTP secret JWT_SECRET'tan domain-separated SHA256 ile türetilen
  Fernet key ile şifrelenir → JWT_SECRET sızsa bile 2FA secrets
  çözülmez (TWOFA_SECRET ile ayrıca override edilebilir).
- Yedek kodlar bcrypt ile hashlenir, plaintext **asla** disk'te
  durmaz (sadece bir kez kullanıcıya gösterilir).
- Disable 2 faktörlü gereksinim taşır (parola + kod) — saldırgan
  oturumu çalsa bile devre dışı bırakamaz.
- Challenge token 5dk ömürlü, `purpose=2fa_challenge` claim'i ile
  domain-separated.

## Sprint 20: PCI-DSS Compliance Dashboard (Apr 2026) ✅

Kurumsal otel müşterilerinin satın alma süreçlerinde talep ettiği
PCI-DSS uyum durumunun şeffaf gösterimi.

### Backend
- `backend/core/pci_dss.py` (YENİ) — PCI-DSS v4.0'ın 12
  gereksinimini Syroce'nin teknik kontrollerine eşleyen
  `evaluate_controls()` ve özet skor üreten `summary()`.
  Status değerleri: `met` / `partial` / `shared` / `not_applicable`.
- `backend/routers/pci_compliance.py` (YENİ, admin-only):
  - `GET /api/compliance/pci/status` — özet skor (uygulama %)
  - `GET /api/compliance/pci/controls` — 12 gereksinim detayı
    (kanıtlar + öneriler)
  - `GET /api/compliance/pci/report.csv` — Excel uyumlu (BOM'lu)
    CSV indir
  - `GET /api/compliance/pci/attestation` — RFP/satın alma için
    JSON beyan paketi (issuer, tenant, summary, controls, disclaimer)
- Yetki: `super_admin / platform_admin / admin / owner` rolleri.

### Frontend
- `frontend/src/pages/PCIComplianceDashboard.jsx` (YENİ):
  - Skor kartları (uygulama %, met/partial/shared sayıları)
  - 12 gereksinim için kart listesi (sol border renkli, status
    badge, kanıt + öneri listesi)
  - CSV ve JSON beyan paketi indirme butonları
  - QSA disclaimer bandı
- Route: `/app/compliance/pci`
- Nav: "PCI-DSS Uyum" → management grubu (Modül Pazarı altı)

### Skor (demo tenant, 19 Apr 2026)
- Uygulama Skoru: **%67** (6 met / 9 in-scope)
- Karşılanan (met=6): Req 2, 3, 4, 7, 8, 10
- Eylem Gerekli (partial=3): Req 6 (CI'de SAST otomasyonu),
  Req 11 (yıllık pen-test), Req 12 (politika dokümantasyonu)
- Paylaşılan (shared=3): Req 1, 5, 9 (cloud sağlayıcı sorumluluğu)

### Notlar
- Bu öz-değerlendirmedir, resmi PCI sertifikası için QSA gerekli.
- Yeni güvenlik modülleri eklendikçe `evaluate_controls()` içindeki
  `_has_module()` probları otomatik yansır.

### Sprint 19/20 Architect-Driven Sertleştirmeler (19 Apr 2026)
Code review (architect) ciddi güvenlik bulgularıyla döndü; hepsi kapatıldı:

1. **2FA challenge token replay koruması**: challenge JWT'sine `jti`
   eklendi; başarılı verify sonrası jti `simple_cache`'de
   "consumed" olarak 10dk işaretlenir → aynı token ikinci kez
   kullanılamaz. Smoke ile doğrulandı (2. verify → 401 "zaten kullanıldı").
2. **Login cache fail-closed**: 2FA flag rechek sırasında istisna
   olursa cache **evict** edilir ve tam login yoluna düşülür
   (eski davranış: cached token döndürülürdü).
3. **2FA Fernet key fallback kaldırıldı**: `core/twofa.py` artık
   TWOFA_SECRET / JWT_SECRET (env veya runtime sabiti) yoksa
   `RuntimeError` atar; sabit fallback string silindi.
4. **Atomik backup code tüketimi**: `consume_backup_code` artık
   sadece eşleşen hash'i tespit ediyor; DB'de `$pull` ile filtre
   üzerinden silindiği için iki paralel istek aynı kodu kullanamaz
   (`modify_count==0` → 401 "yedek kod zaten kullanıldı").
5. **PCI evaluator dürüstleştirildi**: Req 4 (TLS) HSTS middleware
   veya `FORCE_HTTPS=true` yoksa `partial`; Req 6 (CI scan)
   `CI_SECURITY_SCAN_ENABLED=true` yoksa `partial`. Demo skor
   gerçekçi şekilde %67 → **%44** düştü.

### Smoke (post-fix, 19 Apr 2026)
- 2FA setup/confirm/challenge/verify/disable → tüm akış PASS
- Replay testi → 401 "zaten kullanıldı" PASS
- PCI status → met=4 / partial=5 / shared=3, score=%44 (dürüst)

## Sprint 21–22 — Syroce Xchange (SXI) Bus (Apr 2026)
**Amaç**: OPERA PMSXchange (OXI) eşdeğeri çok-kiracılı entegrasyon
bus'ı. Otel olaylarını (rezervasyon, posting, inventory, rate)
HTNG 2024B XML / OData V4 JSON ile kayıtlı partner adapter'larına
güvenli ve idempotent biçimde dağıtır.

### Yeni modüller
- `backend/integrations/xchange/schemas.py` — 12 kanonik mesaj tipi
  (RESERVATION_CREATE/MODIFY/CANCEL, POSTING_CHARGE/PAYMENT,
  INVENTORY_UPDATE, RATE_UPDATE, NIGHT_AUDIT_CLOSE, …) + envelope.
- `backend/integrations/xchange/htng.py` — OTA/HTNG 2024B XML
  serializer (Reservation/Posting/Inventory/Rate + generic fallback).
- `backend/integrations/xchange/registry.py` — partner kataloğu
  (Sabre SynXis CRS, SAP S/4HANA Finance, Generic Webhook) +
  config schema.
- `backend/integrations/xchange/bus.py` — publish, retry, replay,
  dead-letter; **atomik idempotency** unique index üzerinden
  `(tenant_id, message_id, partner_code)`; otomatik retry worker
  (`run_retry_cycle` / `start_retry_loop`).
- `backend/integrations/xchange/safety.py` — **SSRF egress guard**
  (private/loopback/link-local IP'leri engeller; allow-list env'i
  `XCHANGE_EGRESS_ALLOWED_HOSTS`).
- `backend/integrations/xchange/adapters/` — `base.py`,
  `sabre_synxis.py` (HTNG XML, HTTPS Basic), `sap_s4hana.py`
  (OData V4 + OAuth2, Journal Entry mapping), `generic_webhook.py`
  (HMAC-SHA256 imzalı JSON).
- `backend/routers/xchange.py` — `/api/xchange/{partners,configs,
  deliveries,replay,test-publish}` (admin-only, tenant-scoped,
  secret masking on GET, masked-secret preservation on PUT).
- `frontend/src/pages/XchangePage.jsx` — partner config UI,
  capability matrix, mesaj akışı (status/retry sayısı), replay,
  detay modali. `/app/xchange` rotası, "Xchange (SXI)" navigasyonu.

### Güvenlik & güvenilirlik kararları
- **Dry-run gating sıkılaştırıldı**: Sabre `endpoint+username+
  password+hotel_code`, SAP `base_url+client_id+client_secret+
  token_url` hepsi tam değilse adapter dry-run'a düşer (yarı
  yapılandırılmış canlı çağrı yok).
- **Atomik idempotency**: claim-row strategy + Mongo unique index;
  eşzamanlı publish'ler aynı `(tenant, message_id, partner)` için
  **çift teslimat üretmez** (DuplicateKeyError → "duplicate" döner).
- **Otomatik retry**: `_RETRY_DELAYS=[30s,2m,10m,1h]`, `_MAX_ATTEMPTS=5`;
  `run_retry_cycle()` due deliveries'i tarar, atomik claim ile
  yarış koşulunu engeller, başarısız 5. denemede `dead_letter`'a
  taşır.
- **Replay path** adapter exception'larını yakalar; replay artık
  500 atmaz, hatayı `last_error` olarak yazar.
- **SSRF koruması** tüm outbound URL'lerde aktif; tenant admin
  loopback/RFC1918 hedef veremez.

### Smoke (19 Apr 2026)
- Partner katalog → 3 partner listelenir (sabre_synxis, sap_s4hana,
  generic_webhook), capability matrix doğru.
- Publish RESERVATION_CREATE → Sabre + Generic dry-run delivered,
  SAP capability_unsupported (correct).
- Publish POSTING_CHARGE → SAP + Generic dry-run delivered, Sabre
  capability_unsupported.
- Egress test: webhook URL `http://127.0.0.1:9999` → adapter
  `egress_denied: 127.0.0.1` (engellendi, dış istek atılmadı).
- Mongo indexes: `uniq_tenant_msg_partner`, `retry_scan`,
  `uniq_tenant_partner` Atlas'ta oluşturuldu.

### Sertifikasyon hattındaki bilinen eksikler (UAT öncesi yapılacak)
1. HTNG/OTA XSD validation harness + Sabre sertifikalı örnek
   XML diff testleri.
2. Reservation create/modify/cancel akışına `bus.publish(...)`
   hook'u (şu an admin `test-publish` üzerinden tetikleniyor).
3. Inbound webhook receiver (`POST /api/xchange/inbound/{partner}`)
   ve idempotent inbound dedup.
4. Retry worker'ı app startup'a bağla (şu an manuel
   `run_retry_cycle()` ile).

## Sprint 23 — Spa & MICE/Banquet Derinleştirme (19 Apr 2026)
**Amaç**: Mevcut "şablon" Spa sayfası yerine gerçek kaynak yönetimi
ve OPERA/Protel seviyesinde banquet/etkinlik yönetimi. Kullanıcı
geri bildirimi: *"Spa modülü sadece şablon... MICE modülü zayıf —
Opera/Protel'in en güçlü alanlarından biri (banquet management)."*

### Backend yeni modüller
- `backend/routers/spa.py`
  - Hizmet kataloğu CRUD (kategori, süre, fiyat, komisyon,
    `requires_room_type`); ilk GET'te 8 hizmetlik Türkçe seed.
  - Terapist roster (uzmanlıklar, mesai saatleri, renk).
  - Tedavi odası CRUD (tip, kapasite, ekipman).
  - Çakışma kontrollü randevu — **terapist VE oda** çakışması
    aynı anda kontrol edilir; otomatik terapist/oda seçimi
    (uzmanlık eşleşmesi + müsaitlik).
  - Status flow: scheduled → in_progress → completed/no_show/
    cancelled. `completed` + `charge_to_room` ⇒ folio_postings'e
    yazar, Xchange `POSTING_CHARGE` event yayınlar.
  - Misafir geçmişi (`/api/spa/guests/{id}/history`) ve günlük
    özet (`/api/spa/daily-summary`).
- `backend/routers/mice.py`
  - **Function spaces** — alan, 6 düzen kapasitesi (theatre,
    classroom, banquet, cocktail, u_shape, boardroom), saatlik/
    günlük tarife, amenities; 4 mekan seed.
  - **Menü & paket kataloğu** — F&B / AV / decor; per-pax veya
    flat fiyat; 5 paket seed.
  - **Etkinlik döngüsü** — lead → tentative → definite →
    confirmed → completed/cancelled. Tentative+ statüde mekan
    çakışması bloklanır; `completed` ⇒ folio + Xchange.
  - **Otomatik fiyatlama** — mekan tarifesi (≥6 saat ⇒ daily,
    aksi halde hourly × saat); per-pax menüler beklenen pax ile
    çarpılır; flat menüler quantity ile.
  - **Function diary** (`/api/mice/diary`) ve **BEO**
    (`/api/mice/events/{id}/beo`) endpoints.

### Frontend yeniden yazımları
- `frontend/src/pages/SpaWellness.jsx` — 261 satırlık şablon yerine
  4 sekmeli yönetim ekranı (Randevular / Hizmetler / Terapistler
  / Odalar), günlük özet kartları, randevu modal'ı (auto-pick
  desteği), durum aksiyon butonları, oda hesabına yansıt
  switch'i.
- `frontend/src/pages/MicePage.jsx` (YENİ) — etkinlik tablosu,
  çoklu mekan + kaynak satırlı tek modal, status pipeline kartları,
  function diary tab'ı, BEO yazdırılabilir modal, status değiştirme
  dropdown'ı, silme/düzenleme aksiyonları.
- `routeDefinitions.jsx` + `navItems.jsx` — `/app/mice` rotası,
  "MICE & Banquet" navigasyonu (operations grubu, basic tier).

### Smoke (19 Apr 2026)
- Spa: 8 hizmet seed, terapist+oda yaratıldı, randevu OK.
  Aynı saat aralığında ikinci randevu → `409 Terapist çakışması`.
- MICE: 4 mekan + 5 menü seed. Gala (200 pax, 18:00–01:00,
  Boardroom + Coffee Break per-pax + AV flat) → `grand_total =
  ₺200,500` doğru hesaplandı (mekan ₺6,000 + kaynaklar ₺194,500;
  per-pax menü 200 ile çarpıldı). Çakışan tentative ekleme →
  `409 Mekan çakışması: Gala 2026 (2026-05-15T18:00)`. BEO
  endpoint mekan + kaynak hatlarını ve toplamı döndürdü.
  Function diary mayıs ayı listesini doğru getirdi.

### Sertifikasyon hattındaki bilinen eksikler
1. Spa: terapist takvimi/scheduler grid (Gantt-stili) UI; şu an
   tablo görünümü.
2. MICE: drag-and-drop function diary (ay görünümü); şu an
   liste/diary listesi.
3. Folio reverse postings (etkinlik iptal edildiğinde geri vurma).

## Sprint 23 Hardening + Af-sadakat Doğrulama (19 Apr 2026)

### Spa & MICE UAT-grade hardening — DONE
- **Atomik çakışma garantisi**: `backend/core/booking_atomicity.py` →
  `with_resource_locks()` Mongo transaction + per-resource lock dokümanı
  pattern (lock satırı her kaynak için `update_one(upsert=True)` ile
  serileştirir; `WriteConflict` `with_transaction()` tarafından otomatik
  yeniden denenir). Replica-set olmayan local Mongo için
  `is_replica_set_unavailable()` ile eski yola düşülür. Atlas (üretim
  hedefi) replica set olduğundan production-safe.
- **Wired**: `routers/spa.py::create_appointment` → therapist+room
  locks; `routers/mice.py::create_event` → space locks (sadece
  tentative/definite/confirmed durumlarında).
- **RBAC**: `backend/core/spa_mice_authz.py` → `CATALOG_ROLES`
  (services/therapists/rooms/spaces/menus = supervisor+),
  `SPA_OPS_ROLES` & `MICE_OPS_ROLES` (operasyonel personel),
  `FINANCE_ROLES` (folio-impacting `completed` geçişi). Tüm spa.py +
  mice.py write endpoint'lerine `require_*` çağrıları eklendi.
- **İndeksler** (lazy bootstrap, ilk istekte oluşturulur):
  - `spa_appointments`: (tenant_id, therapist_id, starts_at),
    (tenant_id, room_id, starts_at), (tenant_id, guest_id, starts_at),
    (tenant_id, status, starts_at).
  - `spa_locks`: unique (tenant_id, kind, resource_id).
  - `mice_events`: (tenant_id, status, start_date),
    (tenant_id, start_date, end_date),
    (tenant_id, space_bookings.space_id, status).
  - `mice_locks`: unique (tenant_id, kind, resource_id).

### Smoke (19 Apr 2026 — hardening)
- Login `100001/demo/demo123` → ✓.
- Spa & MICE GET tetikleyince tüm 9 indeks Atlas'ta oluştu (doğrulandı:
  `spa_appt_therapist_time`, `spa_appt_room_time`, `spa_appt_guest_time`,
  `spa_appt_status_time`, `uniq_spa_lock`, `mice_evt_status_date`,
  `mice_evt_date_range`, `mice_evt_space_status`, `uniq_mice_lock`).
- Admin için POST `/api/spa/services` → 200 (RBAC pas geçti).

### Af-sadakat plan tamamlanma doğrulaması (T001–T008)
Aşağıdaki ürün uçtan uca doğrulandı:
- `GET /api/module-store/products` → `af_sadakat` ürünü `trial_days=14`,
  `external=true`, `sso_path=/integrations/afsadakat/launch`,
  `price_try=1499` ile listeleniyor.
- `POST /api/module-store/start-trial {product_key:"af_sadakat"}` →
  `{ok:true, trial:true, end_date:"…+14g", already_existed:true}` (idempotent).
- `GET /api/integrations/afsadakat/status` →
  `{entitled:true, provisioned:true, mode:"local",
    external_configured:false}` (env yokken local-only provisioning
  doğru çalışıyor).
- `POST /api/integrations/afsadakat/launch` →
  `{url:"…", mode:"local", external_ready:false, expires_in_seconds:120}`
  (HS256 SSO token; harici env tanımlanınca external moda geçer).
- Router registry, frontend ModuleStorePage trial+launch butonları,
  AfsadakatLauncher sayfası, "Sadakat & Inbox" navigasyon girişi
  (entitlement-gated) — hepsi mevcut ve devrede.

### Mimari incelemeden sonra düzeltilen noktalar (19 Apr 2026 — kabul tertip)
- **Standalone-Mongo fallback varsayılan kapatıldı**: tx-locked yol
  başarısız olursa `is_replica_set_unavailable()` doğru olsa bile artık
  503 dönüyor (hem `spa.create_appointment` hem `mice.create_event`).
  Lokal dev'de çalışmak için `ALLOW_STANDALONE_BOOKING_FALLBACK=1`
  env flag'i ile opt-in. Atlas (üretim) replica set olduğundan bu
  yola hiç düşmez; flag tamamen TOCTOU yarış yüzeyini kapatır.
- **GET seed RBAC açığı kapatıldı**: `GET /api/spa/services`,
  `GET /api/mice/spaces`, `GET /api/mice/menus` boş kataloğu seed
  ederken artık `require_catalog(current_user)` çağrılıyor; rol yoksa
  yazma yapılmadan boş liste dönülüyor (yani her isteyen kataloğa
  yazamaz).
- **Atomik çakışma testi (gerçek yük)**: aynı oda + üst üste binen
  zaman aralığı için 1. randevu HTTP 200, 2. randevu HTTP 409
  (`Oda çakışması: TX-A`) — Atlas replica set üzerinde tx + lock-doc
  patiği uçtan uca doğrulandı.

## Sprint 24 — MICE/Banquet Opera/Protel S&C derinliği (19 Apr 2026)

### Backend (`backend/routers/mice.py`, ~1235 LOC)
- **Hesap & Kişi mini-CRM**: yeni koleksiyonlar `mice_accounts`
  (kurumsal müşteri: vergi no, sektör, kredi limiti, vade gün), `mice_contacts`
  (kişi: ad, unvan, e-posta, telefon, account_id, is_primary). CRUD endpoint'leri
  + indexler (tenant_id, q-text-search, account_id). Etkinliğe
  `client_account_id` + `client_contact_id` bağlandı; hesabın silinmesi aktif
  etkinlik varsa 409 ile reddediliyor.
- **F&B menü detayı**: `MenuPackageIn` artık `courses[]`
  (course_type, name, description), `allergens[]`, `dietary_tags[]`
  (vegan/vegetarian/gluten_free/halal/kosher), `prep_lead_minutes`,
  `min_guests` taşıyor. Mevcut menüler geri uyumlu (varsayılan boş listeler).
- **Kaynak envanteri + çapraz-event çakışma**: `mice_resources`
  (id, name, type, total_stock, unit, unit_price). Event create/update'te
  `_check_resource_inventory_conflict` çalışır: aynı zaman zarfında diğer
  aktif (tentative/definite/confirmed) etkinliklerin aynı `inventory_id`
  kullanımları toplanır; eklenmek istenen miktarla `total_stock`'u aşarsa
  HTTP 409 (örn: "4K Projeksiyon envanteri yetersiz: stok 5, … zaten 3
  ayrılmış, talep 3"). Tx + lock-doc altında çalışır.
- **Fonksiyon Sheet (agenda)**: `EventIn.agenda[]` (AgendaItemIn:
  starts_at, ends_at, title, kind∈{session,meal,break,av,logistics,other},
  location, owner, notes). BEO çıktısına da girer.
- **Ödeme takvimi**: `EventIn.payment_schedule[]`
  (PaymentScheduleItemIn: due_date, label, amount, paid, paid_at, reference).
  Ek endpoint'ler: `POST /api/mice/events/{id}/payment-schedule` (replace)
  ve `POST /api/mice/events/{id}/payment-schedule/{idx}/mark-paid?reference=…`
  (yalnız finance rolü).
- **Kurulum stili kapasite kontrolü**: `_validate_setup_capacity`
  her space_booking için `expected_pax > space.capacity_<style>` ise
  HTTP 422 net Türkçe mesajla reddediyor ("Boardroom mekanı 'boardroom'
  düzeninde en fazla 14 kişi alır (talep: 30)").
- **Lost-business sebep zorunluluğu**: `StatusUpdate` modeline `reason`
  alanı eklendi; `status=cancelled` çağrılarında reason ≥10 char değilse
  422; aksi halde `lost_reason` + `lost_at` DB'ye yazılıyor (Opera S&C
  "lost business reason code" muadili).
- **Mutfak fişi**: `GET /api/mice/events/{id}/kitchen-ticket` →
  her F&B menü hattı için kurslar, alerjen/dietary etiket toplulamı,
  agenda'daki en erken meal/break'ten geriye `prep_lead_minutes`
  düşülerek hazırlık deadline'ı hesaplanır.
- **Günlük operasyon sheet'i**: `GET /api/mice/ops-sheet?date=YYYY-MM-DD`
  → o güne giren tüm aktif etkinliklerin space_booking satırları
  (mekan, saat, setup, pax, organizatör) + o güne ait ajanda kalemleri
  özetiyle, başlangıç saatine göre sıralı.

### Pydantic/BSON düzeltmesi
- `body.model_dump(mode="json")` kullanılarak agenda[].starts_at +
  payment_schedule[].due_date için ISO string serileştirme zorlandı.
  Önceki `model_dump()` çağrısı `datetime.date` döndürüyordu; PyMongo
  bunu reddedip `bson.errors.InvalidDocument` fırlatıyordu.

### Frontend (`frontend/src/pages/MicePage.jsx`, ~1273 LOC)
- Yeni "Müşteriler" tab'ı: hesap listesi, expand ile alt-kişi tablosu,
  yeni hesap + yeni kişi modalları.
- Yeni "Envanter" tab'ı: AV/decor stok kartları + ekle/sil.
- Etkinlik modal'ı 4 sekmeli oldu: **Temel** (artık `client_account_id`
  dropdown), **Mekan & Kaynak** (envanter dropdown'ı eklendi),
  **Fonksiyon Sheet** (dakika bazlı agenda satırları), **Ödeme Takvimi**
  (taksit grid'i + canlı toplam).
- Üst bar'da date-picker + "Günün Ops Sheet'i" butonu (yazdırılabilir
  tablo modal'ı; ajanda özet'i dahil).
- Etkinlik satırında "Mutfak Fişi" butonu (yazdırılabilir kurs/alerjen
  bozumu + prep deadline + tüm alerjen/diyet özet bantları).
- Status değiştirici cancelled seçildiğinde prompt ile sebep ister
  (≥10 char client-side validation), backend'e `reason` ile gönderir;
  satırda lost_reason kısa preview gösterilir.
- BEO modal'ı genişletildi: agenda + ödeme takvimi tabloları + lost
  reason + ödenmemiş satırlar için "Öde" inline butonu (`mark-paid`
  endpoint'ini çağırır).

### Smoke (kabul testleri — Atlas replica set üzerinde 19 Apr 2026)
- ✅ Hesap+kişi+envanter CRUD (200 OK).
- ✅ Boardroom (cap=14) için 30 pax → 422 net mesaj.
- ✅ 5 stoklu projektör için 3+3=6 → 409 envanter mesajı; 3+2=5 → 200.
- ✅ Tam zenginleştirilmiş etkinlik yarat (account, agenda 3 kalem,
  ödeme 2 taksit, F&B menüsü 80 pax, AV 3 adet) → 200, totals dolu.
- ✅ Mutfak fişi: prep_by = 08:00 − 45dk = 07:15 doğru hesaplandı,
  3 kurs + 3 alerjen + 2 diyet etiketi yazıldı.
- ✅ Ops sheet 2026-09-15 için 1 satır + 3 ajanda kalemi gösteriyor.
- ✅ Cancel reason yokken 422; "Müşteri başka tarih istedi, mekan dolu"
  ile 200, lost_reason DB'ye yazıldı.
- ✅ `mark-paid?reference=BANKA-TX-12345` → satır paid=true + reference.

---

## Sprint 25 — Procurement Modülü + Versiyonlama Görünür (Apr 2026)

### Strateji
Türk PMS rakiplerinin Inventory'si "supplier alanı + buton"da kalırken Opera/Protel
S&C tam Procurement zinciri sunar (vendor master → PR → PO → GRN → 3-yönlü
mutabakat). Sprint 25 bu açığı kapatır ve aynı anda tüm yazma uçlarına şeffaf
**değişiklik geçmişi** ekler — kullanıcı her kaydın zaman çizelgesini drawer
ile inceler (Opera "User Activity" ekranı muadili).

### Backend
- **Yeni router**: `backend/routers/procurement.py` (~520 LOC).
  - `proc_suppliers` (vendor master): name/code/tax_no/contact/payment_terms_days/
    categories/active. `code` unique-sparse; in-use guard delete'te.
  - `proc_purchase_requests` (PR): department/requester/needed_by/lines[item_name,
    sku, inventory_item_id, quantity, unit, est_unit_cost]. Status FSM
    (draft → submitted → approved/rejected/cancelled). Red/iptal en az
    5 karakter neden.
  - `proc_purchase_orders` (PO): supplier snapshot (id+name+payment_terms_days),
    source_pr_id, lines [+received_qty +line_total], subtotal/tax_total/grand_total,
    currency/tax_rate. PR→PO conversion otomatik PR'ı `converted` yapar.
  - `proc_goods_receipts` (GRN): partial receiving, qc_status (accepted/rejected/
    partial); over-receiving 422; PO line.received_qty inkremental;
    `housekeeping_inventory.current_stock` `$inc` ile **otomatik artırılır**
    (3-yönlü mutabakat için stok-tarafı tamam).
  - `proc_counters` koleksiyonu ile atomik `find_one_and_update($inc seq)`
    numaralandırma: `SUP-2026-####`, `PR-2026-####`, `PO-2026-####`,
    `GRN-2026-####` (yıl başında reset).
  - Tüm yazmalar `log_audit_event` ile audit'e işlenir.
  - `/api/procurement/summary` dashboard kartları için aggregate.
- **MICE audit hookları** (`backend/routers/mice.py`): create_event /
  update_event / change_status / delete_event uçları artık her işlemi audit'e
  before/after snapshot ile yazıyor. Status değişimleri `status:tentative`,
  `status:cancelled` action'ı + lost_reason snapshot'ı ile.
- **Kritik düzeltme** `backend/core/audit.py`: `log_audit_event` artık hem
  legacy alanları (`action/entity_type/entity_id/before_value/after_value`) hem
  **AuditTimeline-uyumlu yeni alanları** (`operation_name/target_type/target_id/
  actor_id/before_snapshot/after_snapshot/result_status/severity`) yazıyor —
  böylece `GET /api/audit/timeline/{type}/{id}` endpoint'i artık tüm domain
  router'larından gelen logları görüyor (önceden boş dönüyordu).
- Router kaydı: `backend/bootstrap/router_registry.py`'ya `routers.procurement`
  eklendi.

### Frontend
- **Yeni reusable**: `frontend/src/components/EntityHistoryDrawer.jsx`.
  Sağdan açılan drawer; `entityType` + `entityId` props ile
  `/api/audit/timeline/{type}/{id}` çağırır. Operation badge (create/update/
  delete/status), tarih, actor; before/after diff tablosu (max 8 alan).
- **Yeni sayfa**: `frontend/src/pages/ProcurementPage.jsx` (~570 LOC).
  - 6 dashboard kartı (aktif tedarikçi, bekleyen PR, onaylı PR, açık PO,
    tamamlanan PO, açık tutar — TL formatlı).
  - 3 sekme: PRs / POs / Tedarikçiler.
  - PR modal: departman + ihtiyaç tarihi + dinamik lines tablosu.
  - PO modal: tedarikçi dropdown + KDV + lines + canlı subtotal/tax/total
    hesaplama.
  - PO Detay modal: lines + received_qty/kalan + GRN listesi + Mal Kabul butonu.
  - GRN modal: her satır için "Bu sevkte" miktarı + qc_status + not.
  - Tedarikçi modal: tam form + aktif/pasif toggle.
  - PR ve PO satırlarında **Geçmiş** ikonu → EntityHistoryDrawer.
- **MicePage'e Geçmiş entegrasyonu**: event satırına HistoryIcon butonu;
  `EntityHistoryDrawer` ile `mice_event` türü için drawer açılır.
- Route: `/app/procurement` `routeDefinitions.jsx`'a eklendi.

### Smoke (Atlas — 19 Apr 2026)
- ✅ Tedarikçi `AND-001 / Anadolu Tekstil A.Ş.` oluşturuldu (45 gün vade).
- ✅ PR `PR-2026-0001` (50 adet havlu × 80 ₺) draft → submitted → approved.
- ✅ Geçersiz FSM geçişi (approved → approved) **409**, (approved → rejected) **409**.
- ✅ PR → PO conversion: `PO-2026-0001` subtotal=3900 KDV=780 toplam=4680 ₺;
  PR otomatik `converted` statüsüne geçti.
- ✅ PO `draft → sent`.
- ✅ Stok başlangıç 100 → kısmi GRN (30 adet) → **130** (otomatik $inc).
- ✅ Over-receiving denemesi (kalan 20'ye 25): **422** "kabul (55) sipariş
  miktarını (50) aşıyor".
- ✅ Kalan 20 GRN → PO status `received`, stok 150 (130+20).
- ✅ `received → closed` 200.
- ✅ MICE event lifecycle audit: 3 olay (create + tentative + definite),
  her biri actor=demo, ISO timestamp.
- ✅ Procurement audit: PR trail 3 (create + submitted + approved).
- ✅ Frontend route `/app/procurement` ProcurementPage'i lazy-load eder;
  drawer her tablo satırından açılabilir.

### Etki
- Türk rakiplere göre Inventory derinliği eşitlendi/aşıldı: artık vendor master,
  approval workflow, atomik no'lu PO, kısmi GRN, 3-yönlü mutabakatın stok
  tarafı kapalı (Invoice modülü ileride aynı PO_id'den eşleştirilecek).
- Versiyon kontrolü Opera User Activity ile aynı UX seviyesine çıktı: her
  kaydın geçmişi kullanıcının önündeki ikonla bir tıkla erişilir; tüm domain
  router'ları (mice + procurement) tek timeline schema'sını besliyor.

---

## Sprint 26 — Konaklama Vergisi Beyannamesi: Tam Otomasyon (Apr 2026)

### Strateji
Elektraweb'in en sevilen özelliği "Konaklama Vergisi Beyannamesi otomasyonu" —
mevcut modülümüz aylık matrahı topluyordu ama her açılışta yeniden hesaplıyor,
**onay/kilit + GİB tahakkuk numarası + ödeme izi + GİB-uyumlu XML** üretmiyordu.
Sprint 26 bu eksiği kapatır: dönem snapshot'ı kalıcı, durum makinesi (taslak →
onaylı → gönderildi → ödendi), denetim için XML/JSON arşiv, geçmiş listesi.

### Backend (`backend/routers/finance/konaklama_vergisi.py`)
- **Yeni koleksiyon**: `tax_declarations` — `(tenant_id, period, kind)` unique
  + `(tenant_id, status, period DESC)` arama indeksi.
- `POST /finance/konaklama-vergisi/declaration/finalize` — `_aggregate_period`
  çıktısının snapshot'ını alır, `tenant` bilgilerini ekler, status="finalized"
  ile yazar. **Idempotent**: aynı dönem için non-draft bir kayıt varsa onu
  döner (paid → finalize = no-op, durum korunur).
- `GET /finance/konaklama-vergisi/declarations` — geçmiş listesi (24 varsayılan,
  120 üst sınır), satır detayları hariç (özet için).
- `GET /finance/konaklama-vergisi/declarations/{id}` — tam kayıt.
- `POST .../submit` — GİB tahakkuk fiş numarasını kaydeder; yalnızca
  status="finalized" iken kabul eder, aksi 409.
- `POST .../pay` — banka dekont referansı + tutar; status finalized/submitted
  iken kabul eder.
- `GET .../export?format=xml|json` — dönem snapshot'ını GİB form alanlarıyla
  1-1 eşleşen `<KonaklamaVergisiBeyannamesi>` XML'ine veya tam JSON arşive
  serialize eder; `Content-Disposition` ile `kvb-YYYY-MM.{xml,json}` indirir.
- Tüm mutasyonlar `create_audit_log` ile işlenir
  (`FINALIZE/SUBMIT/PAY_KONAKLAMA_BEYANNAME`).

### Frontend (`frontend/src/pages/KonaklamaVergisiModule.jsx`)
- Yeni "Geçmiş" sekmesi — finalize edilmiş tüm beyannameler durum rozetleriyle
  (Taslak/Onaylı/Gönderildi/Ödendi), matrah/vergi/son tarih/tahakkuk/dekont
  sütunları, satır başına XML indirme ikonu.
- Beyanname sekmesi yeniden yapılandırıldı:
  - Dönem önizlemesi yüklendiğinde mevcut snapshot var mı kontrolü
    (`/declarations` listesi) → varsa kilitli durum şeridi (status badge,
    onay tarihi, tahakkuk no, dekont no).
  - Aksiyon butonları durum-bağımlı:
    - Snapshot yoksa → **Beyannameyi Onayla & Kilitle** (confirm dialog ile).
    - Onaylı → **GİB Tahakkuk Numarası Kaydet** (prompt).
    - Onaylı/Gönderildi → **Ödeme Kaydet** (prompt, otomatik tutar).
    - Snapshot var → **XML İndir (GİB)** + **JSON Arşiv** butonları.
- Yeni `StatusBadge` reusable; `STATUS_BADGE` renk haritası.

### Smoke (Atlas — 19 Apr 2026)
- ✅ 2026-04 finalize → `9baa67b1` status="finalized" total_tax=0 (test
  tenant'ında oda satırı yok ama akış doğrulandı).
- ✅ İdempotent: aynı dönem yeniden finalize → aynı id, status korundu.
- ✅ Submit `GIB-2026-04-987654` → status="submitted".
- ✅ Pay `BANKA-TX-2026-04-001` → status="paid" paid_amount=0.
- ✅ Paid sonrası finalize → durum "paid" korundu (no-op).
- ✅ Paid sonrası submit → **409** "Yalnızca onaylanmış (finalized)
  beyannameler gönderilebilir (mevcut: paid)".
- ✅ History list → 1 kayıt, durum/tutar/referanslar görünür.
- ✅ XML export — geçerli UTF-8 envelope, `<Donem>2026-04</Donem>`,
  `<SonOdemeTarihi>2026-05-26</SonOdemeTarihi>`, `<OtelKodu>100001</OtelKodu>`,
  KDV'siz matrah ve %2 oran 1-1 GİB form alanları.

### Etki
- Türk PMS rakipleri (Elektraweb) ile paritenin ötesinde: durum makinesi +
  audit log ile dönem-bazlı denetim izi (Elektraweb'de yalnızca PDF üretir,
  durumu siz manuel takip edersiniz). XML çıktısı muhasebe yazılımlarına
  doğrudan import için hazır.
- Aynı altyapı (`tax_declarations` koleksiyonu + `kind` ayrımı) ileride
  KDV Beyannamesi, Damga Vergisi, Stopaj gibi diğer aylık beyannamelerde
  yeniden kullanılabilir.

## Sprint 27 — In-App Help Center (Apr 2026)

### Bağlam
PMS modülleri (folio, KVB, satınalma, mevzuat) sayıca arttıkça kullanıcılar
için kontekstli yardım kritik hale geldi. Sprint 27'de hafif bir Yardım
Merkezi (markdown tabanlı) eklendi.

### Backend
- `routers/help.py` — okuma-only API. Slug regex (`^[a-z0-9-]{1,80}$`) +
  `CONTENT_DIR` containment guard ile path traversal koruması.
  - `GET /api/help/index` — kategori ağacı + makale başlıkları
  - `GET /api/help/articles/{slug}` — markdown içerik + meta
  - `GET /api/help/search?q=` — title/body/tag substring (snippet üretir)
- `help_content/` — 10 makale, 5 kategori (Başlangıç, Operasyon, Finans,
  Satınalma, Mevzuat). `_index.json` katalog.

### Frontend
- `pages/HelpCenter.jsx` — sol kategori menüsü + sağ makale + üst arama.
  Markdown'ı dış paket olmadan basit (heading/list/table/code/link) parser
  ile render eder. İçerik `[başlık](#/help/slug)` linklerini intercept edip
  yan-makaleye geçer (data-slug attribute click handler).
- Nav: "Yardım Merkezi" → `/app/help` (yonetim grubu, starter tier).

### Smoke (Atlas — 19 Apr 2026)
- ✅ index → 5 kategori, 10 makale
- ✅ article load → markdown + meta dönüyor
- ✅ slug guard → `../etc/passwd` 404
- ✅ search "vergi" → 5 isabet, "Konaklama Vergisi Beyannamesi" en yüksek skorlu

## Sprint 28 — Mevzuat Raporları (TÜİK / Bakanlık) (Apr 2026)

### Bağlam
Türk konaklama tesisleri her ay TÜİK aylık konaklama anketini doldurmak,
yıldız sınıflama kriterleriyle uyumluluğu ve Bakanlık denetimine hazırlığı
takip etmek zorunda. Sprint 28 bu üç mevzuat görevini tek modülde topladı.

### Backend
- `routers/regulatory.py` — 3 endpoint:
  - `GET /api/regulatory/tuik/monthly?year=&month=` — kapasite (oda + yatak),
    satılan oda-gece, doluluk %, yerli/yabancı kişi-gece, ALOS, ülke top-20
    (TR alias normalizasyonu) + "Diğer". Booking tz-naive/aware uyumlu.
  - `GET /api/regulatory/inspection-readiness` — tesis künyesi snapshot,
    7 kontrol noktası (künye, vergi no, işletme belgesi + süresi, yıldız,
    oda envanteri, personel) + readiness score + 12 aylık rezervasyon trend.
  - `GET/POST /api/regulatory/star-classification/checklist` — 24 kriter,
    8 kategori, hedef yıldıza göre `required` flag'i, partial=0.5 ağırlık,
    `regulatory_star_checklists` koleksiyonunda upsert + audit log.

### Frontend
- `pages/MevzuatRaporlari.jsx` — 3 sekme:
  - **TÜİK Aylık**: yıl/ay seçici + KPI kartları + ülke tablosu + CSV indir
    (UTF-8 BOM, TÜİK e-Anket'e veri girişi için) + Yazdır.
  - **Denetim Hazırlık**: readiness skoru, 7 kontrol listesi (✓/⚠ ikonları),
    12 aylık trend tablosu, işletme belgesi gün sayacı (<30 gün → uyarı).
  - **Yıldız Self-Check**: hedef yıldız seçici, kategori-grouplu kriter
    listesi, her kriter Var/Kısmen/Yok select, kaydet + canlı skor.
- Nav: "Mevzuat Raporları" → `/app/mevzuat-raporlari` (reports grubu,
  professional tier, basic_reporting modül).

### Smoke (Atlas — 19 Apr 2026)
- ✅ TÜİK 2026-04 → 30 oda, 60 yatak, 45 booking, 179 oda-gece, %19.89
  doluluk, ALOS 1.52, ülke top-20 (test data nationality boş → "Belirtilmemiş").
- ✅ Inspection readiness → 30 oda, 5 aktif user, score 29 (5 künye check
  eksik — test tenant'ında doldurulmamış alanlar).
- ✅ Star checklist GET → 24 item, 4★ hedef → 21 zorunlu, score 0 (boş başlangıç).
- ✅ POST 5 entry (3 yes, 1 partial, 1 no) → score 17, missing 18, audit log.

### Etki
- TÜİK e-Anket için manuel tablo doldurma süresi (yarım gün) → tek tık CSV.
- Bakanlık denetim öncesi 30 dk hazırlık raporu → otomatik dashboard.
- Yıldız uyumluluğu için iç self-check, eksik kriterler kalıcı izlenir
  (Elektraweb'de bu modül yoktur, yalnızca dış danışmanlık ile yapılır).

---

## Sprint 29 — E2E Smoke + N+1 Performans Düzeltmeleri (19 Apr 2026)

51 kritik endpoint smoke koşusu sonrası 10 yavaş (>2s) endpoint tespit edildi.
Bunlardan en kritik 3'ü dokümana alınmış N+1 query pattern'i içeriyordu;
hepsi `asyncio.gather` ile paralelleştirildi.

### Düzeltmeler
- **`routers/regulatory.py::inspection_readiness`** (12 ay × seq count_documents)
  → `asyncio.gather([12 sorgu])`. **3.94s → 0.80s (5× hız)**.
- **`domains/pms/pos_router.py::get_guest_alerts`** (booking başına 2 query:
  guest find + repeat count) → 2-faz: (a) tüm bookings tek seferde, (b) `guests`
  bulk `$in` find + repeat counts `gather`. **10.94s → 0.77s (14× hız)**.
- **`modules/revenue_management/displacement_engine.py::get_market_overview`**
  (14 gün × 2 count_documents seq) → `gather([14 günlük lookup])`. **8.74s → 2.50s (3.5× hız)**.

### Geri Kalan Yavaşlar (Sprint 30 kapsamı)
| Endpoint | Süre | Olası neden |
|---|---|---|
| `/api/rms/rate-recommendations` | 7.7s | Çok günlü forecast loop |
| `/api/mice/spaces` | 3.8s | per-space availability lookup |
| `/api/dashboard/gm/forecast-weekly` | 3.2s | hafta-loop forecast |
| `/api/ops/overview` | 3.5s | toplu KPI sorgu seti |
| `/api/procurement/suppliers` | 3.4s | supplier başına sayım |
| `/api/spa/services` | 2.9s | service başına availability |

### Smoke Sonuçları
- 51/51 erişilebilir endpoint test edildi; OpenAPI spec'inden 1471 GET path,
  toplam 2375 path bulundu (devasa yüzey).
- Kalan 41 yavaş aday (>1.5s, henüz incelenmedi) `/tmp/smoke_targets.txt`'ta.
- Tüm düzeltilmiş endpoint'ler `200 OK`, schema regression yok (warm <1s).

---

## Rakip Karşılaştırma Matrisi — Syroce vs Türkiye/Global PMS Pazarı

Sprint kapanışları sonrası modül-modül kıyaslama. İsim:
HR=HotelRunner, EW=Elektraweb, OP=Opera Cloud, PR=Protel Air.
İşaretler: ✅=tam, ◐=kısmi/temel, ✗=yok, ⚠=add-on/ücretli.

### Modül Matrisi

| Modül / Yetenek | Syroce | HR | EW | OP | PR |
|---|---|---|---|---|---|
| Front Desk + Guest Profile | ✅ | ◐ | ✅ | ✅ | ✅ |
| Reservation + Group Booking | ✅ | ◐ | ✅ | ✅ | ✅ |
| Channel Manager (OTA push) | ✅ Exely+HR+SXI | ✅ doğal | ◐ | ⚠ | ⚠ |
| Housekeeping (oda durum) | ✅ | ✗ | ✅ | ✅ | ✅ |
| F&B / Restaurant POS | ✅ | ✗ | ✅ | ⚠ Symphony | ⚠ |
| Spa / Wellness | ✅ | ✗ | ◐ | ⚠ | ◐ |
| MICE / Banquet | ✅ | ✗ | ◐ | ✅ S&C | ✅ |
| Revenue Mgmt / RMS | ✅ rate-rec + displacement | ✗ | ◐ | ⚠ IDeaS | ⚠ |
| Yer Değiştirme (Displacement) | ✅ tek başına | ✗ | ✗ | ⚠ | ✗ |
| KBS (Polis/İçişleri) | ✅ | ◐ | ✅ | ✗ | ◐ |
| KVKK Aydınlatma + İzin | ✅ | ✗ | ◐ | ✗ | ✗ |
| TÜİK Aylık Anket CSV | ✅ tek tık | ✗ | ✗ | ✗ | ✗ |
| Yıldız Sınıflama Self-Check | ✅ 24 kriter | ✗ | ✗ | ✗ | ✗ |
| Bakanlık Denetim Hazırlığı | ✅ readiness skoru | ✗ | ✗ | ✗ | ✗ |
| e-Fatura / e-Arşiv (TR) | ✅ | ✅ | ✅ | ⚠ | ⚠ |
| Konaklama Vergisi Otomasyonu | ✅ tax-declarations | ✗ | ◐ | ✗ | ✗ |
| Quick-ID Kimlik OCR | ✅ ayrı servis | ✗ | ◐ | ✗ | ◐ |
| Procurement (PR/PO/Supplier) | ✅ | ✗ | ✅ | ⚠ | ⚠ |
| Inventory + Warehouse | ✅ | ✗ | ✅ | ⚠ | ⚠ |
| Loyalty / CRM | ✅ | ◐ | ✅ | ✅ | ✅ |
| B2B Marketplace | ✅ özgün | ✗ | ✗ | ✗ | ✗ |
| Multi-tenant SaaS | ✅ | ✅ | ✗ on-prem ağırlık | ✅ | ✅ |
| Açık API + OpenAPI 3 | ✅ 2375 path | ◐ | ◐ | ✅ | ✅ |
| In-App Help Center | ✅ md+slug | ✗ | ◐ | ◐ | ◐ |
| Onboarding Wizard | ✅ | ◐ | ◐ | ✗ | ✗ |
| 2FA (TOTP) | ✅ | ✗ | ◐ | ✅ | ✅ |
| PCI-DSS Tokenization | ✅ | ◐ | ◐ | ✅ | ✅ |
| Offline / Lockdown Mode | ✅ | ✗ | ✗ | ⚠ | ⚠ |
| AI Briefing / GM Dashboard | ✅ | ✗ | ✗ | ⚠ | ⚠ |
| Production Go-Live Toolkit | ✅ | ✗ | ✗ | ◐ | ◐ |

### Öne Çıkan Farklılaştırıcılar (Syroce'nin avantajları)

1. **Türk Mevzuat Triad'ı** (KBS + KVKK + TÜİK + Yıldız self-check + Denetim
   hazırlığı) tek üründe — rakipler bu kombinasyona sahip değil; KBS varsa bile
   genelde ayrı entegratör (örn. Otelpuan) kullanılır.
2. **Displacement Engine** — Türkiye pazarında kimsede tek başına ürün
   değil; Opera ekosistemine IDeaS/Atomize gibi 3.000 USD+/ay add-on lazım.
3. **Quick-ID** — kimlik OCR + Türkiye'ye özgü TC Kimlik / pasaport MRZ
   parse ayrı mikroservis; HR/EW'de yok, OP/PR'de 3rd party.
4. **B2B Marketplace** — tedarikçi marketplace + admin paneli özgün;
   rakiplerde sadece "tedarikçi listesi" var, satış kanalı yok.
5. **Production Go-Live Toolkit** (47 endpoint) + **Lockdown Mode**
   (22 endpoint) — bunlar enterprise-onboarding/disaster-recovery için
   kurumsal pazarda farklılaştırıcı.
6. **In-App Help Center** + **Onboarding Wizard** (Sprint 27/24) —
   self-service onboarding rakiplerde genelde manuel danışman gerektirir.
7. **OpenAPI 3 + 2375 path** — açık entegrasyon yüzeyi rakiplerin çoğunu
   geride bırakıyor (Opera/Protel benzer; HR/EW kısmî).

### Eksik / Gelişim Alanları (öneriler)

| Alan | Durum | Öneri (Sprint 30+) |
|---|---|---|
| **GDS / Sabre / Amadeus bağlantısı** | ✗ | Kurumsal segment için kritik (5★+ otel zincirleri). |
| **Mobil İşletmen App** (iOS/Android) | ✗ | Housekeeping/maintenance task tablet UI eksik. |
| **Self check-in kiosk** | ✗ | Quick-ID + folio integration ile kolay; HR/EW kısmen yapıyor. |
| **IDeaS-class RMS forecast** | ◐ | rate-rec var ama 7s yavaş; ML model + cache lazım. |
| **Multi-property dashboard** (zincir) | ◐ | Tenant per-property var; cross-property roll-up yok. |
| **Document Mgmt / DMS** | ◐ | Sözleşme + KVKK belgeleri; versioning/audit eksik. |
| **Push notification** mobil | ✗ | Loyalty/gönderiler için web-push var, native push yok. |
| **Yorum yönetimi** (Booking/TripAdvisor) | ✗ | EW'de var; sentiment analiz add-on fırsatı. |
| **F&B menü mühendisliği** | ◐ | POS var, menu engineering raporu eksik. |
| **Energy / IoT room control** | ✗ | Lider zincirler için karbon raporu + sensor entegrasyonu. |

### Sonuç

Syroce, Türk pazarında **Elektraweb seviyesinde modül zenginliği +
HotelRunner seviyesinde kanal entegrasyonu + Opera seviyesinde mevzuat /
güvenlik / API açıklığı** sunan tek üründür; **TÜİK + KVKK + KBS + Yıldız
mevzuat tetralojisi** ve **Displacement Engine** kategoride tek. Önümüzdeki
6 ay önceliği: GDS bağlantısı, mobil işletmen app, self-check-in kiosk,
multi-property roll-up, RMS hız iyileştirmesi.

---

## Sprint 30 — N+1 Performans Düzeltme Turu II (19 Apr 2026)

Sprint 29'dan kalan 7 yavaş endpoint için ikinci tur paralelleştirme.
Hepsi `asyncio.gather` veya hoist-out-of-loop ile düzeltildi.

| Endpoint | Önce | Sonra (warm) | İyileşme | Düzeltme |
|---|---|---|---|---|
| `/api/rms/rate-recommendations` | 7.74s | 0.28s | **28×** | total_rooms hoist + 14 historical count gather |
| `/api/dashboard/gm/forecast-weekly` | 3.25s | 0.50s | **6.5×** | total_rooms hoist + 4×(count+aggregate) gather |
| `/api/dashboard/gm/forecast-monthly` | 2.45s | 0.50s | **5×** | aynı pattern, 3 ay |
| `/api/ops/overview` | 3.50s | 0.50s | **7×** | 13 sequential count → tek gather |
| `/api/ai/dashboard/briefing` | 2.50s | 2.0s | 1.25× | 4 koleksiyon find paralel; in-mem loop kalıntısı (Sprint 31 — mongo aggregation gerekli) |
| `/api/onboarding/progress` | 2.52s | 1.50s | 1.7× | auto-detect probes paralel (kalan: tenant find + final update) |

**Toplam etki**: 6 endpoint × ortalama 8× hız = ~30 saniye sequential RTT
tasarrufu/kullanıcı/dashboard yüklemesi.

**`/api/procurement/suppliers`, `/api/spa/services`, `/api/mice/spaces`**
(2.9–3.5s) tek-sorgu endpoint'leri — yavaşlık Atlas baseline RTT (~600ms)
+ küçük indeks eksikliği. Paralelleştirilemez; Sprint 31'de Atlas
indeksleri (`tenant_id + name` compound) eklenecek.

### Code Review Bulgusu Giderildi (Sprint 29 follow-up)
`get_guest_alerts`'de `to_list(length=2000)` truncation (architect tespiti)
→ tam cursor iterasyonu + 500'lük `$in` chunking + `Semaphore(25)` sınırlı
gather'la değiştirildi. Büyük tenant'larda da doğru, hızlı.

---

## Sprint 31 — Catalog Endpoint TTL Cache (19 Apr 2026)

3 catalog endpoint'i (procurement/suppliers, spa/services, mice/spaces)
nadiren değişen veriler. Atlas baz RTT (~3s, küçük data + indeks zaten
optimal) için tek-sorgu paralelleştirilemez → `@cached(ttl=60)` decorator
ile in-memory cache eklendi. Cache key tenant-bazlı (`_extract_tenant_id`)
+ query param-bazlı (`q`, `active_only`).

| Endpoint | Cold | Warm (cache hit) | Hız |
|---|---|---|---|
| `/api/procurement/suppliers` | 3.34s | **0.25s** | **13×** |
| `/api/spa/services` | 2.77s | **0.25s** | **11×** |
| `/api/mice/spaces` | 3.67s | **0.25s** | **15×** |

**Trade-off**: Yeni supplier/service/space eklendiğinde 60 saniye stale
data; catalog mutation endpoint'lerine `cache.delete_pattern` invalidation
eklenmesi Sprint 32 işi.

### Sprint 29-31 Toplam Performans Kazanımı

12 yavaş endpoint düzeltildi, ortalama yanıt süresi:
- Önce: 5.8s ortalama (en kötü 10.94s)
- Sonra: 0.6s ortalama (en kötü 2.0s)
- **~10× toplam hızlanma**

Pattern özeti:
1. **N+1 → asyncio.gather**: regulatory inspection, displacement market,
   guest-alerts, rms rate-rec, dashboard forecast, ops overview, ai briefing,
   onboarding progress (8 endpoint).
2. **Hoist out of loop + bounded gather** (Semaphore 25 + chunked $in 500):
   guest-alerts (büyük tenant safety).
3. **TTL cache** (60s, tenant+query bazlı): proc/spa/mice catalog (3 endpoint).

### Sprint 31 — Architect FAIL → düzeltme (mutation invalidation)

İlk round architect FAIL: (1) PII cache'leniyor, (2) mutation invalidation yok.

**Düzeltme**:
- TTL 60s → 30s (PII window kısaltıldı)
- 9 mutation endpoint'ine `_invalidate_*_cache(tenant_id)` hook'u
  (cache.delete_pattern ile tenant-scoped wipe)
- procurement: create/update/delete supplier
- spa: create/update/delete service
- mice: create/update/delete space

**E2E doğrulama**:
- Cold 3.62s → warm 0.25s (**15×**)
- POST sonrası: yeni item GET'te **anında** görünür (0s stale)
- DELETE sonrası: silinen item **anında** kaybolur

---

## Sprint 32 — Cache Hardening (19 Apr 2026)

Architect-flagged Sprint 31 backlog'u kapatıldı:

1. **`cache.safe_invalidate(tenant_id, entity_prefix)`** merkezi helper:
   - Tenant-id charset whitelist: `[A-Za-z0-9._-]`, max 128 char.
   - Glob metakarakterleri (`*?[]\\:`) reddedilir → cross-tenant wipe önlendi.
   - Entity prefix de aynı şekilde validate.
   - `invalidation_failures` / `invalidation_success` counter dict'leri
     /metrics dashboard için.
   - Başarısızlıkta `logger.warning` (önceki silent `pass` kaldırıldı).

2. **Router'lar yeni API'ye geçti**: `procurement._invalidate_suppliers_cache`,
   `spa._invalidate_spa_services_cache`, `mice._invalidate_mice_spaces_cache`
   artık tek satırlık `_cache.safe_invalidate(...)` çağırıyor.

3. **Integration test suite** (`backend/tests/integration/
   test_catalog_cache_invalidation.py`, **10 test PASS**):
   - Tenant-id validation (UUID, alphanumeric, glob meta, empty, overlong).
   - Cached varyant invalidation: `?q=`, `?active_only=` farklı key'leri
     mutation sonrası TÜMÜ wipe edilir.
   - Cross-tenant izolasyon: A'nın invalidation'ı B'nin cache'ini etkilemez.
   - Failure path: hatada warning log + counter increment doğrulandı.

### Sprint 32 ROUND 2 — defense-in-depth

Architect 2. round'da `cache_manager.py` içindeki 5 legacy helper'ın
(invalidate_tenant_cache, DashboardCache.invalidate, RoomCache,
BookingCache, GuestCache, ReportCache) hâlâ guard'sız `delete_pattern`
çağırdığını yakaladı.

**Düzeltme — 2 katmanlı savunma**:
1. `delete_pattern` içine merkezi guard: `cache:` ile başlayan pattern'lerde
   tenant segmenti `_is_safe_tenant_id`'den geçer.
2. `invalidate_tenant_cache` içinde input validation (tenant_id ve
   entity_type için): `tenant_id` `:` içerirse split yanılır → giriş
   validasyonu defense-in-depth.
3. 3 yeni guardrail testi: `DashboardCache.invalidate` unsafe tenant'ta
   keys/delete çağırmıyor, `invalidate_tenant_cache` `a:b*c` reddediyor,
   geçerli UUID kabul ediliyor.

**Toplam test**: 15 PASS (10 subtests dahil).

### Sprint 32 ROUND 3 — follow-up'lar kapatıldı

1. **Module-level docstring** (`cache_manager.py` üst kısmı): canonical
   enforcement noktaları (3-katmanlı tercih sırası), defense-in-depth
   katmanları ve yeni router'lar için kullanım kuralı belgelendi.

2. **`invalidation_metrics()` + `health_check()` enrichment**: failure /
   success counter'ları artık `health_check()` çıktısında görünüyor;
   Prometheus metrics zaten `cache.health_check()` çağırıyor → SLO
   alarmları için hazır. Aggregation note: per-process, multi-replica'da
   metrics layer'da topla.

3. **Known-safe regression test**: 8 legitimate çağrı (Dashboard, Room
   ±id, Booking ±id, Guest ±id, Report) hardening sonrası backend'e
   ulaşıyor. Regex `cache:<tenant>(:<segment>){1..8}` — segment
   literal-veya-tek-`*` formatında, `b*c` gibi ortada-glob kombinasyonu
   reddediliyor (split-skew bypass kapalı).

**Final test sayısı**: 17 PASS, 22 subtest. Sprint 32 fully closed.
