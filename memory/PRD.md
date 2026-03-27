# PMS (Property Management System) - PRD

## Original Problem Statement
Hotel Property Management System - full-stack application with React frontend and FastAPI backend with MongoDB. Multi-tenant PMS with booking management, room management, guest profiles, channel manager integration, enterprise features.

## User Personas
- Hotel managers and staff who manage bookings, rooms, guests, and operations.

## Project Priorities (User-Defined)

### P0 - Go-Live Hardening COMPLETED
- Vite production build optimized
- Nginx hardened
- Go-Live Runbook, SLO/SLA, Incident Playbook created

### P1 - Critical Fixes & Improvements COMPLETED
- `room-move-history` endpoint bug fix — schema normalized to canonical fields
- Load test suite expanded — multi-tenant, failure injection, retry storm, queue backlog, reconciliation
- Import boundary violations resolved — 3/3 exceptions eliminated
- CI orphan file guard fix — `create_test_user.py` moved to `scripts/`

### P2 - Code Quality & Hardening COMPLETED
- [x] CI Load Test Integration — 11 curated load tests as CI hard gate
- [x] Ruff UP Rules (safe wave) — UP006, UP012, UP015, UP017, UP024, UP034, UP041, UP045
- [ ] Ruff UP Rules (wave 2) — UP035 (deprecated imports), UP042 (StrEnum)
- [ ] App.jsx decomposition

### P3 - Security & Compliance
- [x] AWS KMS envelope encryption provider
- [x] Secret classification system (7 types with lifecycle rules)
- [x] PII Registry (31 fields, 4 categories, role-based masking)
- [x] PII masking for logs (SanitizedLogFilter on root logger)
- [x] PII masking for ops/timeline/raw-payload endpoints
- [x] PII access audit trail (MongoDB-backed, 180-day TTL)
- [x] PII anomaly detection
- [x] Secret inventory and classification API
- [x] Secret Rotation + Rollback Flow (COMPLETED 2026-03-25)
- [x] Rotation Ops Panel Frontend (COMPLETED 2026-03-25)
- [x] At-Rest PII Field Encryption — Faz 1 & 2 (COMPLETED 2026-03-25)
- [ ] P2 Faz 3: Plaintext cleanup + mandatory encrypted-only mode (PARKED)

### P4 - HotelRunner Provider Parity (ACTIVE — P0 Priority)
- [x] **Faz 1: Auth + Credential Güvenliği (COMPLETED 2026-03-25)**
  - HotelRunner Mock Server (localhost:9999, supervisor-managed)
  - Environment-aware provider: mock / sandbox / production URL resolution
  - Credential rotation integration with existing KMS infrastructure
  - Multi-step connection test: auth → channels → rooms → rates → reservations
  - Testing: iteration_162 — 15/15 pass (100%)
- [x] **Faz 2: Mock + Read/Write Path E2E (COMPLETED 2026-03-25)**
  - Mock server: realistic responses for channels, rooms, reservations, ARI push
  - Chaos engineering: 429 rate limit, 500 errors, timeout, malformed payload simulation
  - Normalizer fix: handles real HR API format (checkin_date, firstname, address.email, rooms[].room_code, state)
  - Read path: fetch_rooms, fetch_channels, fetch_reservations, paginated fetch — all verified
  - Write path: ARI push (availability, rates, stop_sale, min/max stay, CTA/CTD) — all verified
  - Ingest pipeline E2E: new → duplicate → modify → cancel lifecycle verified
  - Duplicate delivery detection via provider_event_id + payload hash
  - Parser fix: handles string guest field (was failing on `.get()`)
  - Parity test suite: 27/27 pass (/app/backend/tests/test_hr_parity.py)
- [ ] **Faz 3: Reconciliation / Snapshot doğrulama (UPCOMING)**
  - Snapshot collector updated with environment support
  - Cross-provider comparison engine already exists
  - Need: E2E reconciliation test with mock server data vs lineage
- [ ] **Faz 4: Write Path — DRY-RUN controlled exit (UPCOMING)**
  - ARI adapter currently in DRY-RUN
  - Controlled exit: read only → limited write → full ARI
  - CTA/CTD and min/max stay must be verified at provider level
- [ ] **Faz 5: Ops Dashboard — Provider Health Panel (UPCOMING)**
  - Frontend: provider health (HR + Exely side by side)
  - Sync status, error rates, last operations
  - Deferred room assignment visibility

### P5 - Production Deployment (COMPLETED 2026-03-27)
- [x] Production deployment paketi hazirlandi
  - docker-compose.production.yml (6 servis: mongo, redis, backend, worker, beat, nginx)
  - Nginx reverse proxy (api.syroce.com, SSL/Let's Encrypt, rate limiting, security headers)
  - deploy.sh (tek komutla kurulum: Docker, build, deploy, dogrulama)
  - ssl-setup.sh (Let's Encrypt + otomatik yenileme cron)
  - .env.production.example (template)
  - DEPLOYMENT_GUIDE.md (Turkce adim adim rehber)
- [x] Guvenlik: MongoDB/Redis sadece internal network, backend port disari acik degil
- [x] HotelRunner endpoint'leri Nginx'te tanimli (callback GET + webhook POST)

### Backlog
- App.jsx decomposition (after security tasks)
- Legacy migration / cleanup jobs
- Motor -> pymongo async migration
- HMR guard decommission
- Configure Slack webhook for production alerts
- P2 Faz 2: Migration for users/bookings collections
- API response role-based masking

## Architecture
- Frontend: React + Vite + Shadcn UI
- Backend: FastAPI + Motor (async MongoDB)
- Database: MongoDB (hotel_pms)
- CI/CD: GitHub Actions
- Mock Server: HotelRunner Mock API (port 9999, supervisor-managed)

## Key Files
- Backend entry: `/app/backend/server.py`
- Frontend entry: `/app/frontend/src/App.jsx`
- **HotelRunner Provider:**
  - Provider facade: `/app/backend/domains/channel_manager/providers/hotelrunner/provider.py`
  - HTTP client: `/app/backend/domains/channel_manager/providers/hotelrunner/client.py`
  - Mock server: `/app/backend/domains/channel_manager/providers/hotelrunner/mock_server.py`
  - Parser: `/app/backend/domains/channel_manager/providers/hotelrunner/parser.py`
  - Router: `/app/backend/domains/channel_manager/providers/hotelrunner_router.py`
  - Webhook: `/app/backend/domains/channel_manager/providers/hotelrunner_webhook.py`
  - Ingest: `/app/backend/domains/channel_manager/providers/hotelrunner_ingest.py`
  - Normalizer: `/app/backend/domains/channel_manager/ingest/normalizer.py`
  - Pipeline: `/app/backend/domains/channel_manager/ingest/pipeline.py`
  - ARI adapter: `/app/backend/domains/channel_manager/ari/adapters/hotelrunner_ari_adapter.py`
  - Snapshot collector: `/app/backend/domains/channel_manager/reconciliation_engine/snapshot_collectors.py`
  - Comparison engine: `/app/backend/domains/channel_manager/reconciliation_engine/comparison_engine.py`
- **Security:** (unchanged from before)
  - Rotation Engine: `/app/backend/security/rotation_engine.py`
  - Field Encryption: `/app/backend/security/field_encryption.py`
- **Tests:**
  - Parity test: `/app/backend/tests/test_hr_parity.py`
  - Test report: `/app/test_reports/iteration_162.json`

## DB Collections (Channel Manager)
- `raw_channel_events` — Raw webhook/pull events from all providers
- `reservation_lineage` — Canonical reservation state (versioned, with mutation tracking)
- `room_mappings` — Provider room code → PMS room type mapping
- `rate_plan_mappings` — Provider rate code → PMS rate plan mapping
- `webhook_raw_payloads` — Raw JSON payloads for debugging
- `hotelrunner_connections` — Provider connection config per tenant

## Test Credentials
- Email: demo@hotel.com / Password: demo123
- Mock HR token: mock-hr-token-001 / HR ID: HR-HOTEL-001

## Key Decisions
- **HotelRunner provider uses environment-aware URL resolution (mock/sandbox/production)**
- **Mock server supports chaos engineering: 429, 500, timeout, malformed payload injection**
- **Normalizer handles both real HR API format and simplified format (backward compat)**
- **Ingest pipeline: 9-stage processing with idempotency, dedup, stale detection, mapping resolution**
- **Deferred room assignment: reservations stay in pending_mapping until room is explicitly mapped**
- **Credential rotation for HotelRunner uses existing KMS + versioning infrastructure**
- **DRY-RUN exit will be controlled: read only → limited write → full ARI**
