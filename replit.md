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
