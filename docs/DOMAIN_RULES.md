# Domain Dependency Rules

## Allowed Dependencies

```
Router Layer → Service Layer → Repository Layer → Database
     ↓              ↓
  common/*      common/*
```

## Domain Boundaries

| Domain | Can Depend On | Cannot Depend On |
|--------|---------------|-------------------|
| `domains/pms/` | `common/`, `core/` | `domains/revenue/`, `domains/channel_manager/` |
| `domains/channel_manager/` | `common/`, `core/` | `domains/pms/`, `domains/revenue/` |
| `domains/revenue/` | `common/`, `core/` | `domains/pms/`, `domains/channel_manager/` |
| `domains/guest/` | `common/`, `core/` | `domains/pms/` |
| `modules/observability/` | `common/`, `core/` | `domains/*` |
| `modules/incident/` | `common/`, `core/` | `domains/*` |

## Cross-Domain Communication
- Through event bus (`infra/event_bus/`) or shared contracts (`common/`)
- Direct service-to-service calls within same bounded context only
- Never import domain service from another domain directly

## Shared Packages
| Package | Purpose | Rules |
|---------|---------|-------|
| `common/context.py` | OperationContext | Immutable, passed from router to service |
| `common/result.py` | ServiceResult | All service methods return this |
| `common/errors.py` | DomainError hierarchy | Raise in service, catch in router |
| `common/audit_hook.py` | @audited decorator | Apply to all mutating service methods |
| `common/response.py` | API response envelope | Use in routers for consistent responses |
| `core/database.py` | MongoDB connection | Singleton, accessed via `from core.database import db` |
| `core/security.py` | JWT auth | `get_current_user` dependency in routers |

## Repository Boundaries
- Services own their collection access
- No direct `db.collection` access from routers
- Repository pattern for complex query logic (optional, service can access db directly for simple queries)

## Naming Standards
- Audit operations: `{domain}.{action}` (e.g., `frontdesk.checkin`, `pos.create_order`)
- Event names: `{domain}:{action}:{result}` (e.g., `pms:checkin:success`)
- Alert rules: `{component}_{condition}` (e.g., `queue_lag_threshold`)
- Feature toggles: `{module}_{feature}` (e.g., `night_audit_live`)
