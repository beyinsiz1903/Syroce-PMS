# Architecture Decision Records (ADR)

## ADR-001: Domain-Driven Design with Service/Repository Layering
- **Status**: Accepted
- **Date**: 2026-02-24
- **Context**: Enterprise PMS requires clear boundaries between domain logic, data access, and API layers.
- **Decision**: Adopt DDD pattern: Router -> Service -> Repository with OperationContext, ServiceResult, DomainError contracts.
- **Consequences**: Consistent error handling, audit hooks, testability. Slightly more boilerplate per operation.

## ADR-002: MongoDB as Primary Datastore
- **Status**: Accepted
- **Date**: 2026-02-24
- **Context**: Hotel PMS with multi-tenant, flexible schemas, and operational data.
- **Decision**: MongoDB (Motor async driver) for all primary storage. Tenant-scoped queries enforced at service layer.
- **Consequences**: Flexible schema evolution, horizontal scaling. Need careful tenant_id enforcement.

## ADR-003: JWT-Based Authentication with RBAC
- **Status**: Accepted
- **Date**: 2026-02-24
- **Context**: Multi-role access: GM, Admin, Superadmin, Frontdesk, Housekeeping, etc.
- **Decision**: JWT tokens with role-based access control. Token includes tenant_id, user_id, role.
- **Consequences**: Stateless auth, role-based panel visibility. Token refresh not yet implemented.

## ADR-004: Socket.IO for Real-Time Events
- **Status**: Accepted
- **Date**: 2026-03-01
- **Context**: Dashboard needs live updates for health, alerts, and operational events.
- **Decision**: Socket.IO with room-based subscription (system-health room per tenant).
- **Consequences**: Real-time updates with polling fallback. Session management needed for scale.

## ADR-005: Audit Hook Decorator Pattern
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: All mutating operations need audit trail without manual instrumentation.
- **Decision**: @audited decorator wraps service methods. Auto-captures before/after snapshots, duration, correlation_id.
- **Consequences**: Consistent audit trail. Silent failure on audit write to never break operations.

## ADR-006: Concurrency Guard via MongoDB Locks
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: Front desk operations (check-in, check-out, room move) can be triggered concurrently.
- **Decision**: MongoDB-based operation locks with TTL. Idempotent operations return success on re-entry.
- **Consequences**: Prevents double check-in/checkout. Lock TTL prevents deadlocks.

## ADR-007: Alert Rule Engine with Cooldown/Dedupe
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: Observability needs actionable alerts, not metric noise.
- **Decision**: Rule-based alert engine with severity, cooldown, blast radius, runbook hints, MTTA/MTTR tracking.
- **Consequences**: Incident-ready alerting. Route-compatible with Grafana/Alertmanager/PagerDuty.

## ADR-008: Channel Manager Provider Contract Validation
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: Multiple OTA providers with different behaviors, rate limits, error codes.
- **Decision**: Provider contract definitions with retryable/non-retryable error classification. Validation suite per provider.
- **Consequences**: Provider-aware error handling. Safe production validation before going live.

## ADR-009: Feature Toggle System for Pilot Rollout
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: Pilot hotels need safe, gradual feature enablement.
- **Decision**: Tenant-scoped feature toggles stored in MongoDB. Readiness checklist with auto/manual checks.
- **Consequences**: Safe rollout control. Can disable features without deployment.

## ADR-010: Incident Lifecycle Management
- **Status**: Accepted
- **Date**: 2026-03-12
- **Context**: First production incidents need structured response flow.
- **Decision**: Incident create -> acknowledge -> resolve lifecycle with MTTA/MTTR tracking and timeline.
- **Consequences**: Structured incident response. Recovery tools (DLQ replay, stuck worker recovery) accessible from API.

---

# Code Ownership Map

| Domain | Owner | Files |
|--------|-------|-------|
| PMS Core | pms-team | `domains/pms/` |
| Channel Manager | cm-team | `domains/channel_manager/` |
| Revenue | revenue-team | `domains/revenue/` |
| Guest | guest-team | `domains/guest/` |
| Security | security-team | `security/` |
| Infrastructure | platform-team | `infra/`, `workers/`, `bootstrap/` |
| Observability | platform-team | `modules/observability/` |
| Frontend | frontend-team | `frontend/src/` |

---

# Deprecation Policy
- APIs deprecated with `X-Deprecated: true` header and 6-month sunset window
- Deprecated fields return `_deprecated` suffix in response for 2 releases
- Breaking changes require major version bump in URL prefix

# Schema Versioning
- MongoDB documents include implicit versioning via field presence
- API request/response schemas defined in Pydantic models
- Backward-compatible additions allowed without versioning
- Breaking schema changes require new API version

# Endpoint Lifecycle
1. **Alpha**: Internal testing only (prefix: `/api/v0/`)
2. **Beta**: Pilot hotels (current: `/api/`)
3. **Stable**: Production (prefix: `/api/v1/` when stable)
4. **Deprecated**: Sunset announced, maintained for 6 months
5. **Removed**: Endpoint removed after sunset period
