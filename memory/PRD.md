# Syroce PMS — Product Requirements Document

## Problem Statement
Hotel management system with significant technical debt requiring systematic refactoring.

## Architecture Overview
- **Backend**: FastAPI + MongoDB
- **Frontend**: Vite + React
- **DB**: MongoDB (MONGO_URL from env)

## PMS Router Decomposition Map

### Completed
| Module | File | Routes | Stage |
|--------|------|--------|-------|
| Rooms & Companies | `pms_rooms.py` | 14 routes | Stage 1 |
| Guests | `pms_guests.py` | Guest CRUD | Stage 1 |
| Bookings | `pms_bookings.py` | 10 routes (CRUD, approve/reject, multi-room) | Stage 2 |
| Dashboard | `pms_dashboard.py` | 3 routes (dashboard, alerts, alternatives) | Stage 2 |
| Shared Helpers | `pms_shared.py` | `get_guest_name` (pure helper) | Stage 2 |

### Remaining in pms.py (~1384 lines, 32 routes)
| Domain | Routes | Stage |
|--------|--------|-------|
| Room Services | 2 | Stage 3 |
| Room Blocks | 4 | Stage 3 |
| Availability | 1 + helper | Stage 3 (CRITICAL) |
| Staff Tasks | 3 | Stage 3 |
| Allotment Contracts | 3 | Stage 3 |
| Group Reservations | 2 | Stage 3 |
| Setup Status | 1 | Stage 3 |
| Room Details Enhanced | 3 + 2 models | Stage 3 |
| Reservation Details | 8 + 4 models | Stage 3 |
| Room Queue | 5 | Stage 3 |

## CI/CD Status
- Pipeline hardened: `|| true` removed from critical steps
- Ruff rules: W, C4 enabled; B008 ignored for FastAPI Depends
- Node.js: 22 in CI
- Security: pygments CVE documented in SECURITY_IGNORE_REGISTRY.md

## Regression Test
- `test_pms_route_wiring.py`: 59 routes verified after each stage
- `test_pms_decomposition_stage2.py`: 22 API integration tests

## Test Credentials
- Email: `demo@hotel.com`, Password: `demo123`

## Backlog

### P0 — Next
- **Stage 3 Decomposition**: Extract reservations, availability (CRITICAL), queue, services
  - Availability extraction needs expanded test coverage BEFORE extraction
  - Risk: overbooking, inventory drift if done wrong

### P1
- Frontend Refactoring: Monolithic `App.jsx` decomposition
- Architectural Debt: 3 exceptions in `check_import_boundaries.py`
- CI/CD Ruff Wave UP: pyupgrade rules

### P2
- Load & Chaos Testing
- Pre-existing bugs: room-move-history optional param handling, _id projection missing in several reservation routes
