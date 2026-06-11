"""
Celery Tasks for Background Processing
All long-running and periodic tasks
"""

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from celery_app import celery_app

try:
    from integrations.booking import BookingAPIClient, BookingCredentialManager, BookingIntegrationLogger, BookingReservationMapper
    from models.enums import ChannelType
except ImportError as e:
    logger = __import__('logging').getLogger(__name__)
    logger.warning(f"Optional booking integration not available: {e}")
    BookingAPIClient = None
    BookingCredentialManager = None
    BookingIntegrationLogger = None
    BookingReservationMapper = None
    ChannelType = None

logger = logging.getLogger(__name__)

# MongoDB connection for tasks
def get_db():
    """Get database connection"""
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name], client


# ============= ML TRAINING TASKS =============
# ML egitimi yalnizca 'ml' kuyrugunda (ml.txt kurulu worker) calisir.
# Agir ML yigini (sklearn/xgboost/numpy/pandas) bu modulun statik import
# grafigine girmesin diye `ml_service` TEMBEL + DINAMIK olarak yuklenir;
# boylece API imaji ve varsayilan worker imaji bu bagimliliklari tasimaz.

@celery_app.task(name='celery_tasks.ml_training_task', bind=True)
def ml_training_task(self, model: str = 'all', params: dict[str, Any] | None = None):
    """ML model(ler)ini ML worker surecinde egitir.

    model: 'rms' | 'persona' | 'predictive_maintenance' | 'hk_scheduler' | 'all'
    params: modele ozel parametreler (historical_days, num_guests, ...).
    """
    import importlib
    ml_service = importlib.import_module('ml_service')
    return ml_service.run_training(model, params or {})


# ============= NIGHT AUDIT TASKS =============
# ============= BOOKING.COM INTEGRATION TASKS =============

@celery_app.task(name='celery_tasks.booking_push_task')
def booking_push_task(tenant_id: str, payload: dict[str, Any]):
    """Push ARI updates to Booking.com"""
    return asyncio.run(_booking_push_async(tenant_id, payload))

async def _booking_push_async(tenant_id: str, payload: dict[str, Any]):
    db, client = get_db()
    try:
        credentials = await BookingCredentialManager.get_credentials(tenant_id)
        if not credentials:
            raise ValueError("Booking credentials missing")

        api_client = BookingAPIClient(credentials)
        await BookingIntegrationLogger.log_event(
            tenant_id,
            'ari_push_attempt',
            payload,
            'processing',
            message='Sending ARI payload to Booking.com'
        )

        response = await api_client.push_ari(payload)

        await BookingIntegrationLogger.log_event(
            tenant_id,
            'ari_push',
            response,
            'success',
            message='Booking.com ARI push completed'
        )

        return {
            'success': True,
            'rooms_updated': len(payload.get('rooms', [])),
            'endpoint': response.get('endpoint')
        }
    except Exception as e:
        await BookingIntegrationLogger.log_event(
            tenant_id,
            'ari_push',
            payload,
            'failed',
            message=str(e)
        )
        return {'success': False, 'error': str(e)}
    finally:
        await client.close()

@celery_app.task(name='celery_tasks.booking_pull_task')
def booking_pull_task(tenant_id: str):
    """Pull reservations from Booking.com"""
    return asyncio.run(_booking_pull_async(tenant_id))

async def _booking_pull_async(tenant_id: str):
    db, client = get_db()
    try:
        credentials = await BookingCredentialManager.get_credentials(tenant_id)
        if not credentials:
            raise ValueError("Booking credentials missing")

        client_api = BookingAPIClient(credentials)
        response = await client_api.fetch_reservations()
        reservations = response.get('reservations', [])
        mapper = BookingReservationMapper(tenant_id)

        for reservation in reservations:
            ota_record = mapper.to_ota_record(reservation)
            await db.ota_reservations.update_one(
                {'tenant_id': tenant_id, 'channel_type': ChannelType.BOOKING_COM.value, 'channel_booking_id': ota_record['channel_booking_id']},
                {'$set': {
                    **ota_record,
                    'last_synced_at': datetime.now(UTC).isoformat()
                }},
                upsert=True
            )

            guest_id = await ensure_guest_record(db, mapper, reservation)
            room_id = await find_room_for_reservation(db, tenant_id, ota_record.get('room_type'))

            if guest_id and room_id:
                booking_payload = mapper.to_booking_payload(reservation, guest_id, room_id)
                from core.atomic_booking import BookingConflictError, assert_pending_assignment, create_booking_atomic
                try:
                    await create_booking_atomic(booking_payload)
                except BookingConflictError:
                    booking_payload["room_id"] = None
                    booking_payload["allocation_source"] = "pending_assignment"
                    assert_pending_assignment(booking_payload)
                    await db.bookings.insert_one(booking_payload)
                    booking_payload.pop("_id", None)
                await db.ota_reservations.update_one(
                    {'tenant_id': tenant_id, 'channel_booking_id': ota_record['channel_booking_id']},
                    {'$set': {
                        'status': 'imported',
                        'pms_booking_id': booking_payload['id'],
                        'processed_at': datetime.now(UTC).isoformat()
                    }}
                )

        await BookingIntegrationLogger.log_event(
            tenant_id,
            'reservation_pull',
            {'count': len(reservations), 'endpoint': response.get('endpoint')},
            'success',
            message='Booking.com reservations pulled'
        )

        return {'success': True, 'reservations': len(reservations)}
    except Exception as e:
        await BookingIntegrationLogger.log_event(
            tenant_id,
            'reservation_pull',
            {},
            'failed',
            message=str(e)
        )
        return {'success': False, 'error': str(e)}
    finally:
        await client.close()


async def ensure_guest_record(db, mapper: BookingReservationMapper, reservation: dict[str, Any]) -> str | None:
    query = {
        'tenant_id': mapper.tenant_id,
        'email': reservation.get('guest_email')
    }
    guest = await db.guests.find_one(query)
    if guest:
        return guest['id']

    payload = mapper.to_guest_payload(reservation)
    from security.search_normalize import apply_collection_normalized_fields
    apply_collection_normalized_fields(payload, collection="guests")
    await db.guests.insert_one(payload)
    return payload['id']


async def find_room_for_reservation(db, tenant_id: str, room_type: str | None) -> str | None:
    if not room_type:
        return None
    room = await db.rooms.find_one({
        'tenant_id': tenant_id,
        'room_type': room_type,
        'status': 'available'
    })
    return room['id'] if room else None


# ============= NIGHT AUDIT (Task #362) =============
# Per-tenant, local-time, hardened night audit driven by Celery.
#
# The legacy `night_audit_task` (a fixed 02:00 UTC global cron that posted
# simple, un-hardened room charges for every tenant at once) has been removed:
# it closed Tokyo's and London's financial day at the same instant and
# bypassed the hardened state machine. Audits are now triggered per tenant at
# each tenant's own configured LOCAL time by `night_audit_dispatch_task` (beat)
# and executed by `night_audit_for_tenant` (worker).


def _now_utc() -> datetime:
    """Current UTC time. Isolated in a helper so tests can pin the wall clock
    deterministically when exercising the local-time dispatch matching."""
    return datetime.now(UTC)


def _fresh_mongo():
    """Create a throwaway Motor client bound to the CURRENT event loop.

    Celery executes each task body via ``asyncio.run()``, which creates a fresh
    loop and closes it afterwards. A module-level Motor client (e.g.
    ``core.database.client``) binds to the first loop it touches and then raises
    ``RuntimeError: Event loop is closed`` on every later task. So night-audit
    tasks build a per-call client bound to the live loop — the same pattern the
    Booking.com / archival tasks already use via ``get_db()``.

    The connection string / DB name are resolved from ``core.database`` so the
    worker always reads/writes the exact same database as the rest of the app.
    """
    from core.database import db_name, mongo_url
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


@celery_app.task(name='celery_tasks.night_audit_dispatch_task')
def night_audit_dispatch_task():
    """Beat dispatcher (every minute): enqueue per-tenant audits at local time.

    Reads every enabled night-audit schedule, converts ``now`` into each
    tenant's local wall-clock with DST-aware zoneinfo, and when the local
    ``hour:minute`` matches the configured time, atomically claims the tenant
    for today's local day and enqueues ``night_audit_for_tenant``. The claim
    (``find_one_and_update`` on ``last_auto_run``) closes the read-then-write
    race, so a tenant is dispatched at most once per local day even across
    overlapping/duplicate beat ticks.
    """
    return asyncio.run(_night_audit_dispatch_async())


async def _night_audit_dispatch_async() -> dict[str, Any]:
    from domains.pms.night_audit.scheduler import utc_to_local

    client, db = _fresh_mongo()
    queued: list[str] = []
    scanned = 0
    try:
        now_utc = _now_utc()
        schedules = await db.night_audit_schedules.find(
            {"enabled": True}, {"_id": 0}
        ).to_list(1000)

        for schedule in schedules:
            scanned += 1
            tenant_id = schedule.get("tenant_id")
            if not tenant_id:
                continue
            sched_hour = int(schedule.get("scheduled_hour", 0) or 0)
            sched_minute = int(schedule.get("scheduled_minute", 0) or 0)
            tz_name = schedule.get("timezone") or "UTC"

            local_now = utc_to_local(now_utc, tz_name)
            if local_now.hour != sched_hour or local_now.minute != sched_minute:
                continue

            # Atomic per-local-day claim. The tenant's local day starts at local
            # midnight; expressed as a UTC instant it gives an ISO-8601 string
            # that sorts lexicographically by time (same +00:00 suffix as the
            # values we write). A tenant whose `last_auto_run` predates this
            # boundary (or is unset) has not run today → we win the claim.
            local_day_start = local_now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            boundary = local_day_start.astimezone(UTC).isoformat()
            now_iso = now_utc.isoformat()

            claim = await db.night_audit_schedules.find_one_and_update(
                {
                    "tenant_id": tenant_id,
                    "enabled": True,
                    "$or": [
                        {"last_auto_run": {"$exists": False}},
                        {"last_auto_run": None},
                        {"last_auto_run": {"$lt": boundary}},
                    ],
                },
                {"$set": {
                    "last_auto_run": now_iso,
                    "last_auto_run_status": "dispatched",
                }},
            )
            if claim is None:
                # Already claimed for today's local day (race lost / re-tick).
                continue

            night_audit_for_tenant.delay(tenant_id)
            queued.append(tenant_id)
            logger.info(
                "Night audit dispatch: queued tenant=%s at local %02d:%02d (%s)",
                tenant_id, sched_hour, sched_minute, tz_name,
            )

        return {"success": True, "scanned": scanned, "queued": queued}
    except Exception as exc:
        logger.exception("Night audit dispatch error: %s", exc)
        return {"success": False, "error": str(exc), "scanned": scanned, "queued": queued}
    finally:
        client.close()


@celery_app.task(
    name='celery_tasks.night_audit_for_tenant',
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def night_audit_for_tenant(self, tenant_id: str):
    """Run the hardened night audit for a single tenant (Task #362).

    Executes ``core.night_audit_hardened.start_night_audit`` under
    ``tenant_context`` and records the outcome in ``night_audit_schedule_logs``
    and ``night_audit_schedules.last_auto_run``. The hardened engine's state
    machine and ``business_date`` dedup unique index remain the final
    idempotency safety net, so a Celery retry after an *unexpected* error
    (e.g. a transient DB blip) cannot double-post charges.
    """
    try:
        return asyncio.run(_night_audit_for_tenant_async(tenant_id))
    except Exception as exc:  # noqa: BLE001 — infra-level; engine dedup makes retry safe
        logger.exception("Night audit task crashed for tenant=%s: %s", tenant_id, exc)
        raise self.retry(exc=exc)


async def _night_audit_for_tenant_async(tenant_id: str) -> dict[str, Any]:
    import core.night_audit_hardened as engine
    from core.tenant_db import TenantAwareDBProxy, tenant_context

    client, raw_db = _fresh_mongo()
    proxy = TenantAwareDBProxy(raw_db)

    # The hardened engine captured `core.database.{client,db}` at import time;
    # under Celery those are bound to a now-dead loop. Point them at this
    # loop-fresh client for the duration of the run: engine transactions use
    # `engine.client`, all reads/writes use `engine.db`, and the (best-effort)
    # snapshot hook receives `db` explicitly. Celery's default prefork pool runs
    # one task per process at a time, so this process-global rebind is safe.
    saved_client, saved_db = engine.client, engine.db
    engine.client, engine.db = client, proxy
    try:
        settings = await raw_db.tenant_settings.find_one(
            {"tenant_id": tenant_id}, {"_id": 0, "business_date": 1}
        )
        bd = (settings or {}).get("business_date") or datetime.now(UTC).date().isoformat()

        with tenant_context(tenant_id):
            result = await engine.start_night_audit(
                tenant_id=tenant_id,
                business_date=bd,
                trigger_source="scheduler",
                actor={"id": "system_scheduler", "email": "system"},
            )

        success = bool(result.get("success"))
        status = "completed" if success else "failed"
        error_msg = None if success else result.get("error")
        run_id = None
        if success and result.get("run"):
            run_id = result["run"].get("id")
        elif result.get("run_id"):
            run_id = result.get("run_id")

        now_iso = datetime.now(UTC).isoformat()
        await raw_db.night_audit_schedule_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "triggered_at": now_iso,
            "business_date": bd,
            "trigger_type": "automatic",
            "status": status,
            "run_id": run_id,
            "error": error_msg,
            "completed_at": now_iso,
        })
        await raw_db.night_audit_schedules.update_one(
            {"tenant_id": tenant_id},
            {"$set": {
                "last_auto_run": now_iso,
                "last_auto_run_status": status,
            }},
        )

        logger.info(
            "Night audit tenant=%s: %s (run=%s, business_date=%s)",
            tenant_id, status, run_id, bd,
        )
        return {
            "success": success,
            "tenant_id": tenant_id,
            "status": status,
            "run_id": run_id,
            "business_date": bd,
        }
    finally:
        engine.client, engine.db = saved_client, saved_db
        client.close()


# ============= DATA ARCHIVAL TASKS =============

@celery_app.task(name='celery_tasks.archive_old_data_task')
def archive_old_data_task():
    """Archive data older than 6 months"""
    return asyncio.run(_archive_old_data_async())

async def _archive_old_data_async():
    """Async data archival implementation"""
    db, client = get_db()

    try:
        # Archive cutoff date: 6 months ago
        cutoff_date = datetime.now(UTC) - timedelta(days=180)

        results = {
            'cutoff_date': cutoff_date.isoformat(),
            'archived': {}
        }

        # Archive old bookings (checked_out > 6 months ago)
        old_bookings = await db.bookings.find({
            'status': 'checked_out',
            'check_out': {'$lt': cutoff_date}
        }).to_list(10000)

        if old_bookings:
            # Move to archive collection
            await db.bookings_archive.insert_many(old_bookings)

            # Delete from main collection
            booking_ids = [b['booking_id'] for b in old_bookings]
            await db.bookings.delete_many({'booking_id': {'$in': booking_ids}})

            results['archived']['bookings'] = len(old_bookings)
            logger.info(f"Archived {len(old_bookings)} old bookings")

        # Archive old audit logs (> 1 year)
        audit_cutoff = datetime.now(UTC) - timedelta(days=365)
        old_logs = await db.audit_logs.find({
            'timestamp': {'$lt': audit_cutoff}
        }).to_list(50000)

        if old_logs:
            await db.audit_logs_archive.insert_many(old_logs)
            log_ids = [log['_id'] for log in old_logs]
            await db.audit_logs.delete_many({'_id': {'$in': log_ids}})

            results['archived']['audit_logs'] = len(old_logs)
            logger.info(f"Archived {len(old_logs)} old audit logs")

        # Archive old closed folios
        old_folios = await db.folios.find({
            'status': 'closed',
            'closed_at': {'$lt': cutoff_date}
        }).to_list(10000)

        if old_folios:
            await db.folios_archive.insert_many(old_folios)
            folio_ids = [f['folio_id'] for f in old_folios]
            await db.folios.delete_many({'folio_id': {'$in': folio_ids}})

            results['archived']['folios'] = len(old_folios)
            logger.info(f"Archived {len(old_folios)} old folios")

        results['success'] = True
        return results

    except Exception as e:
        logger.error(f"Data archival task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= CLEANUP TASKS =============

@celery_app.task(name='celery_tasks.clean_old_notifications_task')
def clean_old_notifications_task():
    """Clean notifications older than 90 days"""
    return asyncio.run(_clean_old_notifications_async())

async def _clean_old_notifications_async():
    """Async notification cleanup"""
    db, client = get_db()

    try:
        cutoff_date = datetime.now(UTC) - timedelta(days=90)

        result = await db.notifications.delete_many({
            'created_at': {'$lt': cutoff_date}
        })

        logger.info(f"Cleaned {result.deleted_count} old notifications")

        return {
            'success': True,
            'deleted_count': result.deleted_count,
            'cutoff_date': cutoff_date.isoformat()
        }

    except Exception as e:
        logger.error(f"Notification cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= REPORTING TASKS =============

@celery_app.task(name='celery_tasks.generate_daily_reports_task')
def generate_daily_reports_task():
    """Generate daily flash reports for all tenants"""
    return asyncio.run(_generate_daily_reports_async())

async def _generate_daily_reports_async():
    """Async daily report generation"""
    db, client = get_db()

    try:
        tenants = await db.users.distinct('tenant_id', {'active': True})

        results = []
        for tenant_id in tenants:
            try:
                yesterday = (datetime.now(UTC) - timedelta(days=1)).date()

                # Calculate daily metrics
                bookings_yesterday = await db.bookings.count_documents({
                    'tenant_id': tenant_id,
                    'created_at': {
                        '$gte': datetime.combine(yesterday, datetime.min.time()),
                        '$lt': datetime.combine(yesterday + timedelta(days=1), datetime.min.time())
                    }
                })

                revenue_yesterday = await db.payments.aggregate([
                    {
                        '$match': {
                            'tenant_id': tenant_id,
                            'created_at': {
                                '$gte': datetime.combine(yesterday, datetime.min.time()),
                                '$lt': datetime.combine(yesterday + timedelta(days=1), datetime.min.time())
                            }
                        }
                    },
                    {
                        '$group': {
                            '_id': None,
                            'total': {'$sum': '$amount'}
                        }
                    }
                ]).to_list(1)

                report = {
                    'tenant_id': tenant_id,
                    'report_date': yesterday.isoformat(),
                    'bookings_count': bookings_yesterday,
                    'revenue': revenue_yesterday[0]['total'] if revenue_yesterday else 0,
                    'generated_at': datetime.now(UTC)
                }

                await db.daily_reports.insert_one(report)
                results.append(report)

            except Exception as e:
                logger.error(f"Daily report generation error for tenant {tenant_id}: {e}")

        return {
            'success': True,
            'reports_generated': len(results),
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Daily reports task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= OPTIMIZATION TASKS =============

@celery_app.task(name='celery_tasks.refresh_materialized_views')
def refresh_materialized_views():
    """Refresh materialized views for dashboard metrics"""
    return asyncio.run(_refresh_materialized_views_async())

async def _refresh_materialized_views_async():
    """Async materialized views refresh"""
    db, client = get_db()

    try:
        from materialized_views import MaterializedViewsManager

        views_manager = MaterializedViewsManager(db)
        result = await views_manager.refresh_dashboard_metrics()

        logger.info(f"Materialized views refreshed: {result.get('refresh_duration_ms')}ms")

        return result

    except Exception as e:
        logger.error(f"Materialized views refresh failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


@celery_app.task(name='celery_tasks.warm_cache')
def warm_cache():
    """Warm cache with frequently accessed data"""
    return asyncio.run(_warm_cache_async())

async def _warm_cache_async():
    """Async cache warming"""
    db, client = get_db()

    try:
        import redis

        from advanced_cache import AdvancedCacheManager, CacheWarmer
        from materialized_views import MaterializedViewsManager

        # Initialize Redis
        redis_client = redis.Redis(
            host='127.0.0.1',
            port=6379,
            db=0,
            decode_responses=False
        )

        cache_manager = AdvancedCacheManager(redis_client)
        cache_warmer = CacheWarmer(cache_manager)
        views_manager = MaterializedViewsManager(db)

        # Warm dashboard cache
        dashboard_result = await cache_warmer.warm_dashboard_cache(views_manager)

        # Warm PMS cache
        pms_result = await cache_warmer.warm_pms_cache(db)

        logger.info(f"Cache warmed: Dashboard={dashboard_result}, PMS={pms_result}")

        return {
            'success': True,
            'dashboard': dashboard_result,
            'pms': pms_result
        }

    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


@celery_app.task(name='celery_tasks.archive_old_bookings')
def archive_old_bookings():
    """Archive old bookings to separate collection"""
    return asyncio.run(_archive_old_bookings_async())

async def _archive_old_bookings_async():
    """Async booking archival"""
    db, client = get_db()

    try:
        from data_archival import DataArchivalManager

        archival_manager = DataArchivalManager(db)
        result = await archival_manager.archive_old_bookings(dry_run=False)

        logger.info(f"Archival completed: {result.get('records_archived', 0)} bookings archived")

        return result

    except Exception as e:
        logger.error(f"Archival failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


@celery_app.task(name='celery_tasks.cleanup_old_cache')
def cleanup_old_cache():
    """Cleanup expired cache entries"""
    return asyncio.run(_cleanup_old_cache_async())

async def _cleanup_old_cache_async():
    """Async cache cleanup"""
    try:
        import redis

        redis_client = redis.Redis(
            host='127.0.0.1',
            port=6379,
            db=0,
            decode_responses=False
        )

        # Get all keys
        keys = redis_client.keys('pms:cache:*')

        # Redis handles TTL automatically, this is just for logging
        logger.info(f"Cache has {len(keys)} keys")

        return {
            'success': True,
            'total_keys': len(keys),
            'message': 'Redis handles TTL automatically'
        }

    except Exception as e:
        logger.error(f"Cache cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@celery_app.task(name='celery_tasks.database_maintenance')
def database_maintenance():
    """Run database maintenance tasks"""
    return asyncio.run(_database_maintenance_async())

async def _database_maintenance_async():
    """Async database maintenance"""
    db, client = get_db()

    try:
        # Ensure all indexes exist
        from data_archival import DataArchivalManager
        from materialized_views import MaterializedViewsManager

        archival_manager = DataArchivalManager(db)
        views_manager = MaterializedViewsManager(db)

        await archival_manager.setup_indexes()
        await views_manager.setup_indexes()

        # Get database stats
        stats = await client.admin.command('serverStatus')

        logger.info("Database maintenance completed")

        return {
            'success': True,
            'uptime': stats['uptime'],
            'connections': stats['connections']['current']
        }

    except Exception as e:
        logger.error(f"Database maintenance failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


@celery_app.task(name='celery_tasks.generate_daily_report')
def generate_daily_report():
    """Generate comprehensive daily performance report"""
    return asyncio.run(_generate_daily_report_async())

async def _generate_daily_report_async():
    """Async daily report generation"""
    db, client = get_db()

    try:
        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)

        # Collect metrics
        bookings_count = await db.bookings.count_documents({
            'created_at': {
                '$gte': datetime.combine(yesterday, datetime.min.time()),
                '$lt': datetime.combine(today, datetime.min.time())
            }
        })

        # Revenue calculation
        revenue_pipeline = [
            {
                '$match': {
                    'created_at': {
                        '$gte': datetime.combine(yesterday, datetime.min.time()),
                        '$lt': datetime.combine(today, datetime.min.time())
                    }
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total_revenue': {'$sum': '$total_amount'}
                }
            }
        ]

        revenue_result = await db.bookings.aggregate(revenue_pipeline).to_list(1)
        revenue = revenue_result[0]['total_revenue'] if revenue_result else 0

        report = {
            'date': yesterday.isoformat(),
            'bookings_count': bookings_count,
            'revenue': revenue,
            'generated_at': datetime.now(UTC)
        }

        # Store report
        await db.daily_performance_reports.insert_one(report)

        logger.info(f"Daily report generated: {bookings_count} bookings, ${revenue} revenue")

        return {
            'success': True,
            'report': report
        }

    except Exception as e:
        logger.error(f"Daily report generation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()



# ============= MAINTENANCE TASKS =============

@celery_app.task(name='celery_tasks.check_maintenance_sla_task')
def check_maintenance_sla_task():
    """Check maintenance tasks for SLA violations"""
    return asyncio.run(_check_maintenance_sla_async())

async def _check_maintenance_sla_async():
    """Async SLA check"""
    db, client = get_db()

    try:
        # Define SLA thresholds (hours)
        sla_thresholds = {
            'critical': 4,
            'high': 12,
            'medium': 24,
            'low': 72
        }

        violations = []
        now = datetime.now(UTC)

        for priority, hours in sla_thresholds.items():
            threshold = now - timedelta(hours=hours)

            tasks = await db.maintenance_tasks.find({
                'status': {'$in': ['open', 'in_progress']},
                'priority': priority,
                'created_at': {'$lt': threshold}
            }).to_list(1000)

            for task in tasks:
                violation = {
                    'task_id': task['task_id'],
                    'room_id': task.get('room_id'),
                    'priority': priority,
                    'created_at': task['created_at'].isoformat(),
                    'hours_open': (now - task['created_at']).total_seconds() / 3600,
                    'sla_hours': hours
                }
                violations.append(violation)

                # Create notification for SLA violation
                notification = {
                    'notification_id': f"NOTIF-SLA-{task['task_id']}",
                    'tenant_id': task['tenant_id'],
                    'user_id': task.get('assigned_to', 'maintenance_manager'),
                    'type': 'maintenance_sla_violation',
                    'title': 'SLA Violation',
                    'message': f"Maintenance task {task['task_id']} exceeds {priority} priority SLA ({hours}h)",
                    'priority': 'high',
                    'read': False,
                    'created_at': now
                }

                await db.notifications.update_one(
                    {'notification_id': notification['notification_id']},
                    {'$set': notification},
                    upsert=True
                )

        logger.info(f"SLA check completed: {len(violations)} violations found")

        return {
            'success': True,
            'violations_count': len(violations),
            'violations': violations[:50],  # Return first 50
            'timestamp': now.isoformat()
        }

    except Exception as e:
        logger.error(f"SLA check task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= FORECAST TASKS =============

@celery_app.task(name='celery_tasks.update_occupancy_forecast_task')
def update_occupancy_forecast_task():
    """Update occupancy forecast using ML model"""
    return asyncio.run(_update_occupancy_forecast_async())

async def _update_occupancy_forecast_async():
    """Async occupancy forecast update"""
    db, client = get_db()

    try:
        # This would integrate with ML model
        # For now, simple calculation

        tenants = await db.users.distinct('tenant_id', {'active': True})

        results = []
        for tenant_id in tenants:
            # Get next 30 days bookings
            today = datetime.now(UTC).date()
            forecasts = []

            for days_ahead in range(30):
                target_date = today + timedelta(days=days_ahead)

                # Count confirmed/guaranteed bookings
                bookings_count = await db.bookings.count_documents({
                    'tenant_id': tenant_id,
                    'check_in': {'$lte': target_date},
                    'check_out': {'$gt': target_date},
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
                })

                # Get total rooms
                total_rooms = await db.rooms.count_documents({'tenant_id': tenant_id})

                occupancy_pct = (bookings_count / max(1, total_rooms)) * 100

                forecasts.append({
                    'date': target_date.isoformat(),
                    'forecasted_occupancy': round(occupancy_pct, 2),
                    'booked_rooms': bookings_count,
                    'total_rooms': total_rooms
                })

            # Store forecast
            await db.occupancy_forecasts.update_one(
                {'tenant_id': tenant_id},
                {
                    '$set': {
                        'tenant_id': tenant_id,
                        'forecasts': forecasts,
                        'updated_at': datetime.now(UTC)
                    }
                },
                upsert=True
            )

            results.append({
                'tenant_id': tenant_id,
                'forecasts_generated': len(forecasts)
            })

        return {
            'success': True,
            'tenants_updated': len(results),
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Occupancy forecast task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= E-FATURA TASKS =============

@celery_app.task(name='celery_tasks.process_pending_efaturas_task')
def process_pending_efaturas_task():
    """Process pending e-fatura generations"""
    return asyncio.run(_process_pending_efaturas_async())

async def _process_pending_efaturas_async():
    """Async e-fatura processing"""
    db, client = get_db()

    try:
        # Find invoices with pending e-fatura
        pending_invoices = await db.accounting_invoices.find({
            'efatura_status': 'pending',
            'invoice_type': 'sales'
        }).limit(100).to_list(100)

        processed = 0
        for invoice in pending_invoices:
            try:
                # Generate e-fatura (mock - would call actual API)
                efatura_uuid = f"EFATURA-{invoice['invoice_number']}"

                await db.accounting_invoices.update_one(
                    {'invoice_number': invoice['invoice_number']},
                    {
                        '$set': {
                            'efatura_status': 'generated',
                            'efatura_uuid': efatura_uuid,
                            'efatura_generated_at': datetime.now(UTC)
                        }
                    }
                )

                processed += 1

            except Exception as e:
                logger.error(f"E-fatura generation error for {invoice['invoice_number']}: {e}")

        return {
            'success': True,
            'processed': processed,
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"E-fatura processing task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


# ============= CACHE WARMING TASKS =============

@celery_app.task(name='celery_tasks.warm_cache_task')
def warm_cache_task():
    """Warm up cache with frequently accessed data"""
    return asyncio.run(_warm_cache_async())

async def _warm_cache_async():
    """Async cache warming"""
    try:
        from cache_manager import warm_dashboard_cache, warm_room_cache

        db, client = get_db()

        tenants = await db.users.distinct('tenant_id', {'active': True})

        for tenant_id in tenants:
            await warm_dashboard_cache(tenant_id, db)
            await warm_room_cache(tenant_id, db)

        await client.close()

        return {
            'success': True,
            'tenants_warmed': len(tenants),
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        logger.error(f"Cache warming task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# ============= HEALTH CHECK TASKS =============

@celery_app.task(name='celery_tasks.database_health_check_task')
def database_health_check_task():
    """Check database health and performance"""
    return asyncio.run(_database_health_check_async())

async def _database_health_check_async():
    """Async database health check"""
    db, client = get_db()

    try:
        # Test database connection
        await db.command('ping')

        # Check collection sizes
        collections_info = {}
        for coll_name in ['bookings', 'rooms', 'guests', 'folios']:
            count = await db[coll_name].count_documents({})
            collections_info[coll_name] = count

        # Check for slow queries (would need profiling enabled)
        health_status = {
            'status': 'healthy',
            'collections': collections_info,
            'timestamp': datetime.now(UTC).isoformat()
        }

        # Store health check result
        await db.health_checks.insert_one(health_status)

        await client.close()

        return health_status

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat()
        }



# ============= HRv2 SHADOW AUTOMATION TASKS =============

@celery_app.task(name='celery_tasks.hrv2_shadow_snapshot_task')
def hrv2_shadow_snapshot_task():
    """Run 6-hourly shadow automation snapshot for HRv2 connector."""
    return asyncio.run(_hrv2_shadow_snapshot_async())

async def _hrv2_shadow_snapshot_async():
    """Async HRv2 shadow snapshot."""
    try:
        from channel_manager.connectors.hotelrunner_v2.shadow_automation import (
            DEFAULT_TENANT,
            run_periodic_snapshot,
        )
        result = await run_periodic_snapshot(DEFAULT_TENANT)
        logger.info("HRv2 shadow snapshot completed: readiness=%s", result.get("readiness", {}).get("overall_score"))
        return {
            'success': True,
            'readiness_score': result.get("readiness", {}).get("overall_score"),
            'alerts_generated': result.get("alerts_generated", 0),
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error(f"HRv2 shadow snapshot failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(name='celery_tasks.hrv2_daily_summary_task')
def hrv2_daily_summary_task():
    """Generate daily summary for HRv2 shadow automation."""
    return asyncio.run(_hrv2_daily_summary_async())

async def _hrv2_daily_summary_async():
    """Async HRv2 daily summary."""
    try:
        from channel_manager.connectors.hotelrunner_v2.shadow_automation import (
            DEFAULT_TENANT,
            generate_daily_summary,
        )
        result = await generate_daily_summary(DEFAULT_TENANT)
        logger.info("HRv2 daily summary generated: score=%s", result.get("readiness", {}).get("current_score"))
        return {
            'success': True,
            'summary_date': result.get("summary_date"),
            'readiness_score': result.get("readiness", {}).get("current_score"),
            'score_change': result.get("readiness", {}).get("change"),
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error(f"HRv2 daily summary failed: {e}")
        return {'success': False, 'error': str(e)}


# ============= F8N TASK #224 — RNL DUPLICATE AUTO-RESOLVE =============

# Task #237: keep `rnl_auto_resolve_runs` from growing unbounded. The beat job
# writes one summary row per day; without trimming, the super-admin panel's
# `sort(started_at desc).limit(N)` query slows down and Atlas storage grows
# forever. Retention defaults to one year (365 rows for the daily schedule);
# operators can override via the `RNL_AUTO_RESOLVE_RUN_RETENTION_DAYS` env
# var. A descending index on `started_at` keeps both the panel read and the
# pruning delete O(log n).
_RNL_RUN_HISTORY_COLL = "rnl_auto_resolve_runs"
_RNL_RUN_HISTORY_RETENTION_DAYS_DEFAULT = 365
_RNL_RUN_HISTORY_INDEX_READY = False


def _rnl_run_history_retention_days() -> int:
    raw = os.environ.get("RNL_AUTO_RESOLVE_RUN_RETENTION_DAYS")
    if not raw:
        return _RNL_RUN_HISTORY_RETENTION_DAYS_DEFAULT
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return _RNL_RUN_HISTORY_RETENTION_DAYS_DEFAULT
    return v if v > 0 else _RNL_RUN_HISTORY_RETENTION_DAYS_DEFAULT


async def _ensure_rnl_run_history_index(db) -> None:
    """Best-effort create the `started_at desc` index used by the panel
    query and the retention prune. Idempotent and process-cached."""
    global _RNL_RUN_HISTORY_INDEX_READY
    if _RNL_RUN_HISTORY_INDEX_READY:
        return
    try:
        await db[_RNL_RUN_HISTORY_COLL].create_index(
            [("started_at", -1)],
            name="ix_started_at_desc",
            background=True,
        )
        _RNL_RUN_HISTORY_INDEX_READY = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("F8N rnl_auto_resolve_runs index create failed: %s", exc)


async def _prune_rnl_run_history(db, retention_days: int) -> dict[str, Any]:
    """Delete `rnl_auto_resolve_runs` rows older than `retention_days`.

    `started_at` is persisted as an ISO-8601 UTC string (always with the
    `+00:00` suffix produced by `datetime.now(UTC).isoformat()`), so a
    lexicographic `$lt` comparison against another ISO-8601 UTC cutoff is
    equivalent to a chronological comparison.
    """
    cutoff_dt = datetime.now(UTC) - timedelta(days=retention_days)
    cutoff_iso = cutoff_dt.isoformat()
    try:
        res = await db[_RNL_RUN_HISTORY_COLL].delete_many(
            {"started_at": {"$lt": cutoff_iso}}
        )
        return {
            "ran": True,
            "deleted": int(getattr(res, "deleted_count", 0) or 0),
            "retention_days": retention_days,
            "cutoff": cutoff_iso,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("F8N rnl_auto_resolve_runs prune failed: %s", exc)
        return {
            "ran": False,
            "error": str(exc)[:200],
            "retention_days": retention_days,
            "cutoff": cutoff_iso,
        }


@celery_app.task(name='celery_tasks.rnl_duplicate_auto_resolve_task')
def rnl_duplicate_auto_resolve_task(limit: int = 100):
    """Daily Celery beat job: auto-resolve safe duplicate room-night-lock groups.

    Mirrors the super-admin endpoint (`/api/db-admin/room-night-lock-duplicates/resolve`):
    only `auto_safe` / `auto_safe_all_inactive` groups are deleted; `manual_required`
    groups are reported in the response and logged so monitoring can alert when they
    accumulate. After a successful resolution we re-run `ensure_booking_indexes` to
    rebuild the unique `ux_room_night` guard if it was previously blocked by the
    duplicates.
    """
    return asyncio.run(_rnl_duplicate_auto_resolve_async(limit=limit))


async def _rnl_duplicate_auto_resolve_async(limit: int = 100):
    """Async implementation of the RNL duplicate auto-resolver beat job."""
    try:
        from core.atomic_booking import (
            ensure_booking_indexes,
            resolve_room_night_lock_duplicates,
        )
    except Exception as exc:
        logger.error("F8N rnl auto-resolve import failed: %s", exc)
        return {'success': False, 'error': f'import_failed: {exc}'}

    started_at = datetime.now(UTC).isoformat()
    try:
        result = await resolve_room_night_lock_duplicates(
            apply=True,
            limit=limit,
            actor_id="celery_beat",
            actor_name="rnl_duplicate_auto_resolve",
            actor_role="super_admin",
        )
    except Exception as exc:
        logger.error("F8N rnl auto-resolve apply failed: %s", exc)
        return {'success': False, 'error': str(exc), 'started_at': started_at}

    resolved_count = result.get('resolved_count', 0)
    skipped_count = result.get('skipped_count', 0)
    manual_required = [
        s for s in result.get('skipped', [])
        if s.get('recommendation') == 'manual_required'
    ]
    manual_required_count = len(manual_required)

    index_rebuild: dict[str, Any] = {'ran': False}
    if resolved_count > 0:
        try:
            await ensure_booking_indexes()
            index_rebuild = {'ran': True}
        except Exception as exc:
            logger.warning("F8N rnl auto-resolve index rebuild failed: %s", exc)
            index_rebuild = {'ran': False, 'error': str(exc)[:200]}

    # Metric / alert line: a non-zero manual_required count means a human still
    # has to adjudicate. Monitoring should alert on sustained > 0 values.
    logger.warning(
        "F8N rnl_duplicate_auto_resolve scanned=%d resolved=%d skipped=%d manual_required=%d index_rebuild=%s",
        result.get('scanned', 0),
        resolved_count,
        skipped_count,
        manual_required_count,
        index_rebuild,
    )

    # Task #234: record a heartbeat so a separate monitor can alert if this
    # beat job ever stops firing entirely (silent dead-scheduler failure mode
    # that Task #228's outcome alert can't see — no run, no alert).
    try:
        from core.database import db as _hb_db
        await _hb_db[_RNL_HEARTBEAT_COLL].update_one(
            {"state_key": _RNL_HEARTBEAT_KEY},
            {"$set": {
                "state_key": _RNL_HEARTBEAT_KEY,
                "last_success_at": datetime.now(UTC).isoformat(),
                "last_scanned": result.get('scanned', 0),
                "last_resolved_count": resolved_count,
                "last_manual_required_count": manual_required_count,
            }, "$unset": {
                # Heartbeat-stale alert was outstanding; clear it so the next
                # staleness event re-alerts (no permanent suppression).
                "last_stale_alert_at": "",
                "last_stale_alert_age_hours": "",
            }},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001 — never let heartbeat break the job
        logger.warning("F8N rnl auto-resolve heartbeat write failed: %s", exc)

    # Task #228: actively notify operators when manual_required groups stick
    # around. Suppress consecutive-day spam by tracking a tiny state doc; only
    # re-alert when the previous run reported zero (i.e. the issue cleared and
    # came back) or when the count escalates noticeably above the last alert.
    alert_dispatched: dict[str, Any] = {'sent': False, 'suppressed': False}
    try:
        alert_dispatched = await _maybe_dispatch_rnl_manual_required_alert(
            manual_required=manual_required,
            scanned=result.get('scanned', 0),
            resolved_count=resolved_count,
        )
    except Exception as exc:  # noqa: BLE001 — never let alerting break the beat job
        logger.warning("F8N rnl auto-resolve alert dispatch failed: %s", exc)
        alert_dispatched = {'sent': False, 'suppressed': False, 'error': str(exc)[:200]}

    summary = {
        'success': True,
        'started_at': started_at,
        'finished_at': datetime.now(UTC).isoformat(),
        'scanned': result.get('scanned', 0),
        'resolved_count': resolved_count,
        'skipped_count': skipped_count,
        'manual_required_count': manual_required_count,
        'index_rebuild': index_rebuild,
        'alert_dispatched': alert_dispatched,
    }

    # Persist run summary so the super-admin panel can show history without
    # log-diving. Best-effort: a write failure must not fail the beat job.
    # Task #237: also ensure the panel's sort/limit query has a `started_at`
    # index, and prune rows past the retention window so neither Atlas
    # storage nor the panel query grow without bound.
    retention_info: dict[str, Any] = {'ran': False, 'reason': 'skipped'}
    try:
        from core.database import db
        await _ensure_rnl_run_history_index(db)
        await db[_RNL_RUN_HISTORY_COLL].insert_one({
            **summary,
            'actor_id': 'celery_beat',
            'limit': limit,
        })
        retention_info = await _prune_rnl_run_history(
            db, _rnl_run_history_retention_days()
        )
    except Exception as exc:
        logger.warning("F8N rnl auto-resolve run history write failed: %s", exc)
        retention_info = {'ran': False, 'error': str(exc)[:200]}

    summary['run_history_retention'] = retention_info
    return summary


# State doc key: tracks the last manual_required alert so consecutive daily
# runs don't spam operators. Single fixed doc — this is a system-wide signal.
_RNL_ALERT_STATE_COLL = "rnl_duplicate_alert_state"
_RNL_ALERT_STATE_KEY = "manual_required"
# Re-alert when the manual_required count grows by at least this much above
# the last alerted value (so escalation gets a fresh ping even mid-streak).
_RNL_ALERT_ESCALATION_DELTA = 5

# Task #234: heartbeat doc — last successful run of the RNL duplicate beat
# job. A separate monitor task alerts when this is stale, catching the case
# where the beat scheduler itself stops firing the job entirely.
_RNL_HEARTBEAT_COLL = "rnl_duplicate_heartbeat"
_RNL_HEARTBEAT_KEY = "auto_resolve"
# Daily beat job (03:30 UTC) is expected every ~24h. Allow one missed run
# plus 12h grace before screaming.
_RNL_HEARTBEAT_STALE_HOURS = 36
# Re-alert at most once per day when the heartbeat stays stale.
_RNL_HEARTBEAT_REALERT_HOURS = 24

# Task #242: duplicate-prevention unique-index backstop deferral monitor.
# Each backstop self-heals once duplicate residue is cleaned, but while it is
# deferred the "no duplicate supplier/contract" safeguard is OFF for everyone
# (the index is global across tenants). This monitor reads the backstop status
# and emails ops when any backstop stays deferred past a grace window, so the
# residue is cleaned promptly instead of leaving duplicates possible for days.
_BACKSTOP_ALERT_COLL = "unique_backstop_alert_state"
# How long a backstop may stay deferred before we alert. A short grace window
# avoids paging on transient build contention while still flagging a genuine
# duplicate-residue deferral the same day. Overridable for ops tuning.
_BACKSTOP_DEFER_ALERT_HOURS = float(
    os.environ.get("UNIQUE_BACKSTOP_DEFER_ALERT_HOURS", "6") or "6")
# Re-alert at most once per this window while a backstop stays deferred, so a
# multi-day residue does not page on every hourly check.
_BACKSTOP_REALERT_HOURS = float(
    os.environ.get("UNIQUE_BACKSTOP_REALERT_HOURS", "24") or "24")


async def _maybe_dispatch_rnl_manual_required_alert(
    *,
    manual_required: list[dict[str, Any]],
    scanned: int,
    resolved_count: int,
) -> dict[str, Any]:
    """Dispatch a high-severity alert when manual_required > 0, with suppression.

    Suppression rules (Task #228 — "single alert rather than spamming every day"):
      * count == 0 → clear state, no alert.
      * count > 0 and previous state was zero/missing → first detection, alert.
      * count > 0 and previous state was non-zero → suppress, unless the count
        escalated by at least ``_RNL_ALERT_ESCALATION_DELTA`` above the last
        alerted value (so operators get a fresh ping on a worsening backlog).

    The payload includes a representative tenant/room/night triple so
    operators can jump straight to
    ``GET /api/db-admin/room-night-lock-duplicates`` and the matching
    super-admin resolve endpoint.
    """
    from core.database import db

    count = len(manual_required)
    state_filter = {"state_key": _RNL_ALERT_STATE_KEY}
    state_doc = await db[_RNL_ALERT_STATE_COLL].find_one(state_filter, {"_id": 0})
    now_iso = datetime.now(UTC).isoformat()

    if count == 0:
        # Clear streak when the backlog drains so the next non-zero run re-alerts.
        if state_doc and state_doc.get("active"):
            await db[_RNL_ALERT_STATE_COLL].update_one(
                state_filter,
                {"$set": {
                    "active": False,
                    "last_count": 0,
                    "cleared_at": now_iso,
                    "updated_at": now_iso,
                }, "$unset": {"active_since": ""}},
                upsert=True,
            )
            # Task #243: notify the operator dashboard widget that the backlog
            # cleared so it can hide without waiting for the next poll.
            await _broadcast_rnl_alert_state_change(
                transition="cleared",
                current_count=0,
                previous_count=int(state_doc.get("last_alert_count") or 0),
            )
        return {'sent': False, 'suppressed': False, 'reason': 'count_zero'}

    last_alert_count = int((state_doc or {}).get("last_alert_count") or 0)
    streak_active = bool((state_doc or {}).get("active"))
    escalated = (count - last_alert_count) >= _RNL_ALERT_ESCALATION_DELTA

    if streak_active and not escalated:
        # Sustained non-zero, no meaningful escalation → keep quiet but bump
        # last-seen so we can audit the streak.
        await db[_RNL_ALERT_STATE_COLL].update_one(
            state_filter,
            {"$set": {
                "active": True,
                "last_count": count,
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        return {
            'sent': False,
            'suppressed': True,
            'reason': 'streak_active',
            'last_alert_count': last_alert_count,
            'current_count': count,
        }

    sample = manual_required[0]
    sample_ctx = {
        "manual_required_count": count,
        "scanned": scanned,
        "resolved_in_run": resolved_count,
        "sample_tenant_id": sample.get("tenant_id"),
        "sample_room_id": sample.get("room_id"),
        "sample_night_date": sample.get("night_date"),
        "sample_reason": sample.get("reason"),
        "endpoint": "/api/db-admin/room-night-lock-duplicates",
    }
    if escalated and streak_active:
        sample_ctx["previous_alert_count"] = last_alert_count
        sample_ctx["escalation_delta"] = count - last_alert_count

    alert_payload = {
        "title": (
            f"RNL duplicate backlog: {count} manual_required group(s)"
            + (" [escalated]" if (escalated and streak_active) else "")
        ),
        "severity": "high",
        "alert_type": "rnl_duplicate_manual_required",
        "provider": "system",
        "message": (
            "Daily room-night-lock auto-resolver left "
            f"{count} duplicate group(s) needing manual review. "
            "Use the super-admin duplicates endpoint to inspect."
        ),
        "runbook_hint": "docs/GOTCHAS.md → F8N RNL duplicate resolver",
        "context": sample_ctx,
    }

    sent = False
    dispatch_error: str | None = None
    try:
        from domains.channel_manager.monitoring.alert_dispatch import dispatch_alert
        dispatch_result = await dispatch_alert(alert_payload, tenant_id="system")
        sent = bool(
            dispatch_result.get("slack") or dispatch_result.get("email")
            or dispatch_result.get("dashboard")
        )
    except Exception as exc:  # noqa: BLE001
        dispatch_error = str(exc)[:200]
        logger.warning("F8N rnl manual_required dispatch_alert failed: %s", exc)

    if not sent:
        # Reliability guard: do NOT advance suppression state when delivery
        # failed (exception OR all channels reported false). Otherwise a
        # transient dispatcher outage on first detection would silence the
        # next day's alert too. Record last_count for audit, but leave
        # `active` / `last_alert_count` untouched so the next run retries.
        await db[_RNL_ALERT_STATE_COLL].update_one(
            state_filter,
            {"$set": {
                "state_key": _RNL_ALERT_STATE_KEY,
                "last_count": count,
                "last_dispatch_failed_at": now_iso,
                "last_dispatch_error": dispatch_error or "no_channel_accepted",
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        # Structured log so monitoring can spot alerting-channel health issues.
        logger.error(
            "F8N rnl manual_required alert NOT delivered count=%d error=%s "
            "(will retry on next run)",
            count, dispatch_error or "no_channel_accepted",
        )
        return {
            'sent': False,
            'suppressed': False,
            'reason': 'dispatch_failed',
            'dispatch_error': dispatch_error or "no_channel_accepted",
            'current_count': count,
            'previous_alert_count': last_alert_count,
        }

    set_fields: dict[str, Any] = {
        "state_key": _RNL_ALERT_STATE_KEY,
        "active": True,
        "last_count": count,
        "last_alert_count": count,
        "last_alert_at": now_iso,
        "last_sample": {
            "tenant_id": sample.get("tenant_id"),
            "room_id": sample.get("room_id"),
            "night_date": sample.get("night_date"),
        },
        "updated_at": now_iso,
    }
    # Task #233: `active_since` captures the start of the current non-zero
    # streak so the operator dashboard can show how long a backlog has
    # persisted. Only set on the first successful dispatch of the streak;
    # leave untouched on escalation dispatches so the timestamp doesn't
    # drift forward over time. Cleared in the count==0 branch above.
    if not streak_active or not (state_doc or {}).get("active_since"):
        set_fields["active_since"] = now_iso
    await db[_RNL_ALERT_STATE_COLL].update_one(
        state_filter,
        {"$set": set_fields, "$unset": {
            "last_dispatch_failed_at": "",
            "last_dispatch_error": "",
        }},
        upsert=True,
    )

    reason = 'escalated' if (escalated and streak_active) else 'first_detection'
    # Task #243: push a live event to the operator dashboard so the duplicate-
    # locks widget appears/escalates without waiting for the next poll.
    await _broadcast_rnl_alert_state_change(
        transition=reason,
        current_count=count,
        previous_count=last_alert_count,
        active_since=set_fields.get("active_since") or (state_doc or {}).get("active_since"),
        sample=set_fields["last_sample"],
    )

    return {
        'sent': True,
        'suppressed': False,
        'reason': reason,
        'current_count': count,
        'previous_alert_count': last_alert_count,
    }


async def _broadcast_rnl_alert_state_change(
    *,
    transition: str,
    current_count: int,
    previous_count: int,
    active_since: str | None = None,
    sample: dict[str, Any] | None = None,
) -> None:
    """Emit a ``rnl_duplicate_alert_state_changed`` socket event so the
    operator dashboard widget (Task #233) can re-render immediately on
    transitions (count 0→N, escalations, and N→0). Best-effort: websocket
    failures must not affect the resolver outcome.
    """
    try:
        from websocket_server import broadcast_system_health_event
        severity = "info" if transition == "cleared" else "high"
        payload: dict[str, Any] = {
            "transition": transition,
            "manual_required_count": current_count,
            "previous_alert_count": previous_count,
        }
        if active_since:
            payload["active_since"] = active_since
        if sample:
            payload["sample"] = sample
        await broadcast_system_health_event(
            "rnl_duplicate_alert_state_changed",
            payload,
            tenant_id=None,
            severity=severity,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("rnl_duplicate_alert_state_changed broadcast failed: %s", exc)

# ============= F8N TASK #234 — RNL HEARTBEAT MONITOR =============

@celery_app.task(name='celery_tasks.rnl_duplicate_heartbeat_check_task')
def rnl_duplicate_heartbeat_check_task():
    """Periodic check: alert when the daily RNL duplicate auto-resolve beat
    job has not recorded a successful run in ~36h.

    This catches the silent failure mode where the beat scheduler itself
    stops firing (or every run throws before reaching the heartbeat write).
    Task #228 only alerts on the *outcome* of a run; with no runs at all,
    no alert would ever fire and duplicates would silently accumulate.
    """
    return asyncio.run(_rnl_duplicate_heartbeat_check_async())


async def _rnl_duplicate_heartbeat_check_async() -> dict[str, Any]:
    """Async body of the heartbeat staleness monitor."""
    from core.database import db

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    state_filter = {"state_key": _RNL_HEARTBEAT_KEY}
    doc = await db[_RNL_HEARTBEAT_COLL].find_one(state_filter, {"_id": 0})

    # Bootstrap: if we've never seen a successful run, stamp an
    # `first_observed_at` so we don't alert immediately on a fresh deploy
    # but we *do* alert if no run lands within the staleness window after
    # boot.
    if not doc or not doc.get("last_success_at"):
        first_observed = (doc or {}).get("first_observed_at")
        if not first_observed:
            await db[_RNL_HEARTBEAT_COLL].update_one(
                state_filter,
                {"$setOnInsert": {"state_key": _RNL_HEARTBEAT_KEY},
                 "$set": {"first_observed_at": now_iso}},
                upsert=True,
            )
            return {
                "stale": False,
                "reason": "bootstrap",
                "first_observed_at": now_iso,
            }
        baseline_iso = first_observed
        baseline_field = "first_observed_at"
    else:
        baseline_iso = doc["last_success_at"]
        baseline_field = "last_success_at"

    try:
        baseline = datetime.fromisoformat(baseline_iso)
    except Exception:
        # Corrupt timestamp — treat as stale to surface the problem.
        baseline = now - timedelta(hours=_RNL_HEARTBEAT_STALE_HOURS + 1)

    if baseline.tzinfo is None:
        baseline = baseline.replace(tzinfo=UTC)

    age = now - baseline
    age_hours = age.total_seconds() / 3600.0

    if age_hours < _RNL_HEARTBEAT_STALE_HOURS:
        return {
            "stale": False,
            "reason": "fresh",
            "age_hours": round(age_hours, 2),
            "baseline_field": baseline_field,
            "baseline_at": baseline_iso,
        }

    # Stale — suppress repeat alerts so an outage doesn't ping every hour.
    last_alert_iso = (doc or {}).get("last_stale_alert_at")
    if last_alert_iso:
        try:
            last_alert = datetime.fromisoformat(last_alert_iso)
            if last_alert.tzinfo is None:
                last_alert = last_alert.replace(tzinfo=UTC)
            since_last_alert = (now - last_alert).total_seconds() / 3600.0
            if since_last_alert < _RNL_HEARTBEAT_REALERT_HOURS:
                return {
                    "stale": True,
                    "alert_sent": False,
                    "reason": "suppressed",
                    "age_hours": round(age_hours, 2),
                    "hours_since_last_alert": round(since_last_alert, 2),
                }
        except Exception:
            pass

    alert_payload = {
        "title": (
            f"RNL duplicate auto-resolve beat job stale ({int(age_hours)}h "
            "since last success)"
        ),
        "severity": "high",
        "alert_type": "rnl_duplicate_heartbeat_stale",
        "provider": "system",
        "message": (
            "The daily room-night-lock duplicate auto-resolver "
            "(celery_tasks.rnl_duplicate_auto_resolve_task) has not "
            f"recorded a successful run for {int(age_hours)}h "
            f"(threshold: {_RNL_HEARTBEAT_STALE_HOURS}h). The Celery beat "
            "scheduler may be down or the job may be failing before it "
            "reaches the heartbeat write. Duplicates can silently "
            "accumulate until this is restored."
        ),
        "runbook_hint": "docs/GOTCHAS.md → F8N RNL duplicate resolver",
        "context": {
            "age_hours": round(age_hours, 2),
            "stale_threshold_hours": _RNL_HEARTBEAT_STALE_HOURS,
            "baseline_field": baseline_field,
            "baseline_at": baseline_iso,
            "beat_task": "celery_tasks.rnl_duplicate_auto_resolve_task",
        },
    }

    sent = False
    dispatch_error: str | None = None
    try:
        from domains.channel_manager.monitoring.alert_dispatch import dispatch_alert
        dispatch_result = await dispatch_alert(alert_payload, tenant_id="system")
        sent = bool(
            dispatch_result.get("slack") or dispatch_result.get("email")
            or dispatch_result.get("dashboard")
        )
    except Exception as exc:  # noqa: BLE001
        dispatch_error = str(exc)[:200]
        logger.warning("F8N rnl heartbeat dispatch_alert failed: %s", exc)

    if not sent:
        # Don't advance the re-alert suppression clock when delivery fails —
        # next check should retry.
        logger.error(
            "F8N rnl heartbeat stale alert NOT delivered age_hours=%.2f error=%s",
            age_hours, dispatch_error or "no_channel_accepted",
        )
        await db[_RNL_HEARTBEAT_COLL].update_one(
            state_filter,
            {"$set": {
                "state_key": _RNL_HEARTBEAT_KEY,
                "last_stale_dispatch_failed_at": now_iso,
                "last_stale_dispatch_error": dispatch_error or "no_channel_accepted",
            }},
            upsert=True,
        )
        return {
            "stale": True,
            "alert_sent": False,
            "reason": "dispatch_failed",
            "age_hours": round(age_hours, 2),
            "dispatch_error": dispatch_error or "no_channel_accepted",
        }

    await db[_RNL_HEARTBEAT_COLL].update_one(
        state_filter,
        {"$set": {
            "state_key": _RNL_HEARTBEAT_KEY,
            "last_stale_alert_at": now_iso,
            "last_stale_alert_age_hours": round(age_hours, 2),
        }, "$unset": {
            "last_stale_dispatch_failed_at": "",
            "last_stale_dispatch_error": "",
        }},
        upsert=True,
    )
    logger.warning(
        "F8N rnl heartbeat stale alert dispatched age_hours=%.2f", age_hours,
    )
    return {
        "stale": True,
        "alert_sent": True,
        "age_hours": round(age_hours, 2),
        "baseline_field": baseline_field,
        "baseline_at": baseline_iso,
    }


@celery_app.task(name='celery_tasks.unique_backstop_deferral_check_task')
def unique_backstop_deferral_check_task():
    """Task #242: alert ops by email when a duplicate-prevention safeguard is off.

    The "no duplicate supplier/contract" guards are race-safe only behind global
    partial unique indexes (the *backstops*). A build is deferred when legacy
    duplicate rows exist, silently turning the safeguard OFF for everyone until
    the residue is cleaned. Task #231 made this observable (metric + ops
    endpoint) but ops only see it if they look. This periodic check reads the
    backstop status and emails ops when any backstop has stayed deferred past a
    grace window, so duplicates do not stay possible for days unnoticed.
    """
    return asyncio.run(_unique_backstop_deferral_check_async())


async def _unique_backstop_deferral_check_async() -> dict[str, Any]:
    """Async body: attempt the backstop builds, then alert on lingering deferrals.

    The ``index_backstops`` registry is in-process state, and the Celery worker
    is a separate process from the API, so its registry starts empty. We touch
    the same lazy index builders the ops endpoint uses so a build is attempted
    (and self-heals) here, then read the resulting status. Per-backstop deferral
    duration + re-alert suppression are persisted in Mongo so we can alert "off
    for longer than a threshold" and avoid paging on every hourly run.
    """
    from core.database import db
    from shared_kernel import index_backstops

    # Touch the lazy index builders so a not-yet-attempted backstop is attempted
    # (and self-heals) in this worker process, mirroring the ops endpoint.
    try:
        from routers.mice import _ensure_indexes as _mice_ensure_indexes
        await _mice_ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("backstop monitor: mice ensure_indexes failed: %s", exc)
    try:
        from domains.revenue.rms_router.sales import _ensure_contract_indexes
        await _ensure_contract_indexes()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "backstop monitor: contract ensure_indexes failed: %s", exc)

    now = datetime.now(UTC)
    now_iso = now.isoformat()

    backstops = index_backstops.list_status()
    deferred = [b for b in backstops if b.get("status") == "deferred"]
    deferred_names = {b["name"] for b in deferred}

    # Clear persisted state for any backstop that is no longer deferred (it
    # self-healed) so a future deferral starts a fresh grace window and a
    # resolved one never re-alerts.
    cleared = []
    async for st in db[_BACKSTOP_ALERT_COLL].find({}, {"_id": 0}):
        name = st.get("backstop")
        if name and name not in deferred_names:
            await db[_BACKSTOP_ALERT_COLL].delete_one({"backstop": name})
            cleared.append(name)

    if not deferred:
        # No noise while all backstops are active.
        return {
            "deferred_count": 0,
            "alert_sent": False,
            "reason": "all_active",
            "cleared": cleared,
        }

    # Stamp first_deferred_at on first sighting; compute how long each has been
    # off and whether the grace window has elapsed.
    ripe: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for b in deferred:
        name = b["name"]
        st = await db[_BACKSTOP_ALERT_COLL].find_one(
            {"backstop": name}, {"_id": 0})
        if not st or not st.get("first_deferred_at"):
            await db[_BACKSTOP_ALERT_COLL].update_one(
                {"backstop": name},
                {"$setOnInsert": {"backstop": name},
                 "$set": {
                     "collection": b.get("collection"),
                     "fields": b.get("fields"),
                     "first_deferred_at": now_iso,
                 }},
                upsert=True,
            )
            pending.append({**b, "deferred_hours": 0.0})
            continue
        try:
            first = datetime.fromisoformat(st["first_deferred_at"])
            if first.tzinfo is None:
                first = first.replace(tzinfo=UTC)
        except Exception:
            first = now
        deferred_hours = (now - first).total_seconds() / 3600.0
        entry = {
            **b,
            "deferred_hours": round(deferred_hours, 2),
            "first_deferred_at": st["first_deferred_at"],
            "last_alert_at": st.get("last_alert_at"),
        }
        if deferred_hours >= _BACKSTOP_DEFER_ALERT_HOURS:
            ripe.append(entry)
        else:
            pending.append(entry)

    # Of the ripe (past-grace) backstops, only those outside the re-alert
    # suppression window justify a fresh page.
    to_alert: list[dict[str, Any]] = []
    for entry in ripe:
        last_alert_iso = entry.get("last_alert_at")
        if last_alert_iso:
            try:
                last_alert = datetime.fromisoformat(last_alert_iso)
                if last_alert.tzinfo is None:
                    last_alert = last_alert.replace(tzinfo=UTC)
                since = (now - last_alert).total_seconds() / 3600.0
                if since < _BACKSTOP_REALERT_HOURS:
                    continue
            except Exception:
                pass
        to_alert.append(entry)

    if not to_alert:
        return {
            "deferred_count": len(deferred),
            "alert_sent": False,
            "reason": "within_grace_or_suppressed",
            "ripe_count": len(ripe),
            "pending_count": len(pending),
            "cleared": cleared,
        }

    lines = ", ".join(
        f"{e['name']} ({e.get('collection')} on {'+'.join(e.get('fields') or [])}; "
        f"off ~{int(e['deferred_hours'])}h)"
        for e in to_alert
    )
    alert_payload = {
        "title": (
            f"Duplicate-prevention safeguard OFF "
            f"({len(to_alert)} unique-index backstop"
            f"{'s' if len(to_alert) != 1 else ''} deferred)"
        ),
        "severity": "high",
        "alert_type": "unique_index_backstop_deferred",
        "provider": "system",
        "message": (
            "One or more duplicate-prevention unique-index backstops have been "
            f"deferred for over {int(_BACKSTOP_DEFER_ALERT_HOURS)}h, leaving the "
            "no-duplicate safeguard OFF across all tenants (the index is "
            "global). Pre-existing duplicate rows block the build. Remediation: "
            "clean the duplicate rows in the named collection(s) — the backstop "
            "self-heals on the next attempt, no restart needed. Affected: "
            f"{lines}."
        ),
        "runbook_hint": (
            "Inspect GET /api/production-golive/uniqueness-backstops; clean "
            "duplicate supplier/contract residue (see Task #231 / index "
            "backstops in shared_kernel/index_backstops.py)."
        ),
        "context": {
            "deferred_backstops": [
                {
                    "backstop": e["name"],
                    "collection": e.get("collection"),
                    "fields": e.get("fields"),
                    "deferred_hours": e["deferred_hours"],
                    "first_deferred_at": e.get("first_deferred_at"),
                }
                for e in to_alert
            ],
            "grace_hours": _BACKSTOP_DEFER_ALERT_HOURS,
            "total_deferred": len(deferred),
        },
    }

    sent = False
    dispatch_error: str | None = None
    try:
        from domains.channel_manager.monitoring.alert_dispatch import dispatch_alert
        dispatch_result = await dispatch_alert(alert_payload, tenant_id="system")
        sent = bool(
            dispatch_result.get("slack") or dispatch_result.get("email")
            or dispatch_result.get("dashboard")
        )
    except Exception as exc:  # noqa: BLE001
        dispatch_error = str(exc)[:200]
        logger.warning("backstop deferral dispatch_alert failed: %s", exc)

    if not sent:
        # Don't advance the re-alert suppression clock when delivery fails so
        # the next check retries.
        logger.error(
            "backstop deferral alert NOT delivered count=%d error=%s",
            len(to_alert), dispatch_error or "no_channel_accepted",
        )
        return {
            "deferred_count": len(deferred),
            "alert_sent": False,
            "reason": "dispatch_failed",
            "dispatch_error": dispatch_error or "no_channel_accepted",
        }

    for e in to_alert:
        await db[_BACKSTOP_ALERT_COLL].update_one(
            {"backstop": e["name"]},
            {"$set": {"last_alert_at": now_iso,
                      "last_alert_deferred_hours": e["deferred_hours"]}},
            upsert=True,
        )
    logger.warning(
        "backstop deferral alert dispatched count=%d backstops=%s",
        len(to_alert), [e["name"] for e in to_alert],
    )
    return {
        "deferred_count": len(deferred),
        "alert_sent": True,
        "alerted": [e["name"] for e in to_alert],
        "cleared": cleared,
    }


@celery_app.task(name='celery_tasks.hrv2_retention_cleanup_task')
def hrv2_retention_cleanup_task():
    """Clean up old shadow automation data per retention policy."""
    return asyncio.run(_hrv2_retention_cleanup_async())

async def _hrv2_retention_cleanup_async():
    """Async HRv2 retention cleanup."""
    try:
        from channel_manager.connectors.hotelrunner_v2.shadow_automation import cleanup_old_data
        result = await cleanup_old_data()
        logger.info("HRv2 retention cleanup: %s", result)
        return {'success': True, **result}
    except Exception as e:
        logger.error(f"HRv2 retention cleanup failed: {e}")
        return {'success': False, 'error': str(e)}
