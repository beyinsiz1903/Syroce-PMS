"""
Celery Tasks for Background Processing
All long-running and periodic tasks
"""

import asyncio
import logging
import os
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


@celery_app.task(name='celery_tasks.night_audit_task')
def night_audit_task():
    """Run night audit for all tenants"""
    return asyncio.run(_night_audit_async())

async def _night_audit_async():
    """Async night audit implementation"""
    db, client = get_db()

    try:
        # Get all active tenants
        tenants = await db.users.distinct('tenant_id', {'active': True})

        results = []
        for tenant_id in tenants:
            try:
                # Post room charges for all checked-in bookings
                bookings = await db.bookings.find({
                    'tenant_id': tenant_id,
                    'status': 'checked_in'
                }).to_list(1000)

                charges_posted = 0
                for booking in bookings:
                    # Get room rate
                    room_rate = booking.get('total_amount', 0) / max(1, booking.get('nights', 1))

                    # Find guest folio
                    folio = await db.folios.find_one({
                        'tenant_id': tenant_id,
                        'booking_id': booking['booking_id'],
                        'folio_type': 'guest',
                        'status': 'open'
                    })

                    if folio:
                        # Post room charge
                        charge = {
                            'charge_id': f"CHG-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{charges_posted}",
                            'tenant_id': tenant_id,
                            'folio_id': folio['folio_id'],
                            'charge_category': 'room',
                            'description': f"Room charge - {booking.get('room_number', 'N/A')}",
                            'amount': room_rate,
                            'quantity': 1,
                            'unit_price': room_rate,
                            'tax_rate': 0.10,
                            'tax_amount': room_rate * 0.10,
                            'total': room_rate * 1.10,
                            'voided': False,
                            'created_at': datetime.now(UTC)
                        }

                        await db.folio_charges.insert_one(charge)
                        charges_posted += 1

                results.append({
                    'tenant_id': tenant_id,
                    'bookings_processed': len(bookings),
                    'charges_posted': charges_posted
                })

                logger.info(f"Night audit completed for tenant {tenant_id}: {charges_posted} charges posted")

            except Exception as e:
                logger.error(f"Night audit error for tenant {tenant_id}: {e}")
                results.append({
                    'tenant_id': tenant_id,
                    'error': str(e)
                })

        return {
            'success': True,
            'timestamp': datetime.now(UTC).isoformat(),
            'results': results
        }

    except Exception as e:
        logger.error(f"Night audit task failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.close()


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
    try:
        from core.database import db
        await db.rnl_auto_resolve_runs.insert_one({
            **summary,
            'actor_id': 'celery_beat',
            'limit': limit,
        })
    except Exception as exc:
        logger.warning("F8N rnl auto-resolve run history write failed: %s", exc)

    return summary


# State doc key: tracks the last manual_required alert so consecutive daily
# runs don't spam operators. Single fixed doc — this is a system-wide signal.
_RNL_ALERT_STATE_COLL = "rnl_duplicate_alert_state"
_RNL_ALERT_STATE_KEY = "manual_required"
# Re-alert when the manual_required count grows by at least this much above
# the last alerted value (so escalation gets a fresh ping even mid-streak).
_RNL_ALERT_ESCALATION_DELTA = 5


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
                }},
                upsert=True,
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

    await db[_RNL_ALERT_STATE_COLL].update_one(
        state_filter,
        {"$set": {
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
        }, "$unset": {
            "last_dispatch_failed_at": "",
            "last_dispatch_error": "",
        }},
        upsert=True,
    )

    return {
        'sent': True,
        'suppressed': False,
        'reason': 'escalated' if (escalated and streak_active) else 'first_detection',
        'current_count': count,
        'previous_alert_count': last_alert_count,
    }

    # Persist run summary so the super-admin panel can show history without
    # log-diving. Best-effort: a write failure must not fail the beat job.
    try:
        from core.database import db
        await db.rnl_auto_resolve_runs.insert_one({
            **summary,
            'actor_id': 'celery_beat',
            'limit': limit,
        })
    except Exception as exc:
        logger.warning("F8N rnl auto-resolve run history write failed: %s", exc)

    return summary


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
