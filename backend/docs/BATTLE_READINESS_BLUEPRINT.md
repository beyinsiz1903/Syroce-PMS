# BATTLE-READINESS EXECUTION BLUEPRINT
## Syroce PMS — From Reliability-First to Battle-Grade Production System

> **Author**: Staff+ Distributed Systems Architect
> **Date**: 2026-02-15
> **Status**: EXECUTION READY
> **Target**: Live hotel operations in 30 days

---

## Table of Contents

1. [Unified Dashboard + Control Plane](#1-unified-dashboard--control-plane)
2. [Incident Timeline View](#2-incident-timeline-view)
3. [Security: Key Rotation + Breach Simulation](#3-security-key-rotation--breach-simulation)
4. [Infrastructure Maturity](#4-infrastructure-maturity)
5. [Architecture Consistency](#5-architecture-consistency-monolith-cleanup)
6. [PMS Core Battle-Testing](#6-pms-core-battle-testing)
7. [Folio / Payment / Invoice Hardening](#7-folio--payment--invoice-hardening)
8. [Operational Stress Testing](#8-operational-stress-testing)
9. [Real-World Exposure Strategy](#9-real-world-exposure-strategy)
10. [Learning Loop System](#10-learning-loop-system)
11. [30-Day Battle-Readiness Roadmap](#30-day-battle-readiness-roadmap)

---

# 1. UNIFIED DASHBOARD + CONTROL PLANE

## 1.1 Problem Definition

The control plane exists (`/api/ops/*`, 15 endpoints, `cp_failures` collection) but:

- **No aggregated dashboard view** — each endpoint returns raw data, no scoring
- **No tenant-scoped health** — operators cannot see per-hotel health at a glance
- **No historical trends** — only current state, no "was this worse yesterday?"
- **No real-time streaming** — polling-only, no push notifications for critical events
- **Channel manager status disconnected** — `cm_connectors` health not in control plane
- **ARI sync lag invisible** — no metric for "how stale is the OTA inventory?"
- **No reservation pipeline depth** — cannot see end-to-end pipeline bottlenecks

## 1.2 Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND DASHBOARD                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Health    │ │ Pipeline │ │ Provider │ │ Failure    │ │
│  │ Score    │ │ Depth    │ │ Status   │ │ Feed       │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘ │
│       │             │            │              │        │
│       └─────────────┴────────────┴──────────────┘        │
│                         │ poll 10s / SSE                  │
└─────────────────────────┼────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────┐
│              BACKEND: DASHBOARD SERVICE                    │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           DashboardAggregator                        │ │
│  │  - compute_system_health()                           │ │
│  │  - compute_tenant_health(tenant_id)                  │ │
│  │  - compute_connector_status()                        │ │
│  │  - compute_pipeline_depth()                          │ │
│  │  - compute_ari_sync_lag()                            │ │
│  └───────┬──────────┬──────────┬───────────┬───────────┘ │
│          │          │          │           │              │
│   ┌──────┴──┐ ┌─────┴───┐ ┌───┴────┐ ┌───┴──────┐      │
│   │cp_      │ │outbox_  │ │imported│ │cm_       │      │
│   │failures │ │events   │ │_reserv │ │connectors│      │
│   └─────────┘ └─────────┘ └────────┘ └──────────┘      │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │        DashboardSnapshotWorker (60s interval)        │ │
│  │  - stores time-series snapshots for trend queries    │ │
│  └─────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

## 1.3 Data Model

### Collection: `cp_health_snapshots`

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "snapshot_type": "tenant | system",
  "timestamp": "ISO8601",
  "health_score": 92.5,
  "health_grade": "A",
  "metrics": {
    "open_failures": 3,
    "open_failures_by_severity": {
      "critical": 0,
      "high": 1,
      "warning": 2,
      "info": 0
    },
    "failure_rate_1h": 0.02,
    "failure_rate_24h": 0.01,
    "outbox_pending": 5,
    "outbox_stuck": 0,
    "outbox_failed": 1,
    "outbox_processed_24h": 1250,
    "import_pending": 2,
    "import_failed_24h": 0,
    "import_review_required": 1,
    "import_success_rate_24h": 99.8,
    "sync_success_rate_24h": 100.0,
    "sync_avg_latency_ms": 340,
    "ari_sync_lag_minutes": 2.5,
    "secret_anomalies_24h": 0,
    "active_connectors": 2,
    "reservation_pipeline_depth": 7
  },
  "connector_status": [
    {
      "provider": "exely",
      "connector_id": "uuid",
      "status": "healthy",
      "last_successful_sync": "ISO8601",
      "last_error": null,
      "error_count_1h": 0,
      "latency_p50_ms": 200,
      "latency_p95_ms": 800,
      "latency_p99_ms": 1500,
      "queue_depth": 0
    },
    {
      "provider": "hotelrunner",
      "connector_id": "uuid",
      "status": "degraded",
      "last_successful_sync": "ISO8601",
      "last_error": "Rate limit exceeded",
      "error_count_1h": 3,
      "latency_p50_ms": 150,
      "latency_p95_ms": 600,
      "latency_p99_ms": 2000,
      "queue_depth": 12
    }
  ]
}
```

**Indexes**:
```python
# cp_health_snapshots indexes
("tenant_id", "timestamp")               # Tenant trend queries
("snapshot_type", "timestamp")            # System-wide trends
("timestamp",)                            # TTL index: expireAfterSeconds=604800 (7 days)
```

### Health Score Algorithm

```python
def compute_health_score(metrics: dict) -> float:
    """Score 0-100. Weighted by business impact."""
    score = 100.0

    # Critical failures (weight: 30)
    critical_count = metrics["open_failures_by_severity"].get("critical", 0)
    score -= critical_count * 15  # Each critical = -15 points

    # High failures (weight: 20)
    high_count = metrics["open_failures_by_severity"].get("high", 0)
    score -= high_count * 5  # Each high = -5 points

    # Outbox health (weight: 15)
    if metrics["outbox_stuck"] > 0:
        score -= min(15, metrics["outbox_stuck"] * 3)

    # Import health (weight: 15)
    import_fail_rate = 1.0 - metrics["import_success_rate_24h"] / 100
    score -= import_fail_rate * 15

    # Sync health (weight: 10)
    sync_fail_rate = 1.0 - metrics["sync_success_rate_24h"] / 100
    score -= sync_fail_rate * 10

    # ARI freshness (weight: 5)
    if metrics["ari_sync_lag_minutes"] > 15:
        score -= 5
    elif metrics["ari_sync_lag_minutes"] > 5:
        score -= 2

    # Security (weight: 5)
    if metrics["secret_anomalies_24h"] > 0:
        score -= min(5, metrics["secret_anomalies_24h"] * 2)

    return max(0.0, round(score, 1))
```

**Grade mapping**: A (90-100), B (75-89), C (60-74), D (40-59), F (0-39)

## 1.4 APIs

### New Endpoints (added to `controlplane/dashboard_router.py`)

```
GET  /api/ops/dashboard
     → Full system dashboard payload
     → Response: DashboardResponse (all metrics, connectors, pipeline, score)
     → Auth: admin, super_admin, operator

GET  /api/ops/dashboard/tenant/{tenant_id}
     → Tenant-scoped dashboard
     → Response: TenantDashboardResponse

GET  /api/ops/dashboard/trends
     → Query params: hours (default 24), tenant_id (optional), interval (5m|15m|1h)
     → Response: { timestamps: [], health_scores: [], failure_rates: [], ... }

GET  /api/ops/dashboard/connectors
     → All connector health statuses
     → Response: { connectors: [ConnectorStatus] }

GET  /api/ops/dashboard/pipeline
     → End-to-end reservation pipeline depth
     → Response: {
         stages: [
           { name: "webhook_received", count: 5, oldest_seconds: 120 },
           { name: "ingest_pending", count: 3, oldest_seconds: 60 },
           { name: "import_pending", count: 2, oldest_seconds: 30 },
           { name: "outbox_pending", count: 7, oldest_seconds: 15 }
         ],
         total_in_flight: 17,
         estimated_completion_minutes: 5
       }

SSE  /api/ops/dashboard/stream
     → Server-Sent Events for real-time alerts
     → Events: failure_created, alert_fired, connector_status_changed
     → Auth: admin, super_admin
```

### Request/Response Models

```python
class DashboardResponse(BaseModel):
    health_score: float
    health_grade: str  # A/B/C/D/F
    metrics: DashboardMetrics
    connector_status: List[ConnectorStatus]
    pipeline: PipelineDepth
    recent_failures: List[FailureSummary]  # Last 5 critical/high
    active_alerts: List[AlertSummary]
    timestamp: str

class ConnectorStatus(BaseModel):
    provider: str
    connector_id: str
    status: str  # healthy | degraded | down
    last_successful_sync: Optional[str]
    last_error: Optional[str]
    error_count_1h: int
    latency_p95_ms: int
    queue_depth: int

class PipelineDepth(BaseModel):
    stages: List[PipelineStage]
    total_in_flight: int
    estimated_completion_minutes: float

class TrendPoint(BaseModel):
    timestamp: str
    health_score: float
    failure_count: int
    outbox_depth: int
    import_backlog: int
```

## 1.5 Flow (Step-by-Step)

### Real-Time Dashboard Request Flow
```
1. Frontend polls GET /api/ops/dashboard every 10s
2. DashboardAggregator executes 8 parallel queries:
   a. cp_failures: count_by_severity (status=open)
   b. cp_failures: count recent (last 1h)
   c. outbox_events: count by status
   d. imported_reservations: count by import_status
   e. cp_sync_jobs: success rate (last 24h)
   f. cm_connectors: status + last_sync
   g. cp_alerts: active alerts
   h. cp_health_snapshots: latest snapshot (for trend context)
3. Compute health_score from aggregated metrics
4. Build response, return to frontend
5. Total target: < 500ms p95
```

### Snapshot Worker Flow (Background)
```
1. DashboardSnapshotWorker starts with app lifecycle
2. Every 60 seconds:
   a. Run DashboardAggregator.compute_system_health()
   b. For each active tenant: compute_tenant_health(tenant_id)
   c. Store all snapshots in cp_health_snapshots
   d. TTL auto-cleans snapshots older than 7 days
3. If worker crashes: frontend serves stale data, shows "data age" warning
```

### SSE Stream Flow
```
1. Client opens SSE connection to /api/ops/dashboard/stream
2. Server holds connection open
3. On failure_created event → push to all connected SSE clients
4. On alert_fired event → push with severity prefix
5. On connector_status_changed → push
6. Client reconnects on disconnect (EventSource auto-reconnect)
```

## 1.6 Failure Modes

| Failure | Impact | Detection | Recovery |
|---------|--------|-----------|----------|
| Snapshot worker dies | Trend data stale | Health check: last snapshot age > 3min | Auto-restart via supervisor; dashboard shows "stale data" badge |
| MongoDB slow/down | Dashboard returns 503 | Liveness probe fails | Serve cached last-known-good response (max 5min cache) |
| SSE connection drops | Client misses real-time events | EventSource auto-reconnect | Client reconnects + polls /dashboard for missed state |
| Aggregation query timeout | Partial dashboard data | Query timeout > 5s logged as WARNING | Return partial response with `data_completeness: "partial"` |
| High cardinality tenant query | Slow tenant dashboard | Query latency > 2s | Shard by tenant_id; add query cursor pagination |

## 1.7 Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Dashboard API p95 latency | < 500ms | > 2000ms |
| Snapshot worker interval | 60s | Missed > 2 intervals |
| Health score (system) | > 85 | < 60 for > 5 min |
| SSE connected clients | N/A | > 100 (capacity plan) |
| Aggregation query count per request | 8 | > 15 (query bloat) |

---

# 2. INCIDENT TIMELINE VIEW

## 2.1 Problem Definition

Events flow through 6+ subsystems: webhook → ingest → normalize → import → outbox → push → confirm. Today:

- **No unified timeline** — debugging requires querying 5+ collections manually
- **No correlation ID propagation** — cannot trace a reservation from OTA webhook to OTA confirmation
- **No stage tracking** — "where did this reservation get stuck?" requires log spelunking
- **No duration tracking** — cannot measure "ingest → PMS booking" latency per reservation
- **No external ID mapping** — OTA reservation ID → PMS booking ID requires manual lookup

## 2.2 Target Architecture

```
┌───────────────────────────────────────────────────────┐
│                   TIMELINE SERVICE                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │            TimelineWriter (embedded)              │   │
│  │  - append_event(correlation_id, stage, ...)      │   │
│  │  - Idempotent: (entity_id, stage, source) dedup  │   │
│  └──────────────────────┬────────────────────────────┘   │
│                         │ writes to                      │
│  ┌──────────────────────▼────────────────────────────┐   │
│  │         Collection: event_timeline                 │   │
│  └──────────────────────┬────────────────────────────┘   │
│                         │ reads from                     │
│  ┌──────────────────────▼────────────────────────────┐   │
│  │         TimelineReader                             │   │
│  │  - get_timeline(entity_type, entity_id)           │   │
│  │  - get_by_correlation(correlation_id)             │   │
│  │  - get_by_external_id(external_id)                │   │
│  │  - detect_gaps(timeline)                          │   │
│  └───────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────┘
         │                              │
   ┌─────┴──────────────────────┐  ┌───┴───────────────────┐
   │  WRITERS (embedded in each)│  │  READERS (API + UI)   │
   │  - Webhook handler         │  │  - /api/ops/timeline  │
   │  - Ingest pipeline         │  │  - Debug panel in UI  │
   │  - Import bridge           │  │  - Export to CSV      │
   │  - Outbox worker           │  │                       │
   │  - ARI push worker         │  │                       │
   │  - Provider callback       │  │                       │
   └────────────────────────────┘  └───────────────────────┘
```

## 2.3 Data Model

### Collection: `event_timeline`

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "correlation_id": "uuid (propagated through entire flow)",
  "entity_type": "reservation | ari_update | sync_job | night_audit | folio",
  "entity_id": "string (PMS booking ID, folio ID, etc.)",
  "external_id": "string (OTA reservation ID, nullable)",
  "stage": "received | validated | normalized | deduped | import_decided | stored | queued | dispatched | pushed | confirmed | failed | retried | cancelled",
  "status": "success | failure | skipped | in_progress",
  "source": "webhook_exely | webhook_hotelrunner | ingest_pipeline | import_bridge | outbox_worker | ari_push_worker | provider_callback | night_audit_engine | manual",
  "provider": "exely | hotelrunner | pms_direct | null",
  "timestamp": "ISO8601",
  "duration_ms": 45,
  "sequence": 1,
  "metadata": {
    "raw_payload_hash": "sha256 (for duplicate detection tracing)",
    "error_message": "string (if status=failure)",
    "error_code": "IMPORT_TIMEOUT",
    "retry_count": 0,
    "worker_id": "host:pid:uuid",
    "decision": "auto_import | review_required | duplicate",
    "import_id": "uuid (link to imported_reservations)",
    "outbox_event_id": "uuid (link to outbox_events)",
    "booking_id": "uuid (PMS booking, set after import)",
    "room_id": "string (set after room assignment)"
  },
  "parent_event_id": "uuid (for tree/DAG tracing, null for root)"
}
```

### Indexes

```python
# Primary lookup paths
("tenant_id", "entity_id", "timestamp")          # Timeline by entity
("tenant_id", "correlation_id", "timestamp")      # Timeline by correlation
("tenant_id", "external_id", "timestamp")         # Timeline by OTA ID
("entity_type", "stage", "status", "timestamp")   # Stage health queries
("timestamp",)                                     # TTL: 90 days
```

### Stage Sequence (Expected Order)

```
reservation flow:
  received → validated → normalized → deduped → import_decided
  → stored → queued → dispatched → pushed → confirmed

ari flow:
  queued → dispatched → pushed → confirmed

night_audit flow:
  started → validating → posting → reconciling → rolling → completed
```

## 2.4 APIs

```
GET  /api/ops/timeline/{entity_type}/{entity_id}
     → Full timeline for an entity
     → Response: {
         entity_type, entity_id, external_id,
         timeline: [TimelineEvent],
         total_duration_ms: 1250,
         current_stage: "confirmed",
         gap_warnings: []
       }

GET  /api/ops/timeline/correlation/{correlation_id}
     → All events sharing a correlation ID
     → Response: { events: [TimelineEvent], entity_map: {} }

GET  /api/ops/timeline/external/{external_id}
     → Lookup by OTA reservation ID (most common debug entry point)
     → Response: same as entity timeline

GET  /api/ops/timeline/search
     → Query params: tenant_id, provider, stage, status, from, to, limit
     → Response: { events: [TimelineEvent], total: int }

GET  /api/ops/timeline/gaps
     → Events stuck in intermediate stages
     → Response: { stuck_events: [{ entity_id, last_stage, stuck_since, age_seconds }] }
```

## 2.5 Flow (Step-by-Step)

### Write Path — Reservation Import

```
1. Exely webhook hits /api/channel-manager/v2/webhooks/exely
   → TimelineWriter.append(
       correlation_id=new_uuid(),
       entity_type="reservation",
       external_id=exely_reservation_id,
       stage="received",
       source="webhook_exely",
       provider="exely"
     )

2. Ingest pipeline normalizes payload
   → TimelineWriter.append(
       correlation_id=same,
       stage="normalized",
       source="ingest_pipeline",
       metadata={"raw_payload_hash": sha256}
     )

3. Dedup check passes (or flags duplicate)
   → TimelineWriter.append(
       correlation_id=same,
       stage="deduped",
       status="success" | "skipped",
       metadata={"decision": "new" | "duplicate"}
     )

4. Import decision engine evaluates
   → TimelineWriter.append(
       correlation_id=same,
       stage="import_decided",
       metadata={"decision": "auto_import", "import_id": uuid}
     )

5. Import bridge creates PMS booking via create_booking_atomic
   → TimelineWriter.append(
       correlation_id=same,
       entity_id=new_booking_id,  ← entity_id set here
       stage="stored",
       source="import_bridge",
       metadata={"booking_id": new_booking_id, "room_id": "101"}
     )

6. Outbox event enqueued for OTA confirmation
   → TimelineWriter.append(
       correlation_id=same,
       stage="queued",
       source="outbox_service",
       metadata={"outbox_event_id": uuid}
     )

7. Outbox worker dispatches
   → TimelineWriter.append(
       correlation_id=same,
       stage="dispatched",
       source="outbox_worker",
       metadata={"worker_id": "host:pid:abc123"}
     )

8. Provider confirms
   → TimelineWriter.append(
       correlation_id=same,
       stage="confirmed",
       source="provider_callback"
     )
```

### Read Path — Debug from OTA ID

```
1. Operator receives complaint: "Exely reservation 12345 not in PMS"
2. GET /api/ops/timeline/external/12345
3. Response shows:
   - received: OK (10:05:00)
   - normalized: OK (10:05:01)
   - deduped: OK (10:05:01)
   - import_decided: OK (10:05:02, decision=auto_import)
   - stored: FAILED (10:05:03, error="BookingConflictError: Room 101 overlap")
   - ← NO further stages. Root cause: overbooking conflict
4. Operator resolves: assigns different room, manually retries import
```

### Gap Detection

```python
EXPECTED_SEQUENCES = {
    "reservation": ["received", "normalized", "deduped", "import_decided", "stored", "queued", "dispatched", "confirmed"],
    "ari_update": ["queued", "dispatched", "pushed", "confirmed"],
}

def detect_gaps(timeline: List[TimelineEvent], entity_type: str) -> List[str]:
    expected = EXPECTED_SEQUENCES[entity_type]
    actual_stages = [e.stage for e in timeline if e.status == "success"]
    gaps = []
    for i, expected_stage in enumerate(expected):
        if expected_stage not in actual_stages:
            gaps.append(f"Missing stage: {expected_stage} (expected at position {i})")
    return gaps
```

## 2.6 Failure Modes

| Failure | Impact | Detection | Recovery |
|---------|--------|-----------|----------|
| Timeline write fails (DB error) | Gap in timeline | Gap detection query finds missing stages | Fire-and-forget write; main flow continues. Gap = investigation trigger. |
| Correlation ID not propagated | Orphaned events | Events with no correlation_id = anomaly | Enrich retroactively via entity_id + timestamp proximity |
| Duplicate timeline events | Noise in timeline | Dedup on (entity_id, stage, source) | Upsert pattern — skip if exists |
| High write volume (burst) | Write latency spike | Timeline write p95 > 50ms | Batch writes (buffer 10 events, flush every 100ms) |

## 2.7 Metrics to Track

| Metric | Target | Alert |
|--------|--------|-------|
| Timeline event write latency p95 | < 20ms | > 100ms |
| Average reservation pipeline duration | < 60s | > 300s |
| Gap detection hit rate | 0% | > 1% |
| Stuck events (stage age > 30min) | 0 | > 5 |
| Timeline events per day | N/A | > 1M (capacity plan) |

---

# 3. SECURITY: KEY ROTATION + BREACH SIMULATION

## 3A. Key Rotation System

### 3A.1 Problem Definition

Current state: `KeyRing` in `core/crypto/keys.py` loads keys at startup from env vars. No rotation mechanism. If a key is compromised, all encrypted data (provider credentials, PII) is exposed until manual re-encryption.

### 3A.2 Target Architecture

```
┌─────────────────────────────────────────────────────┐
│               KEY LIFECYCLE MANAGER                   │
│                                                       │
│  ┌───────────────────────────────────────────────┐   │
│  │  KeyRotationService                            │   │
│  │  - generate_new_key() → kid                    │   │
│  │  - activate_key(kid)                           │   │
│  │  - initiate_rotation(old_kid, new_kid)         │   │
│  │  - check_rotation_progress(rotation_id)        │   │
│  │  - complete_rotation(rotation_id)              │   │
│  │  - revoke_key(kid)                             │   │
│  └────────┬─────────────────────────┬─────────────┘   │
│           │                         │                  │
│  ┌────────▼──────┐    ┌────────────▼──────────┐       │
│  │ crypto_key_   │    │ ReEncryptionWorker    │       │
│  │ registry      │    │ - batch re-encrypt    │       │
│  │ (collection)  │    │ - progress tracking   │       │
│  └───────────────┘    │ - resume on failure   │       │
│                       └───────────────────────┘       │
└───────────────────────────────────────────────────────┘
```

### 3A.3 Data Model

#### Collection: `crypto_key_registry`

```json
{
  "id": "uuid",
  "kid": "string (key identifier, e.g., 'k-2026-02-v1')",
  "algorithm": "AES-256-GCM",
  "status": "pending | active | rotating | retired | revoked",
  "key_material_encrypted": "base64 (master-key-encrypted or KMS-wrapped)",
  "key_hash": "sha256 of raw key (for integrity check, NOT the key itself)",
  "created_at": "ISO8601",
  "activated_at": "ISO8601 | null",
  "rotation_started_at": "ISO8601 | null",
  "retired_at": "ISO8601 | null",
  "revoked_at": "ISO8601 | null",
  "successor_kid": "string | null",
  "predecessor_kid": "string | null",
  "metadata": {
    "rotation_reason": "scheduled | compromised | policy | manual",
    "created_by": "system | operator_name",
    "key_spec": "256-bit",
    "allowed_operations": ["encrypt", "decrypt"]
  }
}
```

#### Collection: `crypto_rotation_jobs`

```json
{
  "id": "uuid",
  "old_kid": "string",
  "new_kid": "string",
  "status": "running | completed | failed | paused",
  "started_at": "ISO8601",
  "completed_at": "ISO8601 | null",
  "collections_to_process": [
    {
      "collection": "exely_connections",
      "field_paths": ["credentials.password", "credentials.api_key"],
      "total_documents": 50,
      "processed": 48,
      "failed": 0,
      "last_processed_id": "uuid"
    }
  ],
  "progress_percent": 96.0,
  "error_log": [],
  "heartbeat_at": "ISO8601"
}
```

### 3A.4 APIs

```
POST /api/ops/security/keys/generate
     → Generate a new encryption key (does NOT activate)
     → Body: { reason: "scheduled_rotation" }
     → Response: { kid: "k-2026-02-v2", status: "pending" }

POST /api/ops/security/keys/{kid}/activate
     → Activate key for new encryptions
     → Response: { kid, status: "active", predecessor_kid }

POST /api/ops/security/keys/rotate
     → Start rotation from old active key to specified new key
     → Body: { new_kid: "k-2026-02-v2" }
     → Response: { rotation_id, old_kid, new_kid, status: "running", estimated_duration_minutes }

GET  /api/ops/security/keys/rotation/{rotation_id}
     → Check rotation progress
     → Response: { progress_percent, collections_status: [...], estimated_remaining_minutes }

POST /api/ops/security/keys/{kid}/revoke
     → Revoke a retired key (no more decryption)
     → Response: { kid, status: "revoked" }

GET  /api/ops/security/keys
     → List all keys with status
     → Response: { keys: [{ kid, status, created_at, activated_at }] }
```

### 3A.5 Rotation Flow (Zero-Downtime)

```
Phase 1: PREPARE
  1. Generate new key → crypto_key_registry (status=pending)
  2. Activate new key → status=active, old key status=rotating
  3. KeyRing now has TWO active keys:
     - New key: used for ALL new encrypt() calls
     - Old key: used for decrypt() of existing data

Phase 2: RE-ENCRYPT (Background Worker)
  4. ReEncryptionWorker starts:
     a. Query crypto_rotation_jobs for collections to process
     b. For each collection:
        - Find documents with envelope.kid = old_kid
        - Decrypt with old key → re-encrypt with new key
        - Update document atomically
        - Track progress (last_processed_id for resume)
     c. Rate-limited: 100 documents/second (avoid DB pressure)
  5. Progress visible via /api/ops/security/keys/rotation/{id}

Phase 3: COMPLETE
  6. When all collections 100% re-encrypted:
     a. Old key status → retired
     b. KeyRing removes old key from encrypt() pool
     c. Old key still available for decrypt() (backward compat for missed docs)
  7. After retention period (30 days): old key status → revoked

EMERGENCY: Compromised Key
  - Skip Phase 2 gradual approach
  - Immediately revoke old key
  - All decryption with old key returns error
  - Force re-encryption at maximum speed
  - Accept temporary service degradation
```

## 3B. Breach Simulation System

### 3B.1 Problem Definition

No way to validate that tenant isolation, rate limiting, anomaly detection, and revocation actually work under attack conditions. The chaos tests validate subsystem behavior but not coordinated attack scenarios.

### 3B.2 Target Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  BREACH SIMULATION ENGINE                    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  BreachSimulator                                    │     │
│  │  - run_scenario(scenario_type, params)              │     │
│  │  - Scenarios:                                       │     │
│  │    1. compromised_api_key                           │     │
│  │    2. stolen_jwt_token                              │     │
│  │    3. tenant_boundary_probe                         │     │
│  │    4. privilege_escalation_attempt                   │     │
│  │    5. credential_stuffing_simulation                │     │
│  │    6. data_exfiltration_attempt                     │     │
│  └─────────┬────────────────────────┬──────────────────┘     │
│            │                        │                        │
│   ┌────────▼────────┐    ┌─────────▼────────────────┐       │
│   │ breach_         │    │ DETECTION LAYER           │       │
│   │ simulations     │    │ - Anomaly detector        │       │
│   │ (collection)    │    │ - Rate limiter            │       │
│   │                 │    │ - Tenant guard             │       │
│   │                 │    │ - Alert engine             │       │
│   └─────────────────┘    └──────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

### 3B.3 Data Model

#### Collection: `breach_simulations`

```json
{
  "id": "uuid",
  "simulation_type": "compromised_api_key | stolen_jwt | tenant_boundary | privilege_escalation | credential_stuffing | data_exfiltration",
  "status": "scheduled | running | completed | failed",
  "initiated_by": "string",
  "started_at": "ISO8601",
  "completed_at": "ISO8601 | null",
  "scenario": {
    "description": "Simulate compromised Exely API key used from unknown IP",
    "target_tenant_id": "string",
    "target_provider": "exely",
    "simulated_actions": [
      {
        "action": "access_other_tenant_data",
        "expected_result": "blocked",
        "actual_result": "blocked",
        "detection_time_ms": 5
      },
      {
        "action": "escalate_to_super_admin",
        "expected_result": "blocked",
        "actual_result": "blocked",
        "detection_time_ms": 2
      },
      {
        "action": "export_guest_pii",
        "expected_result": "blocked",
        "actual_result": "blocked",
        "detection_time_ms": 8
      }
    ]
  },
  "results": {
    "all_blocked": true,
    "detection_time_avg_ms": 5,
    "detection_time_max_ms": 8,
    "alerts_fired": ["tenant_boundary_violation", "suspicious_access_pattern"],
    "false_positives": 0,
    "access_blocked_count": 3,
    "data_exposed": false,
    "containment_time_ms": 15
  },
  "verdict": "PASS | FAIL | PARTIAL"
}
```

### 3B.4 APIs

```
POST /api/ops/security/breach-sim/run
     → Body: { simulation_type, target_tenant_id, dry_run: bool }
     → Response: { simulation_id, status: "running" }

GET  /api/ops/security/breach-sim/{simulation_id}
     → Response: Full simulation result

GET  /api/ops/security/breach-sim/history
     → Query: limit, simulation_type
     → Response: { simulations: [...], pass_rate: 100.0 }

POST /api/ops/security/breach-sim/schedule
     → Body: { simulation_type, cron: "0 3 * * 0", target_tenant_id }
     → Schedule weekly breach simulations
```

### 3B.5 Scenario Flows

#### Scenario 1: Compromised API Key

```
1. Generate a valid JWT for tenant A
2. Attempt GET /api/pms/bookings with tenant B's context
   → EXPECTED: 403 (tenant guard blocks)
   → MEASURE: detection_time_ms

3. Attempt POST /api/admin/users with elevated role
   → EXPECTED: 403 (role guard blocks)

4. Attempt GET /api/ops/secrets/audit (admin-only)
   → EXPECTED: 403

5. Verify alerts fired in cp_alerts
6. Verify audit log entries created
7. Record results in breach_simulations
```

#### Scenario 2: Credential Stuffing

```
1. Send 100 login attempts in 60 seconds to /api/auth/login
2. EXPECTED:
   - First 5-10 attempts processed normally
   - Rate limiter kicks in (429 response)
   - Alert fires (credential_stuffing_detected)
   - Account NOT locked (rate limiter sufficient)
3. Verify: no successful auth with wrong credentials
4. Verify: legitimate user can still log in after cooldown
```

### 3B.6 Failure Modes

| Failure | Impact | Detection |
|---------|--------|-----------|
| Tenant guard bypass | Cross-tenant data exposure | Breach sim FAIL verdict |
| Rate limiter disabled | Brute force succeeds | Credential stuffing sim FAIL |
| Alert engine down | No detection notification | Simulation completes but alerts_fired = 0 |
| Slow detection (>1s) | Attack window too wide | detection_time_max_ms > 1000 |

### 3B.7 Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Breach sim pass rate | 100% | < 100% |
| Average detection time | < 10ms | > 100ms |
| False positive rate | < 5% | > 10% |
| Simulation coverage (scenarios run/total) | 100% weekly | < 80% |

---

# 4. INFRASTRUCTURE MATURITY

## 4.1 Problem Definition

Current state:
- Docker Compose for production (`docker-compose.prod.yml`) — not IaC
- K8s manifests exist (`infra/k8s/`) but are raw YAML, no templating
- No environment parity enforcement — staging config can drift from production
- No deployment gates — a bad config can go to production
- No config validation system — missing env vars fail at runtime

## 4.2 Target Architecture

### A. Terraform Structure

```
infra/terraform/
├── environments/
│   ├── dev/
│   │   ├── main.tf              # Module composition for dev
│   │   ├── terraform.tfvars     # Dev-specific values
│   │   └── backend.tf           # S3 state backend (dev)
│   ├── staging/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   └── production/
│       ├── main.tf
│       ├── terraform.tfvars
│       └── backend.tf
├── modules/
│   ├── mongodb-atlas/           # MongoDB Atlas cluster
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── redis/                   # ElastiCache Redis
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── ecs-backend/             # ECS Fargate backend service
│   │   ├── main.tf              # Task def, service, ALB target group
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── ecs-worker/              # ECS Fargate worker service
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── networking/              # VPC, subnets, security groups
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── monitoring/              # CloudWatch, alarms, dashboards
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── secrets/                 # AWS Secrets Manager resources
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── cdn-frontend/            # CloudFront + S3 for frontend
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── scripts/
    ├── plan.sh                  # terraform plan with env selection
    ├── apply.sh                 # terraform apply with approval gate
    ├── validate-parity.sh       # Compare staging vs production configs
    └── drift-detect.sh          # Detect infrastructure drift
```

### B. Environment Parity System

## 4.3 Data Model

### Config Validation Schema: `config_validation_rules.json`

```json
{
  "version": "1.0",
  "rules": [
    {
      "key": "MONGO_URL",
      "required": true,
      "type": "string",
      "pattern": "^mongodb(\\+srv)?://",
      "environments": ["staging", "production"],
      "description": "MongoDB connection string"
    },
    {
      "key": "JWT_SECRET",
      "required": true,
      "type": "string",
      "min_length": 32,
      "environments": ["*"],
      "sensitive": true,
      "description": "JWT signing secret"
    },
    {
      "key": "REDIS_URL",
      "required": true,
      "type": "string",
      "pattern": "^redis://",
      "environments": ["staging", "production"]
    },
    {
      "key": "SECRETS_PROVIDER",
      "required": true,
      "type": "enum",
      "allowed_values": ["local_dev", "aws_secrets_manager", "vault"],
      "environments": ["*"],
      "production_required_value": "aws_secrets_manager"
    },
    {
      "key": "CRYPTO_V2_ENABLED",
      "required": true,
      "type": "boolean",
      "production_required_value": "true",
      "environments": ["staging", "production"]
    },
    {
      "key": "STRICT_TENANT_MODE",
      "required": true,
      "type": "boolean",
      "production_required_value": "true",
      "environments": ["production"]
    },
    {
      "key": "SENTRY_DSN",
      "required": true,
      "type": "string",
      "pattern": "^https://.*@.*\\.ingest\\.sentry\\.io/",
      "environments": ["staging", "production"]
    },
    {
      "key": "ALERT_WEBHOOK_URL",
      "required": true,
      "type": "string",
      "pattern": "^https://hooks\\.slack\\.com/",
      "environments": ["production"]
    }
  ]
}
```

## 4.4 APIs

```
POST /api/ops/infra/validate-config
     → Validates current environment config against rules
     → Response: {
         valid: false,
         environment: "staging",
         errors: [
           { key: "ALERT_WEBHOOK_URL", error: "Missing required variable" },
           { key: "JWT_SECRET", error: "Length 16 < minimum 32" }
         ],
         warnings: [
           { key: "SENTRY_DSN", warning: "Using development DSN in staging" }
         ]
       }

GET  /api/ops/infra/parity-check
     → Compares staging and production config structures
     → Response: {
         parity_score: 95.0,
         mismatches: [
           { key: "WORKER_REPLICAS", staging: "1", production: "3", severity: "info" },
           { key: "SECRETS_PROVIDER", staging: "local_dev", production: "aws_secrets_manager", severity: "warning" }
         ]
       }

POST /api/ops/infra/deployment-gate
     → Pre-deployment check (called by CI/CD)
     → Body: { target_environment: "production", image_tag: "v1.2.3" }
     → Response: {
         approved: false,
         blockers: [
           "Config validation failed: STRICT_TENANT_MODE not enabled",
           "3 unresolved CRITICAL failures in control plane"
         ],
         warnings: [
           "2 P2 issues in backlog"
         ]
       }
```

## 4.5 Deployment Gate Flow

```
1. Developer pushes to main branch
2. CI builds Docker images, pushes to registry
3. CI calls POST /api/ops/infra/deployment-gate { target: "staging" }
4. Gate checks:
   a. Config validation passes for target environment
   b. All critical/high failures resolved (cp_failures)
   c. Health score > 75
   d. No running key rotations
   e. All tests pass (pytest + frontend)
5. If approved → deploy to staging
6. Staging soak: 30 minutes with health score monitoring
7. CI calls POST /api/ops/infra/deployment-gate { target: "production" }
8. Production gate adds:
   a. Staging soak passed
   b. STRICT_TENANT_MODE = true
   c. SECRETS_PROVIDER = aws_secrets_manager
   d. SENTRY_DSN configured
   e. ALERT_WEBHOOK_URL configured
9. If approved → deploy to production (rolling update)
```

## 4.6 Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Terraform state corruption | Cannot update infra | S3 state backend with versioning + DynamoDB locking |
| Config drift (manual change) | Staging != production | Weekly drift detection script + alert |
| Bad deploy passes gate | Production incident | Gate checks are additive, not replaceable. Manual approval for exceptions. |
| Missing env var in production | Runtime crash | Config validation runs at startup (startup_validator.py) + deployment gate |

## 4.7 Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Config parity score | > 95% | < 85% |
| Deployment gate approval rate | > 90% | < 70% (too many blockers) |
| Infrastructure drift count | 0 | > 3 drifted resources |
| Time from merge to production | < 2 hours | > 8 hours |

---

# 5. ARCHITECTURE CONSISTENCY (MONOLITH CLEANUP)

## 5.1 Problem Definition

Current codebase has:
- **~150+ Python files** in `backend/` root (flat structure)
- **Dual domain patterns**: `domains/` (new, modular) AND `*_endpoints.py`, `*_models.py` (legacy, flat)
- **Multiple channel manager locations**: `channel_manager/` AND `domains/channel_manager/`
- **Inconsistent imports**: some via `core.database`, some direct MongoDB
- **~264 legacy `db` imports** that bypass tenant isolation
- **No clear service boundaries** — routers call DB directly

## 5.2 Target Architecture

### Final Module Map

```
backend/
├── server.py                    # Bootstrap orchestrator (< 300 lines)
├── app.py                       # FastAPI app factory
├── bootstrap/                   # Startup wiring (middleware, routers, workers)
│
├── core/                        # SHARED KERNEL (cross-cutting)
│   ├── database.py              # DB connection singleton
│   ├── security.py              # Auth, JWT, password hashing
│   ├── audit.py                 # Audit event logger
│   ├── helpers.py               # Permission guards
│   ├── crypto/                  # AES-256-GCM encryption
│   ├── secrets/                 # Unified secrets manager
│   ├── atomic_booking.py        # Transaction-safe booking creation
│   ├── import_bridge_service.py # OTA → PMS import
│   ├── outbox_service.py        # Outbox write-side
│   ├── outbox_worker.py         # Outbox worker (background)
│   └── night_audit_hardened.py  # Financial close engine
│
├── controlplane/                # OPERATIONAL LAYER (stays isolated)
│   ├── failure_model.py         # Taxonomy
│   ├── failure_tracker.py       # Central failure recording
│   ├── retry_engine.py          # Idempotent retry
│   ├── alerting.py              # Alert engine
│   ├── ops_router.py            # /api/ops/* endpoints
│   ├── dashboard_service.py     # NEW: Dashboard aggregation
│   ├── dashboard_router.py      # NEW: Dashboard API
│   ├── timeline_service.py      # NEW: Event timeline
│   └── timeline_router.py       # NEW: Timeline API
│
├── domains/                     # BUSINESS DOMAINS
│   ├── pms/                     # PMS CORE (monolith — intentional)
│   │   ├── reservations/        # Booking CRUD, lifecycle
│   │   ├── rooms/               # Room management
│   │   ├── folio/               # Folio/ledger (migrated from modules/)
│   │   ├── night_audit/         # Night audit UI/scheduling
│   │   ├── housekeeping/        # HK board, tasks
│   │   ├── frontdesk_router.py  # Front desk operations
│   │   ├── calendar_router.py   # Calendar view
│   │   └── dashboard_router.py  # PMS dashboard
│   │
│   ├── channel_manager/         # CHANNEL MANAGER (isolated)
│   │   ├── connectors/          # Provider implementations
│   │   ├── mapping/             # Room/rate mapping
│   │   ├── ingest/              # Webhook ingestion
│   │   ├── sync/                # ARI push/pull
│   │   ├── reconciliation/      # Drift detection
│   │   └── router.py            # Unified CM router
│   │
│   ├── revenue/                 # REVENUE MANAGEMENT (isolated)
│   │   ├── pricing/             # Rate management
│   │   ├── forecasting/         # Demand prediction
│   │   ├── rms/                 # Revenue management system
│   │   └── analytics_router.py  # Revenue analytics
│   │
│   ├── guest/                   # GUEST EXPERIENCE
│   │   ├── journey/             # Guest lifecycle
│   │   ├── messaging/           # WhatsApp, email
│   │   └── segmentation/        # Guest DNA
│   │
│   ├── admin/                   # ADMIN (cross-cutting)
│   │   └── router.py            # User/tenant management
│   │
│   └── sales/                   # SALES & CRM
│       └── crm_router.py
│
├── workers/                     # BACKGROUND WORKERS
│   ├── ari_push_worker.py
│   ├── ari_drift_worker.py
│   ├── queue_monitor.py
│   └── worker_runtime_service.py
│
├── shared_kernel/               # SHARED UTILITIES
│   ├── idempotency.py
│   ├── event_envelope.py
│   ├── tenancy_context.py
│   └── audit_helper.py
│
├── infra/                       # INFRASTRUCTURE
│   ├── distributed_lock.py
│   ├── backup_manager.py
│   └── worker_queue.py
│
├── models/                      # SHARED MODELS (Pydantic + Enums)
│   ├── schemas.py
│   └── enums.py
│
├── security/                    # SECURITY LAYER
│   ├── tenant_guard.py
│   ├── rate_limiter.py
│   └── credential_guard.py
│
└── tests/                       # ALL TESTS
    ├── resilience/              # Chaos/resilience tests
    ├── integration/             # Integration tests
    ├── unit/                    # Unit tests
    └── conftest.py
```

### What Stays Monolith (and WHY)

| Component | Reason | Risk if Separated |
|-----------|--------|-------------------|
| PMS Core (bookings + rooms + folios + night audit) | Transactions span rooms, bookings, and folios atomically. MongoDB multi-document transactions require same-connection scope. | Data inconsistency. Booking created but folio not opened. Room assigned but booking not updated. |
| Admin | Cross-cutting: user management touches every domain. | Circular dependencies. |
| Security | Cross-cutting: tenant isolation, crypto, auth used by all domains. | Security gaps if isolated and misaligned. |

### What Becomes Isolated (Strict Interface Boundaries)

| Component | Interface | Communication |
|-----------|-----------|--------------|
| Channel Manager | `ChannelManagerService` (3 methods: pull, push, status) | In-process function calls today. Can become HTTP/gRPC later. |
| Revenue | `RevenueService` (pricing, forecasting) | In-process. Reads PMS data, writes revenue collections. |
| Control Plane | `ControlPlaneService` (record, query, retry) | In-process. Separate deployment candidate for future. |

### Migration Plan (Legacy Cleanup)

```
Phase 1 (Week 1): AUDIT
  - Catalog all files in backend/ root that are NOT in core/ or domains/
  - Count: ~80+ legacy files (endpoints, models, services)
  - Tag each file: KEEP_IN_PLACE | MOVE_TO_DOMAIN | DEPRECATE

Phase 2 (Week 2): MOVE NON-BREAKING
  - Move standalone *_models.py files into domains/*/models/
  - Move standalone *_endpoints.py files into domains/*/routers/
  - Update imports (keep aliases for backward compat during transition)

Phase 3 (Week 3): FIX DB IMPORTS
  - Replace direct `from core.database import db` with tenant-scoped access
  - Use grep to find all 264 instances
  - Prioritize: PMS core > Channel Manager > Others

Phase 4 (Week 4): CLEAN UP
  - Remove backward compat aliases
  - Delete deprecated files
  - Run full test suite to verify
```

## 5.3 Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Import path change breaks endpoint | 500 errors on affected routes | Keep aliases during transition. Run full test suite after each move. |
| Missing tenant_id after db import fix | Unscoped queries return all tenants' data | STRICT_TENANT_MODE catches this at runtime |
| Circular dependency introduced | App won't start | Test startup in CI after each refactor batch |

---

# 6. PMS CORE BATTLE-TESTING

## 6.1 Problem Definition

The PMS handles real hotel operations. A bug in reservation handling means:
- **Lost revenue** (overbooking, missed charges)
- **Guest complaints** (wrong room, wrong bill)
- **Regulatory risk** (incorrect financial records)
- **OTA penalties** (inaccurate availability, stale rates)

Current test coverage focuses on happy paths. Edge cases that happen daily in real hotels are untested.

## 6.2 Test Matrix

### Scenario 1: Split Reservation

| Aspect | Detail |
|--------|--------|
| **Setup** | Booking B1: Room 101, 5 nights (Feb 1-6), status=checked_in, folio F1 with 2 nights posted |
| **Action** | Split at night 3 (Feb 3): B1 becomes Feb 1-3, new B2 becomes Feb 3-6 |
| **Expected: Booking** | B1: check_out=Feb 3, status=checked_out. B2: check_in=Feb 3, check_out=Feb 6, status=checked_in, same guest_id, same room_id |
| **Expected: Folio** | F1: closed, balance=0 (2 nights posted, 2 nights paid). F2: opened for B2, 3 nights remaining charges. Transfer entry linking F1→F2 for any credits. |
| **Expected: Inventory** | Room 101: still occupied Feb 3-6 (no availability change). ARI update NOT triggered (same room). |
| **Expected: OTA** | Outbox event: booking.modified.v1 for B1 (shortened). Outbox event: booking.created.v1 for B2 (new). |
| **Failure Handling** | TRANSACTION: Both bookings created or neither. Folio split balances to ZERO. If atomic fails, rollback entirely. |
| **Edge Case** | Split on check-in date → reject. Split on check-out date → reject. Split with unpaid folio → transfer balance to new folio. |

### Scenario 2: No-Show

| Aspect | Detail |
|--------|--------|
| **Setup** | Booking B1: Room 101, Feb 1-3, status=confirmed, guest=G1 |
| **Action** | Night audit runs for Feb 1. Guest has not checked in by 23:59. |
| **Expected: Status** | B1: status → no_show |
| **Expected: Folio** | No-show charge posted: 1 night room rate + taxes. Folio status: open (balance due). |
| **Expected: Inventory** | Room 101 released for Feb 2 onwards. Availability +1 for Feb 2-3. ARI update pushed. |
| **Expected: OTA** | Outbox event: booking.cancelled.v1 (with no_show flag). |
| **Failure Handling** | If night audit fails mid-no-show: resume on next run (idempotent charge via unique index). If charge posting fails: booking stays confirmed, flagged for manual review. |
| **Edge Case** | No-show for group booking → each room handled independently. No-show for prepaid booking → no additional charge, just status update. |

### Scenario 3: Partial Stay (Early Checkout)

| Aspect | Detail |
|--------|--------|
| **Setup** | Booking B1: Room 101, 5 nights (Feb 1-6), status=checked_in, 3 nights posted |
| **Action** | Guest checks out Feb 4 (2 nights early) |
| **Expected: Status** | B1: check_out_date → Feb 4, status → checked_out |
| **Expected: Folio** | Nights 4-5 charges NOT posted. If prepaid: refund entry for 2 unused nights. If pay-at-checkout: final bill = 3 nights only. |
| **Expected: Inventory** | Room 101 released for Feb 4 onwards. Availability +1 for Feb 4-6. ARI update pushed. |
| **Expected: OTA** | Outbox event: booking.modified.v1 (shortened stay). |
| **Failure Handling** | Checkout atomic: room release + status update + folio close in single transaction. If refund calculation fails: flag folio for manual review, complete checkout. |
| **Edge Case** | Checkout before any night audit → 0 charges posted, full refund if prepaid. Checkout same day as check-in (0-night stay) → cancellation policy applies. |

### Scenario 4: Room Change Mid-Stay

| Aspect | Detail |
|--------|--------|
| **Setup** | Booking B1: Room 101, Feb 1-6, status=checked_in, 2 nights posted to folio |
| **Action** | Move guest to Room 201 on Feb 3 |
| **Expected: Booking** | B1: room_id → 201, room_history: [{room: 101, from: Feb 1, to: Feb 3}, {room: 201, from: Feb 3, to: Feb 6}] |
| **Expected: Folio** | Rate adjustment entry if room 201 has different rate. Remaining nights (Feb 3-6) posted at room 201 rate. |
| **Expected: Inventory** | Room 101: released Feb 3-6, availability +1. Room 201: occupied Feb 3-6, availability -1. TWO ARI updates pushed. |
| **Expected: OTA** | Outbox event: booking.modified.v1 (room change). |
| **Failure Handling** | TRANSACTION: Room 201 conflict check (atomic_booking pattern). If 201 occupied → reject move, Room 101 unchanged. If move succeeds but ARI push fails → outbox retry handles it. |
| **Edge Case** | Move to maintenance room → reject. Move to different room type → rate recalculation required. Move on checkout day → reject (checkout instead). |

### Scenario 5: Overbooking Prevention

| Aspect | Detail |
|--------|--------|
| **Setup** | Room 101: Feb 1-3 occupied by B1 (confirmed) |
| **Action** | Attempt to book Room 101: Feb 2-4 for guest G2 |
| **Expected** | BookingConflictError raised. B2 NOT created. |
| **Import Path** | If from OTA import: imported_reservations.import_status → review_required. Timeline event: stage=import_decided, decision=review_required, reason="Room conflict". |
| **Manual Path** | API returns 409 with conflict details: { conflicting_booking_id: B1.id, overlap_dates: ["Feb 2", "Feb 3"] } |
| **Edge Case** | Unassigned import (no room_id) → skip conflict check, import succeeds, assign room later. Same-day check-out/check-in → NOT a conflict (check_out=Feb 2, check_in=Feb 2 is OK). |

### Scenario 6: Cancellation Edge Cases

| Scenario | Current Status | Action | Expected Result |
|----------|---------------|--------|-----------------|
| Cancel confirmed booking | confirmed | cancel | status→cancelled, folio charges voided, room released, ARI updated |
| Cancel after check-in | checked_in | cancel | REJECT: must checkout first, then cancel |
| Cancel no-show | no_show | cancel | status→cancelled, no-show charge stands (or reversed per policy) |
| Cancel with deposits | confirmed, folio has payment | cancel | Cancellation fee posted, remaining deposit refunded |
| Cancel past booking | checked_out | cancel | REJECT: cannot cancel completed stay |
| Cancel OTA booking | confirmed, source=exely | cancel | status→cancelled, outbox: booking.cancelled.v1, OTA notified |
| Double cancel | cancelled | cancel | Idempotent: return success, no state change |

## 6.3 Test Implementation Structure

```python
# tests/battle/test_split_reservation.py
class TestSplitReservation:
    async def test_split_creates_two_bookings(self):
    async def test_split_folio_balance_is_zero(self):
    async def test_split_transfers_credits(self):
    async def test_split_on_checkin_date_rejected(self):
    async def test_split_on_checkout_date_rejected(self):
    async def test_split_outbox_events_created(self):
    async def test_split_atomic_rollback_on_failure(self):

# tests/battle/test_noshow.py
class TestNoShow:
    async def test_noshow_detected_by_night_audit(self):
    async def test_noshow_charge_posted_idempotent(self):
    async def test_noshow_room_released(self):
    async def test_noshow_ari_updated(self):
    async def test_noshow_group_booking_independent(self):
    async def test_noshow_prepaid_no_extra_charge(self):

# tests/battle/test_partial_stay.py
# tests/battle/test_room_change.py
# tests/battle/test_overbooking.py
# tests/battle/test_cancellation_edges.py
```

## 6.4 Failure Modes & Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Overbooking rate | 0% | > 0% (any overbooking = P1 incident) |
| No-show detection rate | 100% | < 100% (missed no-show = revenue loss) |
| Room change success rate | > 99% | < 95% |
| Folio balance accuracy | 100% (to the cent) | Any mismatch = P1 |
| Cancellation idempotency | 100% | Double-cancel creates side effects = P1 |

---

# 7. FOLIO / PAYMENT / INVOICE HARDENING

## 7.1 Problem Definition

Current folio system:
- Mutable folio balance (computed field, can drift from entries)
- No immutable ledger (entries can be modified)
- No formal reconciliation between entries and balance
- Void/adjustment model unclear
- No double-entry validation
- Tax calculation embedded in night audit, not reusable

## 7.2 Target Architecture: Immutable Append-Only Ledger

```
┌────────────────────────────────────────────────────────────┐
│                     FOLIO LEDGER ENGINE                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              FolioLedgerService                       │    │
│  │  - post_charge(folio_id, amount, ...)                │    │
│  │  - post_payment(folio_id, amount, ...)               │    │
│  │  - void_entry(entry_id, reason)                      │    │
│  │  - transfer(from_folio, to_folio, amount)            │    │
│  │  - compute_balance(folio_id) → recalculated          │    │
│  │  - reconcile(folio_id) → match ledger vs balance     │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────▼────────────────────────────┐    │
│  │        Collection: folio_ledger (APPEND-ONLY)        │    │
│  │  - NEVER update existing entries                     │    │
│  │  - Void = new VOID entry referencing original        │    │
│  │  - Adjustment = new ADJUSTMENT entry                 │    │
│  │  - Transfer = paired TRANSFER_OUT + TRANSFER_IN      │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │        RECONCILIATION ENGINE (nightly)                │    │
│  │  - Compare: SUM(ledger entries) vs folio.balance      │    │
│  │  - On mismatch: create cp_failure (CRITICAL)          │    │
│  │  - Generate reconciliation report                     │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## 7.3 Data Model

### Collection: `folio_ledger` (IMMUTABLE)

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "folio_id": "string",
  "booking_id": "string",
  "sequence_number": 1,
  "entry_type": "charge | payment | void | adjustment | transfer_out | transfer_in | refund | tax",
  "amount": 150.00,
  "currency": "TRY",
  "description": "Room Charge - Standard Double - Night 1",
  "charge_code": "ROOM | FB | SPA | MINIBAR | PARKING | TELEPHONE | LAUNDRY | TAX | MISC",
  "tax_amount": 18.00,
  "tax_breakdown": [
    {"code": "KDV", "rate": 0.10, "amount": 15.00, "base_amount": 150.00},
    {"code": "TURIZM", "rate": 0.02, "amount": 3.00, "base_amount": 150.00}
  ],
  "payment_method": "cash | card | bank_transfer | online | city_ledger | null",
  "reference_id": "uuid (original entry ID — for voids, adjustments, transfer pairs)",
  "is_voided": false,
  "voided_by_entry_id": "uuid | null",
  "voided_at": "ISO8601 | null",
  "voided_reason": "string | null",
  "correlation_id": "uuid",
  "idempotency_key": "string (prevent double-posting)",
  "posted_by": "user_id | system:night_audit | system:import",
  "posted_at": "ISO8601",
  "business_date": "2026-02-15",
  "night_audit_run_id": "uuid | null (links to night_audit_runs)",
  "metadata": {
    "room_id": "string",
    "rate_code": "string",
    "rate_amount": 150.00,
    "nights": 1,
    "guest_id": "string",
    "source": "night_audit | manual | ota_import | pos | minibar"
  }
}
```

### Indexes

```python
("tenant_id", "folio_id", "sequence_number")     # Unique: ordered ledger
("tenant_id", "folio_id", "entry_type")           # Balance calculation
("tenant_id", "booking_id")                        # Booking → folio entries
("tenant_id", "business_date")                     # Daily reconciliation
("idempotency_key",)                               # Unique: prevent double-post
("tenant_id", "posted_at")                         # Audit queries
```

### Collection: `folio_reconciliation_reports`

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "business_date": "2026-02-15",
  "run_at": "ISO8601",
  "status": "balanced | mismatch | error",
  "summary": {
    "total_folios_checked": 150,
    "balanced": 148,
    "mismatched": 2,
    "errors": 0
  },
  "mismatches": [
    {
      "folio_id": "uuid",
      "booking_id": "uuid",
      "ledger_balance": 450.00,
      "folio_balance": 445.00,
      "difference": 5.00,
      "probable_cause": "missing_void_entry"
    }
  ]
}
```

## 7.4 APIs

```
POST /api/folio/{folio_id}/charge
     → Body: { amount, description, charge_code, tax_included, idempotency_key }
     → Creates CHARGE entry in folio_ledger
     → Updates folio.balance (derived)
     → Returns: { entry_id, new_balance }

POST /api/folio/{folio_id}/payment
     → Body: { amount, payment_method, reference, idempotency_key }
     → Creates PAYMENT entry
     → Returns: { entry_id, new_balance }

POST /api/folio/{folio_id}/void/{entry_id}
     → Body: { reason }
     → Creates VOID entry (does NOT modify original)
     → Sets original.is_voided=true (only allowed field update)
     → Returns: { void_entry_id, new_balance }

POST /api/folio/{folio_id}/transfer
     → Body: { to_folio_id, amount, description, idempotency_key }
     → Creates TRANSFER_OUT in source + TRANSFER_IN in target (atomically)
     → Returns: { transfer_out_id, transfer_in_id }

GET  /api/folio/{folio_id}/ledger
     → Returns: { entries: [LedgerEntry], balance: computed, entry_count }

GET  /api/folio/{folio_id}/reconcile
     → Runs reconciliation check
     → Returns: { ledger_balance, folio_balance, balanced: bool, difference }

POST /api/ops/reconciliation/run
     → Run nightly reconciliation for all open folios
     → Returns: { report_id, summary }
```

## 7.5 Transaction Consistency Rules

```
RULE 1: Balance = SUM(charges + adjustments) - SUM(payments + refunds + voids_of_charges) +/- transfers
  → Computed EVERY time, never cached/stored as source of truth
  → folio.balance field is a denormalized cache, reconciled nightly

RULE 2: Void does NOT delete entries
  → Original entry: is_voided=true, voided_by_entry_id=void_entry.id
  → Void entry: entry_type=void, amount=-original.amount, reference_id=original.id

RULE 3: Transfer is paired
  → TRANSFER_OUT in source folio (amount = -transfer_amount)
  → TRANSFER_IN in target folio (amount = +transfer_amount)
  → Both created in same MongoDB transaction
  → Paired via correlation_id

RULE 4: Idempotency
  → Every POST includes idempotency_key
  → Unique index on idempotency_key prevents double-posting
  → Night audit uses deterministic key: f"{folio_id}:{business_date}:{charge_code}:{night}"

RULE 5: Audit trail
  → Every entry has posted_by, posted_at, business_date
  → Void entries have voided_reason
  → Transfer entries link to partner entry via correlation_id
```

## 7.6 Rollback Strategy

```
Scenario: Wrong charge posted to folio
  1. Operator identifies incorrect charge (entry_id=E1)
  2. POST /api/folio/{folio_id}/void/E1 { reason: "Incorrect room rate" }
  3. System creates:
     - VOID entry: amount=-E1.amount, reference_id=E1.id
     - Updates E1: is_voided=true
  4. Balance recalculated
  5. If correct charge needed: POST new charge with correct amount

Scenario: Failed mid-transaction (e.g., transfer)
  1. Transaction aborts (MongoDB transaction rollback)
  2. Neither TRANSFER_OUT nor TRANSFER_IN created
  3. Retry with same idempotency_key → safe to retry
  4. If partial commit somehow happens (shouldn't with transactions):
     → Reconciliation catches mismatch
     → Operator creates corrective ADJUSTMENT entry
```

## 7.7 Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Folio balance accuracy | 100.0% | Any mismatch (reconciliation) |
| Double-post prevention rate | 100% | Any duplicate entry bypasses idempotency |
| Void-to-charge ratio | < 5% | > 10% (training issue or system bug) |
| Reconciliation pass rate | 100% | < 99% |
| Ledger write latency p95 | < 50ms | > 200ms |

---

# 8. OPERATIONAL STRESS TESTING

## 8.1 Problem Definition

System has never been tested under production-like load for:
- OTA reservation bursts (check-in day morning, campaign launches)
- ARI update storms (bulk rate changes, stop-sale events)
- Provider downtime (Exely/HotelRunner maintenance windows)

## 8.2 Test Designs

### A. Reservation Burst Test

```yaml
test_id: STRESS-001
name: "OTA Reservation Burst"
description: "Simulate peak check-in day reservation inflow"

load_pattern:
  type: ramp_and_hold
  stages:
    - ramp_up: 0 → 50 rps over 60 seconds
    - hold: 50 rps for 300 seconds (5 min)
    - ramp_down: 50 → 0 rps over 30 seconds
  total_reservations: ~15,000

payload:
  source: generated
  provider: exely
  distribution:
    new_reservations: 70%
    modifications: 20%
    cancellations: 10%

infrastructure:
  backend_replicas: 2
  worker_replicas: 2
  mongodb: replica set (3 nodes)

assertions:
  - name: all_imported
    condition: imported_reservations.count(status=imported) >= 14,850  # 99% of 15,000
    timeout: 600s  # 10 minutes after burst ends

  - name: no_duplicates
    condition: |
      db.bookings.aggregate([
        { $group: { _id: "$external_reservation_id", count: { $sum: 1 } } },
        { $match: { count: { $gt: 1 } } }
      ]).length == 0

  - name: outbox_drained
    condition: outbox_events.count(status=pending) == 0
    timeout: 1800s  # 30 minutes

  - name: p99_latency
    condition: webhook_response_p99 < 5000  # 5 seconds
    
  - name: no_overbooking
    condition: booking_conflict_errors == 0 (for assigned rooms)

  - name: error_rate
    condition: failed_imports / total_imports < 0.01  # < 1%

failure_thresholds:
  FAIL: error_rate > 5%
  FAIL: any_duplicate == true
  FAIL: outbox_stuck > 60 minutes
  WARN: p99_latency > 3000ms
  WARN: error_rate > 1%

metrics_to_capture:
  - webhook_latency_percentiles (p50, p95, p99)
  - import_pipeline_throughput (reservations/second)
  - outbox_depth_over_time
  - mongodb_ops_per_second
  - backend_cpu_utilization
  - backend_memory_utilization
  - worker_queue_depth
```

### B. ARI Storm Test

```yaml
test_id: STRESS-002
name: "ARI Update Storm"
description: "Simulate bulk rate change across all room types and dates"

load_pattern:
  type: burst
  stages:
    - burst: 200 ARI updates/second for 600 seconds (10 min)
  total_events: ~120,000

payload:
  event_types:
    rate_updated: 40%
    inventory_availability_updated: 40%
    restriction_updated: 20%
  date_range: next 90 days
  room_types: all mapped room types

assertions:
  - name: all_queued
    condition: outbox_events.count(type in ARI_TYPES) >= 118,800  # 99%
    timeout: 60s

  - name: provider_rate_limits_respected
    condition: |
      # HotelRunner: 5 calls/min, 250/day
      # Exely: per configured limit
      rate_limit_violations == 0

  - name: data_integrity
    condition: |
      # After storm settles, run reconciliation
      # PMS inventory state must match what was pushed to OTA
      ari_drift_count == 0
    timeout: 3600s  # 1 hour

  - name: no_oom
    condition: worker_restart_count == 0

  - name: backlog_cleared
    condition: outbox_events.count(status=pending) == 0
    timeout: 3600s

failure_thresholds:
  FAIL: data_drift > 0 (any inventory mismatch)
  FAIL: rate_limit_violation > 0
  FAIL: worker_oom (restart count > 0)
  WARN: backlog_clear_time > 2x burst_duration
```

### C. Provider Downtime Simulation

```yaml
test_id: STRESS-003
name: "Provider Downtime — Exely 503 for 30 Minutes"
description: "Simulate Exely returning 503 for all API calls"

scenario:
  phase_1_normal: 5 minutes of normal traffic (baseline)
  phase_2_failure: Mock Exely to return 503 for 30 minutes
    - All ARI pushes → 503
    - All reservation pulls → 503
  phase_3_recovery: Exely returns to normal
  phase_4_drain: Wait for backlog to clear

load_during_failure:
  ari_updates: 10/minute (normal hotel rate)
  reservation_pulls: 2/minute

assertions:
  - name: no_data_loss
    condition: |
      Every ARI update generated during downtime is in outbox_events
      Every outbox event eventually reaches "processed" status
    timeout: 7200s  # 2 hours total

  - name: retry_activated
    condition: |
      outbox_events with status=retry count > 0 during phase_2
      exponential backoff observed in retry_at timestamps

  - name: backlog_cleared_after_recovery
    condition: |
      outbox_events.count(status=pending) == 0
      Within 2x downtime_duration after recovery (60 minutes)

  - name: no_duplicates_after_recovery
    condition: |
      No duplicate ARI pushes to Exely after recovery
      (idempotency keys prevent double-push)

  - name: alert_fired
    condition: |
      cp_alerts with trigger=provider_auth_failure fired
      Within 5 minutes of first 503

  - name: metrics_captured
    condition: |
      cp_failures with provider=exely, failure_type=provider_error recorded
      For every failed attempt during downtime

failure_thresholds:
  CRITICAL: any_event_lost == true
  FAIL: duplicate_push > 0
  FAIL: no_alert_fired_within_5_min
  WARN: backlog_clear_time > 3x downtime_duration
```

## 8.3 Metrics to Track (All Tests)

| Metric | STRESS-001 | STRESS-002 | STRESS-003 |
|--------|-----------|-----------|-----------|
| Throughput | reservations/sec | outbox events/sec | events queued during downtime |
| Latency p50/p95/p99 | webhook response | outbox dispatch | N/A |
| Error rate | failed imports % | failed pushes % | retry rate |
| Data integrity | duplicate bookings | ARI drift count | lost events |
| Resource utilization | CPU, memory, connections | CPU, memory, disk IO | queue depth, memory |
| Recovery time | N/A | backlog drain time | backlog drain time |

---

# 9. REAL-WORLD EXPOSURE STRATEGY

## 9.1 Problem Definition

Moving from test to production requires:
- Gradual exposure (not big-bang)
- Feature isolation (one broken feature doesn't take down PMS)
- Quick rollback (< 5 minutes to disable any feature)
- Real-time monitoring during exposure

## 9.2 Target Architecture

### Feature Gating System

```
┌─────────────────────────────────────────────────────┐
│                 FEATURE GATE SERVICE                  │
│                                                       │
│  ┌───────────────────────────────────────────────┐   │
│  │  FeatureGateService                            │   │
│  │  - is_enabled(feature, tenant_id) → bool       │   │
│  │  - enable(feature, tenant_id)                  │   │
│  │  - disable(feature, tenant_id)                 │   │
│  │  - enable_global(feature)                      │   │
│  │  - kill(feature) → immediate global disable    │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  Collection: feature_gates                            │
└───────────────────────────────────────────────────────┘
```

## 9.3 Data Model

### Collection: `feature_gates`

```json
{
  "id": "uuid",
  "feature": "channel_manager.ari_push",
  "status": "enabled | disabled | killed",
  "scope": "global | tenant | percentage",
  "enabled_tenants": ["tenant_1", "tenant_2"],
  "percentage": 0,
  "kill_switch": {
    "active": false,
    "triggered_at": null,
    "triggered_by": null,
    "trigger_reason": null,
    "auto_trigger": {
      "enabled": true,
      "condition": "failure_rate > 10% in 15min",
      "cooldown_minutes": 60
    }
  },
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "history": [
    {
      "action": "enabled",
      "scope": "tenant",
      "tenant_id": "pilot_1",
      "actor": "operator",
      "timestamp": "ISO8601"
    }
  ]
}
```

### Feature Flag Definitions

```json
{
  "features": [
    {
      "key": "channel_manager.enabled",
      "description": "Master switch for channel manager",
      "default": false,
      "dependencies": []
    },
    {
      "key": "channel_manager.reservation_pull",
      "description": "Pull reservations from OTAs",
      "default": false,
      "dependencies": ["channel_manager.enabled"]
    },
    {
      "key": "channel_manager.auto_import",
      "description": "Auto-import pulled reservations to PMS",
      "default": false,
      "dependencies": ["channel_manager.reservation_pull"]
    },
    {
      "key": "channel_manager.ari_push",
      "description": "Push availability/rates/inventory to OTAs",
      "default": false,
      "dependencies": ["channel_manager.enabled"]
    },
    {
      "key": "controlplane.live_tracking",
      "description": "Real-time failure tracking in control plane",
      "default": false,
      "dependencies": []
    },
    {
      "key": "security.strict_tenant_mode",
      "description": "Enforce tenant isolation on all queries",
      "default": false,
      "dependencies": []
    },
    {
      "key": "folio.immutable_ledger",
      "description": "Use append-only folio ledger",
      "default": false,
      "dependencies": []
    },
    {
      "key": "night_audit.v2_hardened",
      "description": "Use hardened night audit engine",
      "default": true,
      "dependencies": []
    }
  ]
}
```

## 9.4 APIs

```
GET  /api/ops/features
     → List all feature flags with current state

GET  /api/ops/features/{feature}
     → Get single feature flag detail

POST /api/ops/features/{feature}/enable
     → Body: { scope: "tenant", tenant_id: "xxx" }
     → Enable for specific tenant or globally

POST /api/ops/features/{feature}/disable
     → Body: { scope: "tenant", tenant_id: "xxx" }

POST /api/ops/features/{feature}/kill
     → EMERGENCY: immediately disable everywhere
     → Body: { reason: "string" }

GET  /api/ops/features/{feature}/check?tenant_id=xxx
     → Check if feature enabled for tenant
     → Response: { enabled: bool, reason: "global | tenant | killed" }
```

## 9.5 Pilot Rollout Plan

```
WEEK 1: INTERNAL PILOT
  Day 1-2: Deploy to internal test hotel (simulated)
    - Enable: channel_manager.enabled, channel_manager.reservation_pull
    - Disable: channel_manager.auto_import, channel_manager.ari_push
    - Monitor: control plane dashboard, error rates
  Day 3-5: Enable auto_import, monitor for 48 hours
    - Check: imported reservations match expected
    - Check: no duplicate bookings
    - Check: folio integrity
  Day 6-7: Enable ari_push, monitor for 48 hours
    - Check: OTA availability matches PMS
    - Check: rate limiter working
    - Check: reconciliation drift = 0

WEEK 2: SHADOW MODE (Real Hotel)
  Day 8-9: Connect real hotel credentials
    - Enable: reservation_pull only (read-only mode)
    - Compare: pulled reservations vs hotel's OTA admin panel
    - Verify: data mapping accuracy
  Day 10-12: Enable auto_import in shadow mode
    - Import creates bookings but marks them as "shadow" (not visible to hotel staff)
    - Compare: shadow bookings vs manually entered bookings
    - Measure: accuracy rate
  Day 13-14: Review shadow results with hotel
    - Decision: proceed to canary or fix issues

WEEK 3: CANARY (10% TRAFFIC)
  Day 15-17: Enable features for real
    - percentage_rollout: 10% of new reservations auto-imported
    - 90% still manual
    - Monitor: error rate, hotel feedback
  Day 18-19: Ramp to 50%
  Day 20-21: Ramp to 100%
    - Full auto-import + ARI push for pilot hotel

WEEK 4: MULTI-HOTEL ROLLOUT
  Day 22-24: Onboard 2-3 additional hotels
  Day 25-28: Monitor, fix, stabilize
  Day 29-30: Go/no-go decision for general availability
```

## 9.6 Kill Switch Flow

```
AUTO-KILL TRIGGER:
1. Alert engine detects: failure_rate > 10% for feature X in 15 minutes
2. AlertingEngine calls FeatureGateService.kill(feature_X)
3. feature_gates.status → killed, kill_switch.active = true
4. All subsequent is_enabled(feature_X, any_tenant) → false
5. Alert sent to operator: "KILL SWITCH ACTIVATED: {feature_X}"
6. Operator investigates, fixes root cause
7. Operator manually restores: POST /api/ops/features/X/enable

MANUAL KILL:
1. Operator calls POST /api/ops/features/X/kill { reason: "..." }
2. Immediate disable. < 1 second propagation.
3. In-flight operations complete, new ones blocked.
4. No data loss (outbox events queued, processed when re-enabled)
```

## 9.7 Rollback Flow

```
ROLLBACK LEVEL 1: Feature disable
  - Disable specific feature flag
  - System continues with feature off
  - No deployment needed
  - Time: < 5 seconds

ROLLBACK LEVEL 2: Config rollback
  - Revert environment variables to previous values
  - Restart services
  - Time: < 5 minutes

ROLLBACK LEVEL 3: Code rollback
  - Deploy previous Docker image tag
  - Rolling update (zero downtime)
  - Time: < 15 minutes

ROLLBACK LEVEL 4: Data rollback
  - Restore MongoDB from point-in-time backup
  - LAST RESORT — data loss possible for recent operations
  - Time: 30-60 minutes
```

## 9.8 Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Kill switch activation count | 0 in production | Any activation |
| Feature enablement time | < 5 seconds | > 30 seconds |
| Rollback time (Level 1) | < 5 seconds | > 30 seconds |
| Pilot hotel satisfaction | > 90% | < 75% |
| Shadow mode accuracy | > 99% | < 95% |

---

# 10. LEARNING LOOP SYSTEM

## 10.1 Problem Definition

No closed-loop learning system:
- Incidents happen but root causes are not formally tracked
- Same incidents recur because prevention measures are informal
- No auto-tagging of failure patterns
- No recurrence detection
- No "never again" enforcement mechanism

## 10.2 Target Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  LEARNING LOOP ENGINE                        │
│                                                              │
│  incident → classify → RCA → fix → prevent → verify         │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  IncidentClassifier                                 │     │
│  │  - auto_classify(failure) → category + subcategory  │     │
│  │  - auto_tag(failure) → [tags]                       │     │
│  │  - detect_recurrence(incident) → previous_ids       │     │
│  └──────────────┬─────────────────────────────────────┘     │
│                 │                                            │
│  ┌──────────────▼─────────────────────────────────────┐     │
│  │  RCAEngine                                          │     │
│  │  - create_rca(incident_id) → RCA document           │     │
│  │  - track_fix(rca_id, fix_details)                   │     │
│  │  - create_never_again_rule(rca_id, rule)            │     │
│  │  - verify_prevention(rule_id) → bool                │     │
│  └──────────────┬─────────────────────────────────────┘     │
│                 │                                            │
│  ┌──────────────▼─────────────────────────────────────┐     │
│  │  NeverAgainEnforcer                                 │     │
│  │  - check_rules() → violations                       │     │
│  │  - runs as part of deployment gate                   │     │
│  │  - blocks deploy if "never again" rule violated      │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

## 10.3 Data Model

### Extended Incident Schema (extends existing `incidents` collection)

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "title": "Exely reservation pull timeout spike",
  "description": "50% of Exely reservation pulls timed out between 14:00-14:30",
  "severity": "P1 | P2 | P3 | P4",
  "status": "open | acknowledged | mitigating | resolved | postmortem | closed",

  "classification": {
    "category": "provider | infrastructure | data | security | human_error | code_bug",
    "subcategory": "timeout | auth_failure | data_corruption | resource_exhaustion | config_error | race_condition",
    "auto_classified": true,
    "confidence": 0.85,
    "tags": ["exely", "timeout", "reservation_pull", "provider_degradation"],
    "auto_tagged": true
  },

  "timeline": [
    {"action": "created", "actor": "auto_detect", "timestamp": "...", "note": "..."},
    {"action": "acknowledged", "actor": "ops_team", "timestamp": "..."},
    {"action": "mitigating", "actor": "ops_team", "timestamp": "...", "note": "Increased pull timeout to 60s"},
    {"action": "resolved", "actor": "ops_team", "timestamp": "...", "note": "Exely API recovered"},
    {"action": "postmortem_started", "actor": "eng_lead", "timestamp": "..."}
  ],

  "metrics": {
    "detection_time_seconds": 120,
    "acknowledgement_time_seconds": 300,
    "mitigation_time_seconds": 600,
    "resolution_time_seconds": 1800,
    "total_duration_seconds": 1800,
    "affected_tenants": 5,
    "affected_reservations": 23,
    "revenue_impact_estimate": 0,
    "data_loss": false
  },

  "root_cause_analysis": {
    "id": "uuid",
    "status": "pending | in_progress | completed",
    "summary": "Exely API experienced degradation due to their DB maintenance window. Our 30s timeout was too aggressive.",
    "contributing_factors": [
      "Exely unannounced maintenance (external)",
      "Our timeout of 30s too short for degraded conditions (internal)",
      "No circuit breaker to prevent cascade (internal)",
      "Alert threshold too high — detected at 50% failure, should be 20% (internal)"
    ],
    "root_cause_type": "external_dependency | internal_bug | configuration | process_gap",
    "five_whys": [
      "Why did pulls fail? → Exely API slow (>30s response)",
      "Why did we fail instead of retry? → Timeout was 30s, no dynamic adjustment",
      "Why no circuit breaker? → Not implemented for reservation pull path",
      "Why late detection? → Alert threshold was 50%, should be lower",
      "Why no pre-notification? → No integration with Exely status page"
    ],
    "fix_applied": "Increased timeout to 60s, added circuit breaker with 5-failure trip",
    "fix_pr_url": "https://github.com/syroce/pms/pull/245",
    "fix_deployed_at": "ISO8601",
    "completed_at": "ISO8601",
    "completed_by": "eng_lead"
  },

  "recurrence": {
    "is_recurrence": false,
    "previous_incident_ids": [],
    "recurrence_count": 0,
    "pattern_signature": "sha256(category:subcategory:provider:affected_service)",
    "last_occurrence": null
  },

  "never_again_rules": [
    {
      "id": "uuid",
      "rule_type": "circuit_breaker | alert_threshold | test_case | monitoring | process | config",
      "description": "Add circuit breaker to all provider connectors",
      "implementation": "Implement circuit breaker pattern in connector base class",
      "verification": {
        "type": "test_exists",
        "test_path": "tests/resilience/test_provider_circuit_breaker.py",
        "test_name": "test_circuit_breaker_trips_after_5_failures"
      },
      "status": "pending | implemented | verified | enforced",
      "assigned_to": "backend_team",
      "due_date": "ISO8601",
      "created_at": "ISO8601",
      "verified_at": "ISO8601 | null"
    },
    {
      "id": "uuid",
      "rule_type": "alert_threshold",
      "description": "Lower provider failure alert threshold from 50% to 20%",
      "implementation": "Update DEFAULT_THRESHOLDS in controlplane/alerting.py",
      "verification": {
        "type": "config_check",
        "check": "alerting.PROVIDER_AUTH_FAILURE.count <= 2"
      },
      "status": "implemented",
      "verified_at": "ISO8601"
    }
  ],

  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### Auto-Classification Rules

```python
CLASSIFICATION_RULES = [
    # Provider issues
    {"keywords": ["exely", "hotelrunner", "provider", "503", "502", "ota"],
     "category": "provider", "subcategory": "auto_detect"},
    {"keywords": ["timeout", "timed out", "connection refused"],
     "category": "provider" if provider_in_context else "infrastructure",
     "subcategory": "timeout"},

    # Infrastructure
    {"keywords": ["memory", "oom", "disk", "cpu", "resource"],
     "category": "infrastructure", "subcategory": "resource_exhaustion"},
    {"keywords": ["mongodb", "redis", "connection pool", "replica"],
     "category": "infrastructure", "subcategory": "database"},

    # Data
    {"keywords": ["mapping error", "validation", "schema", "corrupt"],
     "category": "data", "subcategory": "data_corruption"},
    {"keywords": ["duplicate", "conflict", "idempotency"],
     "category": "data", "subcategory": "duplicate"},

    # Security
    {"keywords": ["unauthorized", "forbidden", "token", "credential", "breach"],
     "category": "security", "subcategory": "auto_detect"},

    # Code
    {"keywords": ["null pointer", "attribute error", "type error", "unhandled"],
     "category": "code_bug", "subcategory": "unhandled_exception"},
]
```

### Recurrence Detection

```python
async def detect_recurrence(incident: dict) -> dict:
    """Check if this incident matches a previous pattern."""
    signature = compute_pattern_signature(incident)

    # Find previous incidents with same signature
    previous = await db.incidents.find(
        {
            "recurrence.pattern_signature": signature,
            "id": {"$ne": incident["id"]},
            "status": {"$in": ["resolved", "postmortem", "closed"]},
        },
        {"_id": 0, "id": 1, "title": 1, "created_at": 1, "never_again_rules": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    if previous:
        # Check if "never again" rules were supposed to prevent this
        violated_rules = []
        for prev in previous:
            for rule in prev.get("never_again_rules", []):
                if rule["status"] in ("implemented", "verified", "enforced"):
                    violated_rules.append({
                        "rule_id": rule["id"],
                        "description": rule["description"],
                        "from_incident": prev["id"],
                    })

        return {
            "is_recurrence": True,
            "previous_incident_ids": [p["id"] for p in previous],
            "recurrence_count": len(previous),
            "violated_never_again_rules": violated_rules,
            "severity_escalation": True if violated_rules else False,
        }

    return {"is_recurrence": False}
```

## 10.4 APIs

```
POST /api/ops/incidents
     → Create incident (auto-classifies)
     → Body: { title, description, severity, affected_service }
     → Response: { incident_id, classification, recurrence }

PUT  /api/ops/incidents/{id}/rca
     → Add/update root cause analysis
     → Body: { summary, contributing_factors, five_whys, fix_applied }

POST /api/ops/incidents/{id}/never-again
     → Add "never again" rule
     → Body: { rule_type, description, implementation, verification, due_date }

GET  /api/ops/incidents/{id}/recurrence
     → Check recurrence and violated rules

POST /api/ops/incidents/{id}/verify-prevention
     → Verify all "never again" rules are implemented
     → Response: { all_verified: bool, pending_rules: [...] }

GET  /api/ops/learning/dashboard
     → Learning metrics: MTTR, recurrence rate, rule compliance
     → Response: {
         mttr_p50: 1800,
         mttr_p95: 7200,
         recurrence_rate: 5.0,
         never_again_rules_total: 15,
         never_again_rules_verified: 12,
         incidents_30d: 8,
         p1_incidents_30d: 1,
         top_categories: [...]
       }

GET  /api/ops/learning/patterns
     → Common failure patterns and frequencies
     → Response: { patterns: [{ signature, count, last_seen, incidents }] }
```

## 10.5 "Never Again" Enforcement in Deployment Gate

```python
async def check_never_again_rules():
    """Called by deployment gate before production deploy."""
    rules = await db.incidents.aggregate([
        {"$unwind": "$never_again_rules"},
        {"$match": {"never_again_rules.status": {"$in": ["pending", "implemented"]}}},
        {"$project": {
            "rule": "$never_again_rules",
            "incident_id": "$id",
            "incident_title": "$title"
        }}
    ]).to_list(100)

    blockers = []
    for r in rules:
        rule = r["rule"]
        if rule["status"] == "pending" and rule.get("due_date", "") < now_iso():
            blockers.append({
                "type": "overdue_never_again_rule",
                "rule": rule["description"],
                "from_incident": r["incident_title"],
                "due_date": rule["due_date"],
            })

    return {
        "rules_checked": len(rules),
        "blockers": blockers,
        "deploy_allowed": len(blockers) == 0,
    }
```

## 10.6 Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Auto-classification wrong | Incident misrouted | Operators can override classification |
| Recurrence detection false positive | Alert fatigue | Require >= 2 matching keywords in signature |
| "Never again" rule blocks deploy for unrelated issue | Deploy blocked | Override mechanism with super_admin approval + audit log |

## 10.7 Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Mean Time to Detect (MTTD) | < 5 min | > 15 min |
| Mean Time to Acknowledge (MTTA) | < 15 min | > 30 min |
| Mean Time to Resolve (MTTR) | < 2 hours | > 4 hours |
| Recurrence rate (30d rolling) | < 5% | > 15% |
| Never-again rule compliance | > 90% verified | < 80% |
| Postmortem completion rate | 100% for P1/P2 | < 100% |

---

# 30-DAY BATTLE-READINESS ROADMAP

## Week 1: FOUNDATIONS (Day 1-7)

### MUST DO (Blocking Go-Live)

| Day | Task | Owner | Deliverable | Verification |
|-----|------|-------|-------------|--------------|
| 1 | Wire FailureTracker into import_bridge_service | Backend | cp_failures populated on import errors | Run import with bad data → failure in cp_failures |
| 1 | Wire FailureTracker into outbox_worker | Backend | cp_failures populated on dispatch errors | Mock provider 503 → failure recorded |
| 2 | Wire FailureTracker into ARI push engine | Backend | ARI push failures tracked | Push to offline provider → failure recorded |
| 2 | Implement Event Timeline collection + writer | Backend | event_timeline collection, TimelineWriter class | Import reservation → 5+ timeline events created |
| 3 | Implement Timeline API endpoints | Backend | /api/ops/timeline/* endpoints | GET timeline by entity_id returns ordered events |
| 3 | Implement Feature Gate system | Backend | feature_gates collection + API | Toggle feature on/off via API |
| 4 | Implement Dashboard Aggregator + Snapshot Worker | Backend | /api/ops/dashboard endpoint | Health score computed, snapshot stored |
| 4 | Run crypto migration (SEC-002) | DevOps | CRYPTO_V2_ENABLED=true | All credentials re-encrypted with V2 |
| 5 | Enable STRICT_TENANT_MODE in staging | DevOps | Tenant isolation enforced | Cross-tenant query returns empty |
| 5 | Implement Kill Switch system | Backend | Auto-kill on failure_rate > threshold | Simulate high failure → feature auto-killed |
| 6-7 | Integration testing: control plane + timeline + features | QA | All new endpoints tested | 30+ new integration tests pass |

### SHOULD DO (Important but not blocking)

| Task | Deliverable |
|------|-------------|
| Fix pre-existing lint errors (frontdesk_router.py, misc_router.py) | Clean lint |
| Protect /api/ops/* with admin role guard | Auth on ops endpoints |
| Config validation endpoint (/api/ops/infra/validate-config) | Config checker |

---

## Week 2: HARDENING (Day 8-14)

### MUST DO

| Day | Task | Owner | Deliverable | Verification |
|-----|------|-------|-------------|--------------|
| 8 | Implement immutable folio_ledger collection + service | Backend | FolioLedgerService with append-only writes | Post charge → entry in folio_ledger, original unchanged |
| 8 | Implement folio reconciliation engine | Backend | Nightly reconciliation, mismatch detection | Introduce mismatch → reconciliation catches it |
| 9 | Implement key rotation data model + API | Backend | crypto_key_registry collection, rotation endpoints | Generate key, activate, start rotation |
| 9 | Implement ReEncryptionWorker | Backend | Background re-encryption with progress tracking | Start rotation → progress visible via API |
| 10 | Battle tests: Split reservation, No-show | Backend | test_split_reservation.py, test_noshow.py | 10+ battle test scenarios pass |
| 11 | Battle tests: Room change, Overbooking, Cancellation edges | Backend | test_room_change.py, test_overbooking.py, test_cancellation.py | 15+ battle test scenarios pass |
| 12 | Implement IncidentClassifier + auto-tagging | Backend | Auto-classification on incident creation | Create incident → auto-classified + tagged |
| 13 | Implement recurrence detection | Backend | Pattern matching across historical incidents | Create similar incident → recurrence detected |
| 14 | Integration testing: folio ledger + battle tests + learning loop | QA | All week 2 features tested | 50+ new tests pass |

### SHOULD DO

| Task | Deliverable |
|------|-------------|
| Deployment gate endpoint | /api/ops/infra/deployment-gate |
| Never-again rule enforcement in gate | Deploy blocked if overdue rules |
| Breach simulation: tenant boundary test | Basic breach sim |

---

## Week 3: STRESS + EXPOSURE (Day 15-21)

### MUST DO

| Day | Task | Owner | Deliverable | Verification |
|-----|------|-------|-------------|--------------|
| 15 | Run Reservation Burst test (STRESS-001) | QA/Infra | 15,000 reservations, < 1% error | All assertions pass |
| 15 | Run ARI Storm test (STRESS-002) | QA/Infra | 120,000 ARI updates, 0 drift | Reconciliation clean |
| 16 | Run Provider Downtime sim (STRESS-003) | QA/Infra | 30min downtime, 0 data loss | All events recovered |
| 16 | Fix issues found in stress tests | Backend | Bug fixes | Re-run failed tests → pass |
| 17 | Connect pilot hotel (shadow mode) | Ops | Real credentials, read-only | Reservation pull matches hotel's OTA panel |
| 18-19 | Shadow mode monitoring (48h) | Ops | Shadow import accuracy report | > 99% match |
| 20 | Enable canary (10% auto-import) | Ops | Real imports for pilot hotel | Imported bookings correct |
| 21 | Ramp canary to 50% | Ops | Increased traffic | Error rate < 1% |

### SHOULD DO

| Task | Deliverable |
|------|-------------|
| Full breach simulation suite | All 6 scenarios pass |
| Terraform modules for production | IaC for core infra |
| Environment parity check automation | Staging == production validation |

---

## Week 4: PRODUCTION + STABILIZE (Day 22-30)

### MUST DO

| Day | Task | Owner | Deliverable | Verification |
|-----|------|-------|-------------|--------------|
| 22 | Ramp pilot hotel to 100% | Ops | Full auto-import + ARI push | Error rate < 0.5%, drift = 0 |
| 22 | Enable controlplane.live_tracking | DevOps | Real-time failure tracking | Dashboard shows live data |
| 23 | Execute secrets management rollout (SEC-001) | DevOps | Secrets in AWS Secrets Manager | Credentials loaded from AWS SM |
| 24-25 | Onboard 2 additional hotels | Ops | 3 hotels live total | All 3 hotels running smoothly |
| 26-27 | 48-hour soak test (all 3 hotels, real traffic) | QA/Ops | Soak report | Health score > 90 for 48h |
| 28 | Fix any soak test issues | Backend | Bug fixes | Re-run tests → pass |
| 29 | Production hardening review | Team | Checklist completed | All P0 items green |
| 30 | Go/No-Go decision | Leadership | Decision document | All criteria met |

### SHOULD DO

| Task | Deliverable |
|------|-------------|
| Frontend control plane dashboard | React dashboard for ops team |
| Grafana dashboards from cp_health_snapshots | Visual monitoring |
| Game Day exercise (from CHAOS_TESTING_MASTER_PLAN.md) | Half-day operational exercise |

---

## Go/No-Go Criteria (Day 30)

| Criterion | Requirement | Status |
|-----------|-------------|--------|
| Health score | > 90 for 48 hours | ☐ |
| Open critical failures | 0 | ☐ |
| Overbooking incidents | 0 | ☐ |
| Folio reconciliation mismatches | 0 | ☐ |
| Stress test pass rate | 100% | ☐ |
| Breach simulation pass rate | 100% | ☐ |
| Kill switch tested | Yes | ☐ |
| Rollback tested | Yes (Level 1 and 3) | ☐ |
| Pilot hotel approval | Yes | ☐ |
| Alert webhook configured | Yes (Slack) | ☐ |
| STRICT_TENANT_MODE | Enabled | ☐ |
| CRYPTO_V2_ENABLED | Enabled | ☐ |
| Secrets in AWS SM | Yes | ☐ |
| Never-again rules | 0 overdue | ☐ |
| MTTR for pilot incidents | < 2 hours | ☐ |
| Documentation complete | Go-Live Playbook updated | ☐ |

---

## Summary: What the Final System Must Be

| Property | How We Achieve It |
|----------|------------------|
| **Observable** | Unified dashboard with health score, event timeline for every entity, real-time SSE stream |
| **Debuggable** | Correlation ID tracing, timeline gap detection, external ID lookup, 5-second root cause path |
| **Recoverable** | Idempotent retry engine, kill switches, 4-level rollback, outbox guaranteed delivery |
| **Auditable** | Immutable folio ledger, event timeline, secret access audit, breach simulation reports |
| **Self-Improving** | Learning loop: incident → classification → RCA → never-again rule → deployment gate enforcement |

---

*This system will run live hotels in 30 days. Every design in this document is implementable with the existing codebase. No hand-waving. No concepts. Just execution.*
