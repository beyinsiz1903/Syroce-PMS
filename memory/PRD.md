# Syroce PMS - Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS with unified channel manager, role-based access, dedicated Regional Agency Portal, and an Auto Room Mapping Wizard for new channel connections. The system integrates with HotelRunner v2 API and Exely SOAP API for channel distribution.

## User Personas
- **Hotel Admin** (super_admin): Full system access, manages rooms, bookings, channel connections
- **Front Desk Staff**: Day-to-day operations, check-in/check-out, reservations
- **Regional Agency**: Portal access for booking creation and management

## Core Architecture
- **Frontend**: React + Vite + Shadcn UI
- **Backend**: FastAPI + MongoDB
- **Channel Manager**: Modular connector architecture (HotelRunner v2, Exely)
- **Auth**: JWT-based authentication with role-based access

## What's Been Implemented

### PMS Core
- Room management (6 types: Standard, Deluxe, Superior, Suite, Junior Suite, Family)
- Booking/reservation management
- Guest management
- Dashboard with KPI analytics
- Night audit system

### Channel Manager
- Unified connector architecture (`/channel_manager/connectors/`)
- HotelRunner v2 integration (inventory sync, reservation import, rate management)
- Exely SOAP integration (availability, rates, reservations)
- Auto Room Mapping Wizard with fuzzy matching
- Entity mapping system (cm_mappings, cm_entity_mappings)

### Agency Portal
- Dedicated login/registration for agencies
- Reservation creation and management

### Security
- AES-256-GCM credential encryption
- JWT authentication
- Role-based access control

## Completed Tasks (Latest Session - 2026-04-07)
- **DB Cleanup**: Removed 30+ duplicate connectors, test mappings, mock external room types/rate plans
- **Fetch-External Mechanism**: New POST endpoint to fetch real room types from HotelRunner API
- **Wizard Update**: Auto-fetches channel data when clicking "İleri", shows clear error/success messages
- **Lint Fixes**: Fixed 19 ruff lint errors across backend Python files
- **Legacy HR Connector Removal**: Completed in previous session (2026-04-07)

## Active Connectors
1. HotelRunner Sandbox (id: c79fd9cb-d240-4344-8b2d-7d8b71d6a681)
2. Sandbox Exely (id: sandbox-exely-sim-e1fca6dc1c5b)
3. Sandbox HotelRunner (id: sandbox-hotelrunner-sim-e1fca6dc1c5b)

## Prioritized Backlog

### P2 - Upcoming
- Real-time UI notifications for channel push results (instead of silent background processing)

### P3 - Future Enhancements
- Channel Manager Dashboard: recent reservations, failed imports, push queue status, connection health
- Admin UI Panel for encryption management (view status, trigger migrations, check audit logs)
- Make unassigned reservations more prominent in the calendar
- Improve Auto Room Mapping logic: include capacity (max occupancy) and base price in fuzzy matching

### P4 - Refactoring
- Abstract/subdivide `hotelrunner_sync.py` (~1000 lines)
- `hr_rate_manager_router.py` (>1100 lines)
- Migrate `v1_` prefixed modules inside `hotelrunner_v2/` to native v2 API

## 3rd Party Integrations
- HotelRunner v2 API (LIVE, token active)
- Exely SOAP API (requires provider credentials)
- AWS KMS (encryption, requires user API key)
- Emergent Integrations (Universal LLM Key)

## Key API Endpoints
- `POST /api/auth/login` - JWT login (returns `access_token`)
- `GET /api/channel-manager/v2/connectors` - List connectors
- `POST /api/channel-manager/v2/mapping-wizard/{id}/fetch-external` - Fetch real channel data
- `GET /api/channel-manager/v2/mapping-wizard/{id}/suggest-rooms` - Room mapping suggestions
- `GET /api/channel-manager/v2/mapping-wizard/{id}/suggest-rate-plans` - Rate plan suggestions
- `POST /api/channel-manager/v2/mapping-wizard/{id}/confirm` - Confirm mappings
