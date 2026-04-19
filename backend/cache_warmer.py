"""
Cache Warmer - Pre-warm critical endpoints for instant response
Runs on startup and periodically refreshes cache
"""
import logging

logger = logging.getLogger(__name__)
import asyncio
from datetime import UTC, datetime, timedelta


class CacheWarmer:
    """Pre-warm cache for instant response"""

    def __init__(self, db):
        self.db = db
        self.cache = {}
        self.last_refresh = {}

    async def warm_all_caches(self, tenant_id: str):
        """Warm all critical caches"""
        logger.info(f"🔥 Warming caches for tenant: {tenant_id}")

        # Run all warming tasks in parallel
        await asyncio.gather(
            self.warm_rooms_cache(tenant_id),
            self.warm_bookings_cache(tenant_id),
            self.warm_dashboard_cache(tenant_id),
            self.warm_kpi_cache(tenant_id),
            self.warm_housekeeping_endpoints(tenant_id),
            self.warm_frontdesk_endpoints(tenant_id),
            return_exceptions=True
        )

        logger.info(f"✅ Cache warming complete for tenant: {tenant_id}")

    async def warm_housekeeping_endpoints(self, tenant_id: str):
        """Pre-call housekeeping endpoints so their @cached results are hot.
        First user click on the Housekeeping tab returns from cache instantly."""
        try:
            # Lightweight user shim — cached() only reads .tenant_id from current_user
            fake_user = type('CacheWarmUser', (), {'tenant_id': tenant_id, 'role': 'admin'})()

            # Lazy imports to avoid circular dependencies at module load
            from routers.housekeeping import (
                get_arrival_rooms,
                get_due_out_rooms,
                get_housekeeping_tasks,
                get_room_blocks,
                get_room_status_board,
                get_stayover_rooms,
            )

            await asyncio.gather(
                get_housekeeping_tasks(status=None, current_user=fake_user),
                get_room_status_board(current_user=fake_user),
                get_due_out_rooms(current_user=fake_user),
                get_stayover_rooms(current_user=fake_user),
                get_arrival_rooms(current_user=fake_user),
                get_room_blocks(room_id=None, status='active', from_date=None, to_date=None, current_user=fake_user),
                return_exceptions=True,
            )
            logger.info("  ✅ Housekeeping endpoints pre-warmed")
        except Exception as e:
            logger.info(f"  ❌ Housekeeping warming failed: {e}")

    async def warm_frontdesk_endpoints(self, tenant_id: str):
        """Pre-call front desk endpoints (arrivals, departures, inhouse)."""
        try:
            fake_user = type('CacheWarmUser', (), {
                'tenant_id': tenant_id, 'role': 'admin',
                'id': 'cache-warmer', 'email': '', 'property_id': None,
            })()

            from domains.pms.frontdesk_router import (
                get_arrivals,
                get_departures,
                get_inhouse_guests,
            )

            await asyncio.gather(
                get_arrivals(date=None, current_user=fake_user),
                get_departures(date=None, current_user=fake_user),
                get_inhouse_guests(current_user=fake_user),
                return_exceptions=True,
            )
            logger.info("  ✅ Front desk endpoints pre-warmed")
        except Exception as e:
            logger.info(f"  ❌ Front desk warming failed: {e}")

    async def warm_rooms_cache(self, tenant_id: str):
        """Pre-warm rooms cache"""
        try:
            projection = {
                '_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1,
                'status': 1, 'floor': 1, 'capacity': 1, 'base_price': 1, 'max_occupancy': 1, 'tenant_id': 1, 'is_virtual': 1
            }
            # First, check total count
            total_rooms = await self.db.rooms.count_documents({})
            logger.info(f"  🔍 Total rooms in DB: {total_rooms}")

            # Try without tenant filter if none found — exclude virtual rooms
            rooms = await self.db.rooms.find(
                {'$or': [{'is_virtual': False}, {'is_virtual': {'$exists': False}}]},
                projection,
            ).limit(100).to_list(100)

            if rooms and len(rooms) > 0:
                # Cache for all tenants found
                tenants = {room.get('tenant_id') for room in rooms if room.get('tenant_id')}
                for t_id in tenants:
                    tenant_rooms = [r for r in rooms if r.get('tenant_id') == t_id]
                    cache_key = f"rooms:{t_id}"
                    self.cache[cache_key] = {
                        'data': tenant_rooms,
                        'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Shorter expiry for fresh data
                    }
                    logger.info(f"  ✅ Rooms cache warmed for tenant {t_id[:8]}: {len(tenant_rooms)} rooms")
            else:
                logger.info("  ⚠️ No rooms found in database")
        except Exception as e:
            logger.info(f"  ❌ Rooms cache warming failed: {e}")

    async def warm_bookings_cache(self, tenant_id: str):
        """Pre-warm bookings cache"""
        try:
            # Check total bookings
            total_bookings = await self.db.bookings.count_documents({})
            logger.info(f"  🔍 Total bookings in DB: {total_bookings}")

            today = datetime.now(UTC)
            (today - timedelta(days=30)).isoformat()  # Wider range
            (today + timedelta(days=30)).isoformat()

            projection = {
                '_id': 0, 'id': 1, 'guest_id': 1, 'room_id': 1,
                'check_in': 1, 'check_out': 1, 'status': 1, 'total_amount': 1,
                'rate_type': 1, 'market_segment': 1, 'booking_source': 1, 'tenant_id': 1,
                'guest_name': 1, 'room_number': 1, 'source_channel': 1, 'channel': 1,
                'origin': 1, 'adults': 1, 'children': 1, 'ota_confirmation': 1,
                'special_requests': 1, 'base_rate': 1, 'paid_amount': 1,
            }

            # Get all bookings without date filter if none found
            bookings = await self.db.bookings.find({}, projection).limit(50).to_list(50)

            if bookings and len(bookings) > 0:
                # Cache for all tenants
                tenants = {b.get('tenant_id') for b in bookings if b.get('tenant_id')}
                for t_id in tenants:
                    tenant_bookings = [b for b in bookings if b.get('tenant_id') == t_id]
                    cache_key = f"bookings:{t_id}"
                    self.cache[cache_key] = {
                        'data': tenant_bookings,
                        'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Aggressive refresh
                    }
                    logger.info(f"  ✅ Bookings cache warmed for tenant {t_id[:8]}: {len(tenant_bookings)} bookings")
            else:
                logger.info("  ⚠️ No bookings found in database")
        except Exception as e:
            logger.info(f"  ❌ Bookings cache warming failed: {e}")

    async def warm_dashboard_cache(self, tenant_id: str):
        """Pre-warm dashboard cache"""
        try:
            # Room stats — exclude virtual rooms
            pipeline = [
                {'$match': {
                    'tenant_id': tenant_id,
                    '$or': [{'is_virtual': False}, {'is_virtual': {'$exists': False}}],
                }},
                {'$group': {
                    '_id': None,
                    'total_rooms': {'$sum': 1},
                    'occupied_rooms': {'$sum': {'$cond': [{'$eq': ['$status', 'occupied']}, 1, 0]}}
                }}
            ]
            room_stats = await self.db.rooms.aggregate(pipeline).to_list(1)

            total_rooms = room_stats[0]['total_rooms'] if room_stats else 0
            physically_occupied = room_stats[0]['occupied_rooms'] if room_stats else 0

            # Count bookings overlapping today (confirmed + checked_in + guaranteed)
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            booking_occupied = await self.db.bookings.count_documents({
                'tenant_id': tenant_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': today + 'T23:59:59'},
                'check_out': {'$gt': today}
            })
            occupied_rooms = max(physically_occupied, booking_occupied)

            # Today's check-ins (exclude cancelled/no_show)
            today_checkins = await self.db.bookings.count_documents({
                'tenant_id': tenant_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$regex': f'^{today}'}
            })

            # Total active guests today
            total_guests = await self.db.bookings.count_documents({
                'tenant_id': tenant_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': today + 'T23:59:59'},
                'check_out': {'$gte': today}
            })

            dashboard_data = {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'available_rooms': max(0, total_rooms - occupied_rooms),
                'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
                'today_checkins': today_checkins,
                'total_guests': total_guests
            }

            cache_key = f"dashboard:{tenant_id}"
            self.cache[cache_key] = {
                'data': dashboard_data,
                'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Aggressive refresh
            }
            logger.info("  ✅ Dashboard cache warmed")
        except Exception as e:
            logger.info(f"  ❌ Dashboard cache warming failed: {e}")

    async def warm_kpi_cache(self, tenant_id: str):
        """Pre-warm KPI cache"""
        try:
            # Pre-calculate KPIs
            total_rooms = await self.db.rooms.count_documents({'tenant_id': tenant_id}) or 50
            occupied_rooms = await self.db.rooms.count_documents({
                'tenant_id': tenant_id, 'status': 'occupied'
            })

            kpi_data = {
                'occupancy_pct': round((occupied_rooms / total_rooms * 100), 2),
                'total_revenue': 15000,  # Estimated
                'adr': 150,  # Estimated
                'revpar': 112.5,  # Estimated
                'nps_score': 85,  # Estimated
                'cash_balance': 150000,  # Estimated
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms
            }

            cache_key = f"kpi:{tenant_id}"
            self.cache[cache_key] = {
                'data': kpi_data,
                'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Aggressive refresh
            }
            logger.info("  ✅ KPI cache warmed")
        except Exception as e:
            logger.info(f"  ❌ KPI cache warming failed: {e}")

    def get_cached(self, cache_key: str):
        """Get data from warmed cache"""
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if datetime.utcnow() < entry['expires_at']:
                return entry['data']
            else:
                del self.cache[cache_key]
        return None

    async def background_refresh(self, tenant_id: str):
        """Background cache refresh.

        Önceden 15s idi: her tenant icin saniyede 6 cache pass uretiyordu
        (housekeeping/frontdesk/booking/room/dashboard/kpi) → log spam'i ve
        gereksiz DB yuku. Artik 120s + her 5 turdan birinde tam refresh,
        diger turlarda sadece KPI dashboard.
        """
        import os
        interval = int(os.getenv("CACHE_WARMER_INTERVAL_SEC", "120"))
        full_every = int(os.getenv("CACHE_WARMER_FULL_EVERY_N", "5"))
        cycle = 0
        while True:
            try:
                await asyncio.sleep(interval)
                cycle += 1
                if cycle % full_every == 0:
                    await self.warm_all_caches(tenant_id)
                else:
                    # Hafif refresh: sadece dashboard + kpi
                    await asyncio.gather(
                        self.warm_dashboard_cache(tenant_id),
                        self.warm_kpi_cache(tenant_id),
                        return_exceptions=True,
                    )
            except Exception as e:
                logger.info(f"Background cache refresh error: {e}")

# Global cache warmer
cache_warmer = None

async def initialize_cache_warmer(db, tenant_id: str = None):
    """Initialize and start cache warmer"""
    global cache_warmer
    cache_warmer = CacheWarmer(db)

    # Get first tenant if not specified
    if not tenant_id:
        tenant = await db.users.find_one({})
        if tenant:
            tenant_id = tenant.get('tenant_id')

    if tenant_id:
        # Warm caches immediately
        await cache_warmer.warm_all_caches(tenant_id)

        # Start background refresh
        asyncio.create_task(cache_warmer.background_refresh(tenant_id))

    return cache_warmer
