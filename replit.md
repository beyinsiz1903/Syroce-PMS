# Syroce PMS - Hotel Property Management System

## Project Overview

Enterprise-grade multi-tenant Hotel Property Management System (PMS) with AI-powered features for hotel operations, reservations, housekeeping, financial folios, and OTA channel management.

## Architecture

### Frontend (Primary - Running on Port 5000)
- **Framework**: React 19 + Vite 8
- **Styling**: Tailwind CSS + shadcn/ui
- **State**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **i18n**: i18next (8 languages including Turkish)
- **Package Manager**: Yarn 1.22.22

### Backend (FastAPI - Port 8001)
- **Framework**: FastAPI (Python 3.11+)
- **Database**: MongoDB 7.0+ (motor for async)
- **Cache**: Redis
- **Tasks**: Celery with Redis
- **Auth**: JWT + AES-256-GCM + RBAC

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

The frontend dev server runs on port 5000 with the "Start application" workflow.

```bash
cd frontend && yarn start
```

## Deployment

Configured as a static deployment:
- Build: `cd frontend && yarn install && yarn build`
- Public dir: `frontend/build`

## Key Features

- Front desk management and reservations
- Housekeeping module
- Financial folios
- Channel Manager (OTA sync with Exely, HotelRunner)
- Control Plane for operational monitoring
- AI-driven dynamic pricing and forecasting
- WebSocket real-time updates
- Multi-tenant architecture
- 8-language internationalization
