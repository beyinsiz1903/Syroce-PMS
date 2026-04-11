# Control Plane Rollout Plan

## Prerequisites
- [x] SEC-001 (Secrets Manager) deployed
- [x] SEC-002 (AES-256-GCM Encryption) deployed
- [x] MongoDB indexes created (automatic on startup)

## Phase 1: Deploy (Zero Downtime)

### Step 1: Deploy the Control Plane Module
The control plane is additive — it doesn't modify existing behavior.

1. Deploy the new `controlplane/` module
2. The startup validator runs automatically and creates indexes
3. Verify startup logs show: `Control plane validation: pass`

### Step 2: Verify API Endpoints
```bash
# System overview
curl /api/ops/overview

# Should return zero failures initially
curl /api/ops/failures

# Verify runbooks loaded
curl /api/ops/runbooks
```

### Step 3: Enable Alerting (Optional)
```bash
# Add webhook URL to .env for Slack/webhook notifications
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## Phase 2: Integrate Failure Tracking

### Step 1: Wire Import Pipeline
Add failure tracking to the import bridge service:
```python
from controlplane import get_failure_tracker

tracker = get_failure_tracker()
await tracker.record(
    tenant_id=tenant_id, provider=provider,
    operation_type="reservation_import",
    error_code="IMPORT_FAILED",
    error_message=str(error),
    context={"import_id": import_id},
)
```

### Step 2: Wire Outbox Worker
Add failure tracking to the outbox worker on dispatch failures.

### Step 3: Wire ARI Push
Track ARI push failures through the outbox failure path.

### Step 4: Wire Secret Access
Integrate `SecretAccessControl.check_and_log()` into credential vault operations.

## Phase 3: Operational Readiness

### Step 1: Configure Alert Thresholds
Adjust thresholds in `controlplane/alerting.py` based on production traffic patterns.

### Step 2: Train Operators
Distribute runbooks and train operators on:
- Reading the overview dashboard
- Using dry-run retry mode
- When to escalate vs. ignore

### Step 3: Monitor and Iterate
- Watch failure patterns for the first 2 weeks
- Adjust classification keywords if needed
- Add new runbooks for newly discovered failure modes

## Rollback Plan
The control plane is completely additive. To rollback:
1. Remove the router entry from `bootstrap/router_registry.py`
2. Remove the startup validation from `startup.py`
3. The `controlplane/` module can remain — it has no side effects when not mounted

## Security Considerations
- All failure events are sanitized — no plaintext secrets in context or error messages
- Secret access audit never stores secret values
- Cross-tenant access is blocked at query level
- The `/api/ops/*` endpoints should be protected by admin/operator role
