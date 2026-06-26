"""
Celery Configuration for Background Jobs
Handles long-running tasks, periodic jobs, and async processing
"""

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

from redis_ssl import celery_ssl_conf, normalize_redis_url_for_redis_py

load_dotenv()

# Redis as message broker
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'hotel_pms',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# ── Managed Redis TLS (rediss://) ───────────────────────────────────
# DigitalOcean Managed Caching / Valkey enforces TLS. kombu only opens an SSL
# broker connection when broker_use_ssl is set, and celery's redis result backend
# hard-refuses a rediss:// URL unless redis_backend_use_ssl carries ssl_cert_reqs
# ("A rediss:// URL must have parameter ssl_cert_reqs"). Configure both. Then
# normalize REDIS_URL in this worker process so the redis-py clients pulled in by
# task modules (cache, event bus) also connect over TLS without failing cert
# verification against the managed CA. No-op for plain redis:// (Replit/local).
_redis_ssl = celery_ssl_conf(REDIS_URL)
if _redis_ssl:
    celery_app.conf.broker_use_ssl = _redis_ssl
    celery_app.conf.redis_backend_use_ssl = _redis_ssl
    os.environ['REDIS_URL'] = normalize_redis_url_for_redis_py(REDIS_URL)

# ── Logging hardening (secret/PII sanitizer + quiet httpx request URLs) ──
# Celery hijacks the root logger and installs its own handlers AFTER import, so
# we (a) quiet httpx/httpcore immediately at import — this stops the
# "HTTP Request: GET <url-with-?token=...>" INFO leak in worker logs right away
# (scheduled connector calls such as HotelRunner pulls run in this process) —
# and (b) re-attach the sanitizer via Celery's logging signals once its own
# handlers exist.
try:
    from celery.signals import after_setup_logger, after_setup_task_logger

    from security.log_sanitizer import harden_logging

    harden_logging()

    @after_setup_logger.connect
    def _harden_after_setup_logger(logger=None, **kwargs):
        harden_logging()

    @after_setup_task_logger.connect
    def _harden_after_setup_task_logger(logger=None, **kwargs):
        harden_logging()
except Exception as _celery_log_err:  # pragma: no cover - defensive
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Celery log hardening skipped: %s", _celery_log_err
    )

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3000,  # 50 minutes warning

    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # Result backend
    result_expires=86400,  # 24 hours
    result_backend_transport_options={
        'master_name': 'mymaster'
    },

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    # Beat schedule for periodic tasks
    beat_schedule={
        # Night audit dispatcher (Task #362) — runs every minute and enqueues a
        # per-tenant hardened audit when each tenant's LOCAL configured time
        # arrives (DST-aware). Replaces the old fixed 02:00 UTC global cron that
        # closed every hotel's financial day at the same instant regardless of
        # timezone. An atomic per-local-day claim makes it safe even if multiple
        # beat processes run (autoscale) — at most one dispatch per tenant/day.
        'night-audit-dispatch': {
            'task': 'celery_tasks.night_audit_dispatch_task',
            'schedule': crontab(minute='*'),
        },

        # Folio close event (e-Fatura readiness) — off-hot-path outbox sweep that
        # emits the reference-based folio.closed.v1 SXI event for newly-closed
        # folios. No-op unless PUBLIC_APP_URL + FOLIO_EVENT_EMIT_SINCE are set and
        # a subscriber tenant has a partner supporting FOLIO_CLOSE OUTBOUND.
        'folio-closed-event-sweep': {
            'task': 'celery_tasks.folio_closed_event_sweep_task',
            'schedule': crontab(minute='*/5'),
        },

        # KBS dispatcher (Task #570) — PMS-içi otomatik polis konaklama bildirimi.
        # Her dakika bekleyen KBS kuyruğunu claim eder, KBS uç noktasına gönderir
        # ve complete/fail eder. Fail-closed: KBS_API_URL/KBS_API_TOKEN yoksa
        # (ve KBS_TEST_MODE kapalıysa) no-op döner + operatörü throttled uyarır;
        # sahte başarı YAZILMAZ. Harici masaüstü ajan/bot artık gerekmez.
        'kbs-dispatch': {
            'task': 'celery_tasks.kbs_dispatch_task',
            'schedule': crontab(minute='*'),
        },

        # KBS gece güvenlik taraması (Task #570) — night-audit ile aynı kalıp:
        # her dakika tick'ler, her kiracının YEREL saatiyle 00:00'ında kapanan
        # günün gönderilmemiş konaklamalarını yeniden enqueue eder (DST-aware,
        # atomik per-local-day claim). Gün içinde gözden kaçanları yakalar.
        'kbs-nightly-sweep-dispatch': {
            'task': 'celery_tasks.kbs_nightly_sweep_dispatch_task',
            'schedule': crontab(minute='*'),
        },

        # Contact Center Faz 2 (Task #648) — çağrı kaydı retention sweep.
        # Her gün 02:30'da süresi dolan (CC_RECORDING_RETENTION_DAYS) kayıtları
        # ayrı nesne deposundan siler ve recording_ref'i kaldırır. Fail-closed:
        # kayıt deposu yapılandırılmamışsa no-op.
        'cc-purge-expired-recordings': {
            'task': 'celery_tasks.purge_expired_call_recordings_task',
            'schedule': crontab(hour=2, minute=30),
        },

        # Data archival - runs weekly on Sunday at 3 AM
        'archive-old-data': {
            'task': 'celery_tasks.archive_old_data_task',
            'schedule': crontab(day_of_week=0, hour=3, minute=0),
        },

        # Clean old notifications - runs daily at 4 AM
        'clean-notifications': {
            'task': 'celery_tasks.clean_old_notifications_task',
            'schedule': crontab(hour=4, minute=0),
        },

        # Generate daily reports - runs at 1 AM
        'generate-daily-reports': {
            'task': 'celery_tasks.generate_daily_reports_task',
            'schedule': crontab(hour=1, minute=0),
        },

        # Check maintenance SLA - runs every hour
        'check-maintenance-sla': {
            'task': 'celery_tasks.check_maintenance_sla_task',
            'schedule': crontab(minute=0),  # Every hour at :00
        },

        # Update occupancy forecast - runs every 6 hours
        'update-occupancy-forecast': {
            'task': 'celery_tasks.update_occupancy_forecast_task',
            'schedule': crontab(minute=0, hour='*/6'),  # 0, 6, 12, 18
        },

        # Process pending e-faturas - runs every 30 minutes
        'process-efaturas': {
            'task': 'celery_tasks.process_pending_efaturas_task',
            'schedule': crontab(minute='*/30'),
        },

        # Cache warming - runs every 10 minutes
        'warm-cache': {
            'task': 'celery_tasks.warm_cache_task',
            'schedule': crontab(minute='*/10'),
        },

        # Database health check - runs every 5 minutes
        'db-health-check': {
            'task': 'celery_tasks.database_health_check_task',
            'schedule': crontab(minute='*/5'),
        },

        # HRv2 Shadow Automation — 6 saatte bir snapshot
        'hrv2-shadow-snapshot': {
            'task': 'celery_tasks.hrv2_shadow_snapshot_task',
            'schedule': crontab(minute=0, hour='*/6'),
        },

        # HRv2 Shadow Automation — Gunluk ozet (00:00 UTC)
        'hrv2-daily-summary': {
            'task': 'celery_tasks.hrv2_daily_summary_task',
            'schedule': crontab(hour=0, minute=0),
        },

        # HRv2 Shadow Automation — Retention cleanup (Pazar 05:00 UTC)
        'hrv2-retention-cleanup': {
            'task': 'celery_tasks.hrv2_retention_cleanup_task',
            'schedule': crontab(day_of_week=0, hour=5, minute=0),
        },

        # F8N Task #224 — Auto-resolve duplicate room-night locks (daily 03:30 UTC).
        # Touches only auto_safe / auto_safe_all_inactive groups; manual_required
        # groups are logged so monitoring can alert if they accumulate.
        # Retention (Task #237): the `rnl_auto_resolve_runs` history collection
        # is pruned inline at the end of each run (default 365 days, overridable
        # via `RNL_AUTO_RESOLVE_RUN_RETENTION_DAYS`). No separate beat entry.
        'rnl-duplicate-auto-resolve': {
            'task': 'celery_tasks.rnl_duplicate_auto_resolve_task',
            'schedule': crontab(hour=3, minute=30),
        },

        # F8N Task #234 — Heartbeat monitor for the daily RNL duplicate
        # auto-resolve job. Alerts when no successful run has happened in
        # ~36h (silent dead-scheduler failure mode that the outcome-based
        # Task #228 alert can't see). Runs hourly at :15.
        'rnl-duplicate-heartbeat-check': {
            'task': 'celery_tasks.rnl_duplicate_heartbeat_check_task',
            'schedule': crontab(minute=15),
        },

        # Task #242 — Alert ops by email when a duplicate-prevention unique-index
        # backstop stays deferred (safeguard OFF) past a grace window. Runs
        # hourly at :45; the task attempts the build (self-heal), tracks deferral
        # duration in Mongo, and emails ops via the shared alert dispatcher.
        'unique-backstop-deferral-check': {
            'task': 'celery_tasks.unique_backstop_deferral_check_task',
            'schedule': crontab(minute=45),
        },

        # Outbox terminal-state retention (Atlas Query Targeting 2026-06-17) —
        # daily off-peak janitor that deletes outbox_events rows in terminal
        # states (processed/failed/parked) older than OUTBOX_TERMINAL_RETENTION_
        # DAYS (default 14) in bounded batches. NEVER touches pending/retry/
        # processing. Prevents the unbounded terminal backlog that makes the
        # every-minute outbox monitoring count scan grow without bound.
        'outbox-terminal-retention-cleanup': {
            'task': 'celery_tasks.outbox_terminal_retention_task',
            'schedule': crontab(hour=4, minute=30),
        },

        # Revenue Autopilot dispatcher (Rota 1-A) — runs every minute and enqueues
        # each active tenant's deterministic optimization cycle when its LOCAL
        # configured time arrives (DST-aware, tenant_settings.timezone; default
        # 02:00 Europe/Istanbul). Replaces the old fixed 02:00 UTC global cron so
        # the pricing cycle runs during each hotel's own night regardless of
        # timezone. An atomic per-local-day claim keeps it safe even if multiple
        # beat processes run (autoscale) — at most one dispatch per tenant/day.
        # Enqueues on the dedicated `pricing` queue (isolated from the agency-
        # webhook Outbox/other workers). In full_auto mode the cycle emits per-
        # room_type/date RATE_UPDATED outbox events (idempotent); supervised/
        # advisory keep pending_approval.
        'revenue-autopilot-dispatch': {
            'task': 'celery_tasks.revenue_autopilot_dispatch_task',
            'schedule': crontab(minute='*'),
        },

        # Stress dead-PENDING outbox residue sweep (Plan A — Task #620) —
        # dedicated nightly beat (03:50 UTC, non-colliding slot) that sweeps the
        # stress tenant's no-consumer guest.checked_in/out.v1 PENDING backlog so
        # it cannot rebuild and re-trip the Atlas query-targeting alert. This is
        # DECOUPLED from the e2e-stress suite teardown (which only ran the
        # cleanup when the suite ran end-to-end). Fail-closed: deletes ONLY when
        # STRESS_OUTBOX_SWEEP_ENABLED=true AND E2E_STRESS_TENANT_ID is set AND
        # the tenant is not the pilot; otherwise a silent metric-only no-op
        # (so dev / unconfigured prod behaviour is unchanged). 24h age guard.
        'stress-outbox-residue-sweep': {
            'task': 'celery_tasks.stress_outbox_residue_sweep_task',
            'schedule': crontab(hour=3, minute=50),
        },
    }
)

# Import tasks directly (celery_tasks is a module, not a package)
try:
    import celery_tasks  # noqa: F401
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"celery_tasks import failed: {e}")

if __name__ == '__main__':
    celery_app.start()
