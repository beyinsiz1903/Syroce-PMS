# Quick ID Reader - Hotel Guest Management System

## Overview
A professional hotel reception and guest management system for automating identity document scanning and processing using AI (OpenAI GPT-4o Vision). Supports Turkish ID types, KVKK compliance, multi-property management, and more.

## Architecture

### Backend (FastAPI + Python)
- **Entry point**: `backend/server.py`
- **Port**: 8000 (localhost)
- **Database**: MongoDB (local instance via `mongod`)
- **Startup script**: `start_backend.sh` (starts MongoDB, then the FastAPI server)

### Frontend (React + CRACO + Tailwind CSS)
- **Entry point**: `frontend/src/index.js`
- **Port**: 5000 (0.0.0.0)
- **Build tool**: CRACO (Create React App Configuration Override)
- **API proxy**: Requests to `/api/*` are proxied to `http://localhost:8000`

## Workflows
- **Start application**: Runs the React frontend dev server on port 5000
- **Backend API**: Starts MongoDB and the FastAPI backend on port 8000

## Key Configuration Files
- `frontend/.env`: Frontend environment (PORT=5000, HOST=0.0.0.0, proxy to backend)
- `frontend/craco.config.js`: Webpack/dev server config (allowedHosts: "all" for Replit proxy)
- `backend/server.py`: Main API server with CORS, auth, MongoDB configuration

## Environment Variables Needed
- `OPENAI_API_KEY`: For GPT-4o Vision ID scanning (direct OpenAI SDK, no wrapper)
- `MONGO_URL`: MongoDB Atlas connection string (stored as secret, includes credentials)
- `DB_NAME`: MongoDB database name (stored as secret)
- `JWT_SECRET`: Secret for JWT token signing
- `CORS_ORIGINS`: Comma-separated allowed origins (defaults to localhost + Replit domain)

## Default Credentials
- Admin: `admin@quickid.com` / `admin123`
- Receptionist: `resepsiyon@quickid.com` / `resepsiyon123`

## Key Features
- AI-powered ID document scanning (Turkish and international)
- Streamlined scan-to-room flow: Scan → Review → Save → Assign Room (all on one page)
- Guest check-in/check-out management
- Room management with quick assignment grid
- KVKK (Turkish Data Protection Law) compliance
- Multi-property support
- Biometric face matching
- TC Kimlik validation
- Offline/kiosk mode support
- PDF report generation
- Audit trail

## UI Design Notes
- ScanPage simplified: provider selection, image quality details, MRZ info removed from default view (auto mode used by default)
- ExtractionForm: essential fields shown by default (name, ID, DOB, gender, nationality), optional fields (birth place, parents, dates, notes) collapsible under "Diğer bilgiler"
- RoomQuickAssign component: shown inline after guest save, displays available rooms as clickable grid
- Save button reads "Kaydet ve Oda Ata" to signal the combined flow

## Dependency Notes
- AI scanning uses OpenAI SDK directly (`openai` package) via `backend/llm_client.py` helper module
- The frontend has complex ajv versioning requirements - some packages need ajv@6, others ajv@8. Manually patched nested `node_modules` structure to resolve conflicts.
- MongoDB: kullanıcının kendi MongoDB Atlas cluster'ı kullanılıyor (uzak). Yerel mongod artık başlatılmıyor. `start_backend.sh` sadece backend sunucusunu başlatır.
- `DISABLE_ESLINT_PLUGIN=true` set in frontend/.env to avoid ajv version conflicts in webpack
