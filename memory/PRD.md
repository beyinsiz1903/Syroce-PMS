# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform. The software development phase has been declared complete. The current directive is operational validation and real-world integration testing.

## Current Phase: Operational Validation & Integration

### What's Been Implemented

#### Phase 1: CI/CD Pipeline Fix (Completed - March 2026)
- Fixed 548+ ruff linting errors (E722 bare except, F401 unused imports)
- Resolved dependency conflicts in requirements.txt (locust/python-engineio/python-socketio)
- Added proper ruff configuration in pyproject.toml
- CI/CD pipeline now passes with 0 lint errors

#### Phase 2: HotelRunner REST API Integration (Completed - March 2026)
- **Backend Provider:** Full HotelRunner API client with rate limiting (5 req/min, 250 req/day)
  - Connection test, rooms fetch, ARI push (availability/rates/inventory)
  - Reservation pull with pagination, delivery confirmation
  - Channel listing, transaction tracking, bulk ARI operations
- **Backend Router:** 16 API endpoints under `/api/channel-manager/hotelrunner/`
  - Connection management (connect, test, disconnect)
  - Room operations (list, update, bulk update)
  - Reservation operations (fetch, sync, confirm delivery, local storage)
  - Room mappings CRUD
  - Sync logs, API usage stats
- **Frontend Dashboard:** HotelRunner Integration page at `/hotelrunner`
  - 5 tabs: Baglanti, Odalar, Rezervasyonlar, Eslemeler, Loglar
  - Connection form with Token + HR_ID inputs
  - Auto sync and delivery confirmation toggles

### Staging Soak Test (Previously Completed)
- Locust load test infrastructure with multiple user roles
- System resource monitor
- Successfully ran with 0% error rate
- Dashboard at `/soak-test`

## Architecture
```
PMS Core
   |
   ├── ReservationService
   ├── InventoryService  
   ├── PricingService
   |
   ▼
Channel Manager Layer
   |
   ├── Provider Interface
   │      ├── HotelRunnerProvider  ← NEW (March 2026)
   │      ├── BookingProvider
   │      └── ExpediaProvider
   |
   ▼
Worker Queue
   |
   ├── ARI Push
   ├── Reservation Sync
   └── Drift Reconciliation
```

## Key Files
- `/app/backend/domains/channel_manager/providers/hotelrunner.py` - Core API client
- `/app/backend/domains/channel_manager/providers/hotelrunner_router.py` - REST endpoints
- `/app/frontend/src/pages/HotelRunnerIntegration.jsx` - Dashboard
- `/app/backend/pyproject.toml` - Ruff configuration

## Prioritized Backlog

### P0 - Blocked on User
- **HotelRunner Sandbox Credentials:** User obtaining TOKEN + HR_ID from HotelRunner partner portal
- Once credentials arrive: real connection test, room sync, reservation pull

### P0 - Next
- HotelRunner Sandbox Real Test (with credentials)
- Room/Rate mapping between PMS and HotelRunner

### P1
- Pilot Hotel Onboarding
- Canary Rollout Plan execution
- Weekly Incident Drills

### P2
- Webhook endpoint for real-time reservation push from HotelRunner
- Scheduled reservation pull job (cron)
- ARI drift reconciliation with HotelRunner

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |
