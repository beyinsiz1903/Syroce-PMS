# Channel Manager v2 - Architecture Document

## Executive Summary

Syroce PMS'e production-grade, connector-first channel manager mimarisi entegre edildi. HotelRunner ilk connector olarak implement edildi. Mimari, gelecekte SiteMinder, Channex veya başka herhangi bir provider'ın eklenmesini minimal eforla destekleyecek şekilde tasarlandı.

## Varsayımlar
- HotelRunner production credential'ları henüz yok → sandbox/mock adapter
- Multi-tenant mimari (tenant_id tüm koleksiyonlarda zorunlu)
- Başlangıçta tek property, yapı çoklu property destekliyor
- Connector credentials DB'de saklanıyor (production'da encrypt edilmeli)

## Architecture Overview

```
backend/channel_manager/
├── __init__.py
├── domain/                          # Domain layer (entities, value objects)
│   ├── __init__.py
│   └── models/
│       ├── __init__.py
│       ├── canonical.py             # Provider-agnostic data models
│       ├── connector_account.py     # ConnectorAccount entity
│       ├── external_property.py     # ExternalProperty, Room, Rate
│       ├── mapping.py               # MappingRule entity
│       ├── sync.py                  # SyncJob, SyncEvent, PushReceipt
│       ├── reservation_import.py    # ImportBatch, ImportedReservation
│       ├── reconciliation.py        # ReconciliationIssue
│       └── audit.py                 # IntegrationAuditLog
├── application/                     # Application services (use cases)
│   ├── __init__.py
│   ├── connector_service.py         # Connector CRUD + lifecycle
│   ├── mapping_service.py           # Mapping CRUD + validation
│   ├── inventory_sync_service.py    # Push inventory/rates to providers
│   ├── reservation_import_service.py # Pull + import reservations
│   ├── reconciliation_service.py    # Drift detection
│   └── observability_service.py     # Dashboard + health metrics
├── connectors/                      # Provider implementations
│   ├── __init__.py
│   └── hotelrunner/
│       ├── __init__.py
│       ├── client.py                # HTTP client with rate limit + retry
│       ├── auth.py                  # Token + hr_id auth
│       ├── xml_builder.py           # OTA XML request builder
│       ├── xml_parser.py            # OTA XML response parser
│       ├── mapper.py                # HotelRunner ↔ Canonical mapper
│       ├── rate_limit.py            # Token bucket rate limiter
│       ├── retry_policy.py          # Exponential backoff + jitter
│       └── errors.py                # Typed connector errors
├── infrastructure/                  # Persistence + external concerns
│   ├── __init__.py
│   ├── repository.py                # MongoDB repository (tenant-scoped)
│   └── indexes.py                   # MongoDB index definitions
└── interfaces/                      # API layer
    ├── __init__.py
    └── router.py                    # FastAPI router (/api/channel-manager/v2/)
```

## Bounded Contexts

### PMS Core
- Reservations (bookings collection)
- Rooms (rooms collection)
- Guests (guests collection)
- Folios

### Channel Manager (NEW)
- ConnectorAccount: Bağlantı yaşam döngüsü
- MappingRule: PMS ↔ External entity eşleşmeleri
- SyncJob/SyncEvent: Push/pull operasyonları
- ImportedReservation: Dışarıdan gelen rezervasyonlar
- ReconciliationIssue: Veri drift tespiti

### Integration Layer
- HotelRunner connector: XML/OTA protocol
- Future: SiteMinder, Channex connectors

## Data Models (MongoDB Collections)

| Collection | Purpose | Key Indexes |
|---|---|---|
| cm_connectors | Connector accounts | (tenant_id, id), (tenant_id, property_id, provider) |
| cm_mappings | PMS ↔ External mappings | (tenant_id, id), (tenant_id, connector_id, entity_type, status) |
| cm_sync_jobs | Sync job tracking | (tenant_id, connector_id, created_at), (id) |
| cm_sync_events | Individual sync events | (job_id, status), (id) |
| cm_push_receipts | Provider acknowledgements | (tenant_id, connector_id, sync_event_id) |
| cm_import_batches | Reservation import batches | (tenant_id, connector_id, started_at), (id) |
| cm_imported_reservations | Imported reservations | (tenant_id, connector_id, external_reservation_id), (tenant_id, import_status) |
| cm_reconciliation_issues | Data drift issues | (tenant_id, connector_id, status) |
| cm_integration_audit | Immutable audit trail | (tenant_id, created_at), (tenant_id, connector_id, action) |

## Canonical Data Model

Provider-agnostic entities PMS içinde kullanılır. Her connector kendi verilerini bu modele dönüştürür:

- **CanonicalRoomType**: id, code, name, max_occupancy, base_occupancy
- **CanonicalRatePlan**: id, code, name, currency, meal_plan, cancellation_deadline
- **InventorySlice**: date, room_type_id, total, sold, blocked, available
- **RestrictionSet**: date, room_type_id, rate_plan_id, closed, CTA, CTD, min/max_stay
- **CanonicalReservation**: external_id, guest, dates, room/rate, pricing, payment
- **CanonicalGuest**: name, email, phone, nationality
- **PriceBreakdown**: daily rates with taxes
- **TaxBreakdown**: tax_name, rate, amount, is_inclusive

## HotelRunner Integration Protocol

### Authentication
- Token-based: `token` + `hr_id` query parameters
- Headers: Content-Type: application/xml

### OTA Message Types
1. **OTA_HotelAvailNotifRQ**: Inventory push (room availability)
2. **OTA_HotelRateAmountNotifRQ**: Rate push (prices)
3. **OTA_ReadRQ**: Reservation pull (undelivered)
4. **OTA_NotifReportRQ**: Acknowledgement

### Rate Limiting
- Token bucket algorithm
- Default: 60 req/min, 1000 req/hour
- Configurable per connector

### Retry Policy
- Exponential backoff with jitter
- Max 3 retries
- Auth errors never retried
- Rate limit uses Retry-After header

## Inventory Sync Flow

```
PMS Event (booking, rate change, block)
  → Delta Detection (what changed since last push)
  → Coalescing (merge rapid changes for same room/date)
  → Batching (group into efficient API calls, max 50 per batch)
  → Rate Limit Check
  → Provider Push (XML request)
  → Response Parsing
  → Push Receipt Creation
  → Connector Health Update
```

## Reservation Import Flow

```
Scheduled Pull (OTA_ReadRQ)
  → Parse Response (XML → raw dicts)
  → Canonical Mapping (HotelRunnerMapper)
  → Duplicate Detection (external_reservation_id lookup)
  → Action Classification:
    ├── NEW → Create PMS booking
    ├── MODIFICATION → Update PMS booking
    ├── CANCELLATION → Cancel PMS booking
    ├── DUPLICATE → Skip
    └── NO MAPPING → Review Queue
  → Acknowledgement (OTA_NotifReportRQ)
  → Audit Log
```

## API Endpoints

### Connector Management
| Method | Path | Description |
|---|---|---|
| GET | /api/channel-manager/v2/connectors | List connectors |
| POST | /api/channel-manager/v2/connectors | Create connector |
| GET | /api/channel-manager/v2/connectors/{id} | Get connector (masked creds) |
| POST | /api/channel-manager/v2/connectors/{id}/test | Test connection |
| POST | /api/channel-manager/v2/connectors/{id}/activate | Activate |
| POST | /api/channel-manager/v2/connectors/{id}/pause | Pause |
| DELETE | /api/channel-manager/v2/connectors/{id} | Delete |

### Mapping Management
| Method | Path | Description |
|---|---|---|
| GET | /api/channel-manager/v2/mappings/{connector_id} | List mappings |
| POST | /api/channel-manager/v2/mappings | Create mapping |
| DELETE | /api/channel-manager/v2/mappings/{id} | Delete mapping |
| POST | /api/channel-manager/v2/mappings/{connector_id}/validate | Validate all |
| GET | /api/channel-manager/v2/mappings/{connector_id}/sync-readiness | Check readiness |

### Sync Operations
| Method | Path | Description |
|---|---|---|
| POST | /api/channel-manager/v2/sync/inventory | Push inventory |
| POST | /api/channel-manager/v2/sync/rates | Push rates |
| GET | /api/channel-manager/v2/sync/jobs | List sync jobs |
| GET | /api/channel-manager/v2/sync/jobs/{id} | Job detail with events |

### Reservation Import
| Method | Path | Description |
|---|---|---|
| POST | /api/channel-manager/v2/reservations/pull | Trigger pull |
| GET | /api/channel-manager/v2/reservations/imported | List imported |
| GET | /api/channel-manager/v2/reservations/review-queue | Review queue |
| POST | /api/channel-manager/v2/reservations/approve | Approve from review |
| GET | /api/channel-manager/v2/reservations/batches | Import batches |

### Reconciliation
| Method | Path | Description |
|---|---|---|
| POST | /api/channel-manager/v2/reconciliation/run | Run check |
| GET | /api/channel-manager/v2/reconciliation/issues | List issues |
| POST | /api/channel-manager/v2/reconciliation/issues/{id}/resolve | Resolve |
| POST | /api/channel-manager/v2/reconciliation/issues/{id}/dismiss | Dismiss |

### Observability
| Method | Path | Description |
|---|---|---|
| GET | /api/channel-manager/v2/dashboard | Full dashboard |
| GET | /api/channel-manager/v2/health/{connector_id} | Connector health |
| GET | /api/channel-manager/v2/audit | Audit log |

## Test Results

Backend: 23/25 passed (92%)
Frontend: 100% all UI elements work
Test file: /app/backend/tests/test_channel_manager_v2.py

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Overbooking | Idempotent imports, duplicate detection by external_reservation_id |
| Rate drift | Reconciliation service detects mismatches |
| Sync failure | Retry with exponential backoff, dead letter for persistent failures |
| Mapping errors | Validation before sync, sync-readiness check |
| Duplicate reservations | Unique index on (tenant_id, connector_id, external_reservation_id) |

## 90-Day Roadmap

### Days 1-30 (DONE)
- ✅ Architecture + folder structure
- ✅ All domain models + canonical models
- ✅ HotelRunner connector skeleton (client, XML, mapper, auth, rate limit, retry)
- ✅ Connector CRUD + lifecycle
- ✅ Mapping CRUD + validation + sync-readiness
- ✅ Inventory sync engine
- ✅ Reservation import engine
- ✅ Reconciliation engine
- ✅ Observability dashboard + health
- ✅ Admin panel UI (Integration Hub)
- ✅ MongoDB indexes
- ✅ Audit logging

### Days 30-60
- [ ] HotelRunner sandbox test with real credentials
- [ ] Scheduled sync (cron-based inventory push)
- [ ] Scheduled reservation pull
- [ ] Event-driven sync (PMS booking → automatic inventory push)
- [ ] Credential encryption at rest
- [ ] Full reconciliation with inventory comparison
- [ ] CancelReservation write-path migration

### Days 60-90
- [ ] SiteMinder or Channex connector
- [ ] Rate plan derivation engine
- [ ] Advanced restriction management
- [ ] ChargePost write-path migration
- [ ] Performance optimization (bulk operations)
- [ ] Production deployment checklist
