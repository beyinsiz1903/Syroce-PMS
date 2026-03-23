# CHANGELOG

## [2026-03-23] CI/CD Workflow Fix — VITE_BACKEND_URL Duplicate
- **Fixed:** Removed duplicate `VITE_BACKEND_URL` env var from `backend-test` step in `ci-cd.yml`
- **Root Cause:** `VITE_BACKEND_URL` (a Vite/frontend env var) was unnecessarily defined in the backend Python test env block, causing GitHub Actions YAML validation to fail with "already defined" error
- **Impact:** CI/CD pipeline was blocked; now unblocked

## [Previous Sessions] — CI/CD Hardening & Control Plane (P0 Complete)
- Standardized CI/CD notifications with GitHub annotations and job summaries
- Added deploy trend endpoint (`/api/ops/dashboard/deploy-trend`) and Recharts visualization
- Fixed `booking_availability` import path in `analytics_router.py`
- Annotated historical `REACT_APP_BACKEND_URL` → `VITE_BACKEND_URL` migration in docs

> **Note:** Historical references to `REACT_APP_BACKEND_URL` in older entries reflect the pre-Vite era. The app now uses `VITE_BACKEND_URL` exclusively.
