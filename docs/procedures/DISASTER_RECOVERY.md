# Disaster Recovery Plan — Syroce Hotel PMS

## Recovery Objectives
| Metric | Target | Notes |
|--------|--------|-------|
| RPO (Recovery Point Objective) | 24 hours | Daily automated backups |
| RTO (Recovery Time Objective) | 4 hours | Full service restoration |

## Backup Strategy

### Automated Backups
- **Schedule**: Daily at 02:00 UTC via Celery beat
- **Method**: `mongodump --gzip` to configured backup path
- **Retention**: 30 days (configurable via `BACKUP_RETENTION_DAYS`)
- **Verification**: Weekly automated restore tests

### Critical Collections (Priority 1)
Must be restored first:
- `users`, `tenants` — Authentication & authorization
- `bookings`, `rooms`, `guests` — Core PMS data
- `folios`, `invoices`, `payments` — Financial records
- `companies`, `rates` — Business configuration
- `channel_connections` — OTA integrations
- `audit_logs` — Compliance trail

### Secondary Collections (Priority 2)
- `event_bus_log`, `messaging_delivery_logs`
- `observability_traces`, `alert_history`
- `pipeline_runs`, `analytics_export_history`

## Recovery Procedures

### Scenario 1: Database Corruption
1. Stop all backend services
2. Identify last good backup: `GET /api/infra/backup/history`
3. Restore: `mongorestore --gzip --uri=$MONGO_URL --db=$DB_NAME <backup_path>`
4. Verify data integrity
5. Restart services
6. Run `POST /api/infra/backup/trigger` for fresh snapshot

### Scenario 2: Redis Failure
1. System auto-falls back to in-memory event bus
2. Check status: `GET /api/infra/redis/health`
3. Fix/replace Redis instance
4. Backend auto-reconnects via `reconnect_with_backoff`
5. Verify: WebSocket, Pub/Sub, Locks, Cache

### Scenario 3: Complete Infrastructure Failure
1. Provision new infrastructure
2. Deploy containers from latest images
3. Restore MongoDB from backup
4. Configure environment variables
5. Start services in order: MongoDB -> Redis -> Backend -> Worker -> Frontend
6. Verify all health endpoints
7. Re-seed demo data if needed

### Scenario 4: Single Instance Failure
- Multi-instance setup: Load balancer routes to healthy instances
- Worker failure: Other workers pick up queued tasks
- Frontend failure: Other frontend replicas serve traffic

## Monitoring & Alerting
- Backup status: `GET /api/infra/backup/status`
- Redis health: `GET /api/infra/redis/health`
- Instance health: `GET /api/infra/scaling/instances`
- Worker health: `GET /api/infra/workers/summary`

## Contact & Escalation
- **L1**: Check dashboards, restart services
- **L2**: Database restore, infrastructure changes
- **L3**: Full DR execution, data recovery
