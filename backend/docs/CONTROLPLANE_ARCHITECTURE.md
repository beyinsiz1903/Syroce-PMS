# Control Plane Architecture

## Overview

The Control Plane is a **system behavior layer** (NOT a dashboard feature) that provides:

1. **Full system visibility** — every failure, every operation, every access is tracked
2. **Failure detection and classification** — strict 5-type taxonomy with severity levels
3. **Retry / replay capabilities** — idempotent, duplicate-safe, with dry-run mode
4. **Secret access control + audit** — policy enforcement, tenant isolation, anomaly detection
5. **Operational safety** — alerting, runbooks, startup validation

## Module Structure

```
backend/controlplane/
├── __init__.py              # Module exports
├── failure_model.py         # Taxonomy enums, classification, event schema
├── failure_tracker.py       # Central failure recording service
├── retry_engine.py          # Idempotent retry/replay engine
├── ops_router.py            # All /api/ops/* endpoints
├── secret_audit.py          # Enhanced secret access control + audit
├── alerting.py              # Threshold-based alerts (log + webhook)
├── runbooks.py              # 14 structured operational runbooks
├── indexes.py               # MongoDB index definitions
└── startup_validator.py     # Startup health checks
```

## Failure Model

### Taxonomy (5 Types)
| Type | Description | Default Severity |
|------|-------------|-----------------|
| `RETRYABLE` | Transient error, safe to retry | WARNING |
| `PERMANENT` | Cannot be fixed by retry | HIGH |
| `PROVIDER_ERROR` | OTA provider issue | HIGH |
| `DATA_ERROR` | Invalid/missing data | WARNING |
| `SECURITY_ERROR` | Crypto, auth, or access issue | CRITICAL |

### Severity Levels
| Level | Description |
|-------|-------------|
| `info` | Informational, no action required |
| `warning` | Should be monitored |
| `high` | Requires attention soon |
| `critical` | Immediate action required |

### Failure Event Schema
```json
{
  "id": "uuid",
  "tenant_id": "string",
  "provider": "string",
  "property_id": "string",
  "operation_type": "reservation_import | ari_push | outbox_dispatch | ...",
  "failure_type": "retryable | permanent | provider_error | data_error | security_error",
  "severity": "info | warning | high | critical",
  "error_code": "string",
  "error_message": "sanitized string (max 1000 chars)",
  "context": { "safe metadata only — no secrets" },
  "retry_count": 0,
  "first_seen_at": "ISO8601",
  "last_seen_at": "ISO8601",
  "status": "open | resolved | ignored | retrying",
  "correlation_id": "uuid"
}
```

### Auto-Classification
Errors are automatically classified by keyword matching:
- **Security** (highest priority): decrypt, encrypt, credential, secret, unauthorized, denied
- **Provider**: exely, hotelrunner, provider, 401, 403, 502
- **Data**: mapping error, validation, business rule, not found
- **Retryable**: timeout, network, rate limit, 429, 503

## API Endpoints

### System Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/overview` | Single pane of glass: failures, outbox, imports, sync, secrets |

### Failure Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/failures` | List with filters (tenant, provider, type, severity, status) |
| GET | `/api/ops/failures/{id}` | Get single failure |
| POST | `/api/ops/failures/{id}/retry` | Idempotent retry with dry-run support |
| POST | `/api/ops/failures/{id}/resolve` | Mark resolved |
| POST | `/api/ops/failures/{id}/ignore` | Mark ignored |

### Monitors
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/outbox` | Outbox: pending, stuck (>30min), failed events |
| GET | `/api/ops/imports` | Import pipeline: pending, failed, review |
| GET | `/api/ops/sync` | Sync jobs: success rate, latency |

### Secret Access Audit
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/secrets/audit` | Audit trail with filters |
| GET | `/api/ops/secrets/anomalies` | Failures/denials in time window |

### Alerting
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/alerts` | Recent alerts |
| POST | `/api/ops/alerts/check` | Manually trigger alert checks |

### Runbooks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ops/runbooks` | All runbooks (filterable by category) |
| GET | `/api/ops/runbooks/{id}` | Single runbook with resolution steps |

## Retry/Replay Design

### Guarantees
1. **Reservation imports**: checked against existing bookings — no duplicates
2. **ARI push**: pushes current state, not deltas — safe to repeat
3. **Outbox events**: reset to pending, worker picks up — idempotent claim pattern
4. **Dry-run mode**: validate without executing — operator safety

### Flow
```
POST /api/ops/failures/{id}/retry
  │
  ├─ dry_run=true → validate and return preview
  │
  └─ dry_run=false
       ├─ Check retryable (not permanent, status is open)
       ├─ Mark as "retrying"
       ├─ Log retry attempt
       ├─ Dispatch to handler (import/outbox/ARI/sync)
       │   ├─ Success → Mark resolved
       │   └─ Failure → Reopen with new error
       └─ Return result
```

## Secret Access Control

### Policy Model
- Service-level ACL: `channel_manager`, `import_bridge`, `ari_push` can access their providers
- `system` and `operator` have wildcard access
- Unknown callers are denied by default

### Tenant Isolation
- Cross-tenant access is **ALWAYS denied** at query level
- Not just policy — the check compares request tenant to target tenant
- Violations are logged as CRITICAL and emit a security failure event

## Alerting Design

### Channels
1. **Log-based** (always active) — structured log with severity level
2. **HTTP Webhook** (optional) — Slack-compatible JSON payload
   - Set `ALERT_WEBHOOK_URL` env var to enable
   - Payload uses Slack Block Kit format

### Triggers
| Trigger | Threshold | Severity |
|---------|-----------|----------|
| Import failure spike | 5 in 30min | HIGH |
| Outbox stuck | 10 events > 30min | HIGH |
| Sync failure spike | 3 in 60min | HIGH |
| Secret access anomaly | 3 in 60min | CRITICAL |
| Provider auth failure | 2 in 15min | CRITICAL |
| High error rate | 20 in 60min | CRITICAL |
| Crypto failure | 1 in 60min | CRITICAL |

### Cooldown
- 15-minute dedup window per trigger type
- Prevents alert storms

## Startup Validation

At application startup, the control plane validates:
1. **Crypto keys** — loaded and functional
2. **Secrets manager** — operational and indexed
3. **MongoDB indexes** — created for all control plane collections
4. **Environment variables** — required crypto config present

Fails loudly in `production`/`staging` mode.

## MongoDB Collections

| Collection | Purpose | Key Indexes |
|------------|---------|-------------|
| `cp_failures` | Failure events | tenant+status, severity, provider+type, operation, correlation |
| `cp_sync_jobs` | Sync job tracking | tenant+status, provider+type |
| `cp_alerts` | Alert history | fired_at (desc) |
| `cp_retry_log` | Retry attempt log | failure_id |
| `secret_access_audit` | Secret access log | tenant+provider+time, result+time |

## Test Coverage

38 unit tests covering:
- Failure classification (14 scenarios)
- Severity resolution (4 tests)
- Event building + sanitization (5 tests, including no-plaintext-leak)
- Secret access policy (5 tests)
- Runbook completeness (5 tests, all 14 runbooks verified)
- Operation type enum (1 test)
- Alert thresholds (2 tests)
- Status lifecycle (2 tests)
