# Syroce PMS - Product Requirements Document

## Original Problem Statement
Build a complete Hotel Property Management System (PMS) with Channel Manager integration for Exely. The system manages reservations, room availability, pricing, and synchronization with OTAs (Online Travel Agencies) through Exely's SOAP API.

## Core Requirements
1. **Exely Reservation Sync**: Automated reservation pulling from Exely every 60 seconds
2. **Notification System**: Bell icon notifications for new reservations
3. **Rate Manager (ARI Push)**: Full-stack feature for managing Availability, Rates, and Inventory directly from PMS, pushing changes to Exely and OTAs
4. **Channel Manager**: OTA connections, room mappings, rate management, reservation import

## What's Been Implemented
### Completed Features
- **Exely Sync (60s interval)** - Scheduler pulls reservations every 60 seconds
- **Notification System** - Backend creates notifications on new booking import, frontend bell icon displays alerts
- **Rate Manager Page** - Full-stack ARI management with grid view, edit dialog, Exely push
- **Rate Manager UI Redesign** (Mar 17, 2026) - Redesigned to match Channel Manager's light theme (white bg, standard cards, consistent typography)
- **Channel Manager** - OTA connections, room mappings, rate & availability, reservations, exceptions

### Architecture
```
/app
├── backend/
│   ├── main.py
│   ├── domains/
│   │   ├── channel_manager/
│   │   │   └── services/auto_import_service.py
│   │   └── pms/
│   │       ├── notifications_router.py
│   │       └── rate_manager_router.py
│   └── services/scheduler_service.py
└── frontend/
    └── src/
        ├── App.jsx
        ├── components/Layout.js
        └── pages/RateManager.jsx
```

## Prioritized Backlog
### P1 - Mapping UI Improvement
Enhance the UI for mapping PMS rooms/rates to provider rooms/rates.

### P2 - Legacy Collection Cleanup
Archive or delete old, unused database collections.

### P3 - Deprecation Cleanup
Remove deprecated provider files (hotelrunner.py, client.py, exely_client_legacy.py).

### P4 - Stress Testing
Conduct 24h soak test, reservation burst test, and ARI storm test.

## Key API Endpoints
- `POST /api/pms/rate-manager/update-ari` - Push ARI updates to Exely
- `GET /api/pms/rate-manager/rooms-and-rates` - Fetch Rate Manager grid data
- `GET /api/pms/notifications` - Fetch unread notifications
- `POST /api/pms/notifications/mark-as-read` - Mark notifications as read
- `GET /api/channel-manager/exely/pull-reservations` - Manual sync trigger

## 3rd Party Integrations
- **Exely (SOAP API)**: Production-ready for reservation pull and ARI push
- **HotelRunner (REST API)**: Implemented
- **Slack**: Integrated

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
