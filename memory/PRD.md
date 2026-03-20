# Hotel Management System - PRD

## Original Problem Statement
Achieve a stable, fully passing CI/CD pipeline for a hotel management system with channel manager integrations (HotelRunner, Exely).

## Core Requirements
- All CI tests must pass (target: 731 tests)
- Backend: FastAPI + MongoDB + Redis
- Channel manager integrations: HotelRunner, Exely
- Multi-tenant architecture with role-based access

## What's Been Implemented
- Full hotel management backend with reservations, guests, rooms, billing
- Channel manager v2 with provider config, webhooks, ARI push
- Admin tenant management
- Guest messaging system
- Production go-live validation suite
- Comprehensive test suite (731 tests)

## Changelog
- **2026-02-XX (Session 14+)**: Fixed `test_login_success` assertion (`admin` → `super_admin`)
- **2026-02-XX (Session 15)**: Fixed `test_hotelrunner_test_connection_no_creds` assertion (`200` → `400`) — API correctly returns 400 when no credentials configured

## Prioritized Backlog
### P0
- [x] Fix `test_login_success` assertion
- [x] Fix `test_hotelrunner_test_connection_no_creds` assertion
- [ ] Validate full CI pipeline passes (user must push & run)

### P1
- [ ] Refactor `@cached` decorator in `cache_manager.py` for Pydantic/Redis serialization

### P2
- [ ] Fix `reconciliation_engine` module structure (remove try/except workaround)
- [ ] Consolidate CI files (`ci.yml` + `ci-cd.yml`)
- [ ] Fix Python lint errors in `pms.py` (F821 undefined names)

### P3
- [ ] Legacy collection cleanup

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Architecture
- Backend: FastAPI (Python)
- Database: MongoDB
- Cache: Redis
- Tests: pytest (731 tests)
- CI: GitHub Actions
