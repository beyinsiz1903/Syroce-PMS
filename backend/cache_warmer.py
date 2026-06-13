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
            self.warm_guest_room_maps_cache(tenant_id),
            self.warm_dashboard_cache(tenant_id),
            self.warm_kpi_cache(tenant_id),
            self.warm_housekeeping_endpoints(tenant_id),
            self.warm_frontdesk_endpoints(tenant_id),
            return_exceptions=True
        )

        logger.info(f"✅ Cache warming complete for tenant: {tenant_id}")

    async def warm_guest_room_maps_cache(self, tenant_id: str):
        """Pre-build guest_id→name and room_id→{number,type} maps per tenant.

        Why: the bookings list endpoint (cache-hit path) needs to enrich
        each booking row with guest_name and room_number. Doing that as
        two batched Atlas round-trips per request adds ~500ms (Atlas is
        cross-region). Pre-building these maps once and serving from RAM
        cuts the bookings endpoint from ~1.8s to ~200ms.

        TTL is short (20s) — same as the other warmed caches — so a
        renamed guest or renumbered room shows up within a few seconds.
        For instant invalidation after a mutation, callers can use
        :meth:`invalidate` with key ``guest_map:{tenant_id}`` /
        ``room_map:{tenant_id}``.
        """
        try:
            # Guests: project the minimum we need to compute a display name
            guest_map: dict[str, str] = {}
            async for g in self.db.guests.find(
                {'tenant_id': tenant_id},
                {'_id': 0, 'id': 1, 'name': 1, 'first_name': 1, 'last_name': 1},
            ):
                gid = g.get('id')
                if not gid:
                    continue
                nm = g.get('name') or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
                # Walk-in placeholder ("C4", "V4 Refund", "X" gibi) reddet — caller
                # boyle bir id icin map'te bulamadiginda display fallback ("Misafir
                # <SHORTID>") devreye girer.
                from core.guest_name_utils import is_placeholder_guest_name
                if nm and not is_placeholder_guest_name(nm):
                    guest_map[gid] = nm

            # Rooms: project number + type for the booking row
            room_map: dict[str, dict] = {}
            async for r in self.db.rooms.find(
                {'tenant_id': tenant_id},
                {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1},
            ):
                rid = r.get('id')
                if not rid:
                    continue
                room_map[rid] = {
                    'room_number': r.get('room_number'),
                    'room_type': r.get('room_type'),
                }

            # TTL is generous (180s) so the entry stays warm BETWEEN the
            # background refresh cycles (default 120s). If TTL were shorter
            # than the refresh interval, every Nth request would miss the
            # cache and fall back to a slow Atlas round-trip — which is
            # exactly the regression we just fixed for the bookings list.
            self.cache[f"guest_map:{tenant_id}"] = {
                'data': guest_map,
                'expires_at': datetime.utcnow() + timedelta(seconds=180),
            }
            self.cache[f"room_map:{tenant_id}"] = {
                'data': room_map,
                'expires_at': datetime.utcnow() + timedelta(seconds=180),
            }
            logger.info(
                f"  ✅ Guest/Room maps warmed for tenant {tenant_id[:8]}: "
                f"{len(guest_map)} guests, {len(room_map)} rooms"
            )
        except Exception as e:
            logger.info(f"  ❌ Guest/Room map warming failed: {e}")

    def invalidate(self, *cache_keys: str) -> int:
        """Drop cache entries by key. Returns number of entries removed.

        Use after a mutation that would make a warmed entry stale (e.g.
        renaming a guest → ``invalidate(f"guest_map:{tenant_id}")``).
        Safe to call with keys that aren't present.
        """
        removed = 0
        for k in cache_keys:
            if k in self.cache:
                del self.cache[k]
                removed += 1
        return removed

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
                        # TTL=180s lives ONE refresh cycle longer than the
                        # 120s background interval, so the entry never goes
                        # cold between refreshes. Without this, every ~6th
                        # request would fall back to a 1.8s Atlas query.
                        'expires_at': datetime.utcnow() + timedelta(seconds=180)
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

            # Date-only overlap (matches AI briefing) — single source of truth.
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            bookings_today = await self.db.bookings.find(
                {
                    'tenant_id': tenant_id,
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                },
                {'_id': 0, 'check_in': 1, 'check_out': 1}
            ).to_list(5000)

            # v95 — Track unique active rooms (not booking count) so that
            # double-booked rooms or overlapping holds don't inflate occupancy.
            active_room_ids: set[str] = set()
            booking_occupied_count = 0  # for total_guests display
            today_checkins = 0
            for _i, b in enumerate(bookings_today):
                ci = str(b.get('check_in', ''))[:10]
                co = str(b.get('check_out', ''))[:10]
                rid = b.get('room_id')
                if ci <= today and co > today:
                    booking_occupied_count += 1
                    if rid:
                        active_room_ids.add(rid)
                if ci == today:
                    today_checkins += 1
                # Cooperative yield: this pass can iterate up to 5000 docs.
                # Run on the single uvicorn event loop that also serves the
                # SPA static chunks, an unbroken synchronous loop briefly
                # blocks the loop and surfaces as intermittent chunk 502s /
                # white screen. Yield control every 1024 iterations.
                if (_i & 0x3FF) == 0x3FF:
                    await asyncio.sleep(0)

            # Single source of truth: unique rooms with an overlapping booking.
            booking_occupied = len(active_room_ids)
            occupied_rooms = booking_occupied
            total_guests = booking_occupied_count
            if abs(physically_occupied - booking_occupied) >= 3:
                # v95 — Auto-reconcile: bring rooms.status in line with active bookings.
                # active_room_ids already computed above (unique rooms truth).
                try:
                    # Mark active rooms as occupied
                    if active_room_ids:
                        await self.db.rooms.update_many(
                            {
                                'tenant_id': tenant_id,
                                'id': {'$in': list(active_room_ids)},
                                'status': {'$ne': 'occupied'},
                            },
                            {'$set': {'status': 'occupied',
                                      'status_synced_at': datetime.now(UTC).isoformat()}},
                        )
                    # Free rooms previously marked occupied that are no longer in any booking
                    await self.db.rooms.update_many(
                        {
                            'tenant_id': tenant_id,
                            'status': 'occupied',
                            'id': {'$nin': list(active_room_ids)} if active_room_ids else {'$exists': True},
                            '$or': [{'is_virtual': False}, {'is_virtual': {'$exists': False}}],
                        },
                        {'$set': {'status': 'available',
                                  'status_synced_at': datetime.now(UTC).isoformat()}},
                    )
                    logger.info(
                        "[OCCUPANCY-RECONCILE] tenant=%s reconciled rooms.status to %d active bookings (was %d marked occupied)",
                        tenant_id, len(active_room_ids), physically_occupied,
                    )
                except Exception as recon_err:
                    logger.warning(
                        "[OCCUPANCY-DRIFT] tenant=%s drift=%d but auto-reconcile failed: %s",
                        tenant_id, abs(physically_occupied - booking_occupied), recon_err,
                    )

            # Tenant currency for unified display.
            try:
                from core.tenant_currency import get_tenant_currency
                cur_code, cur_sym = await get_tenant_currency(tenant_id)
            except Exception:
                cur_code, cur_sym = 'TRY', '\u20ba'

            dashboard_data = {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'available_rooms': max(0, total_rooms - occupied_rooms),
                'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
                'today_checkins': today_checkins,
                'total_guests': total_guests,
                'currency': cur_code,
                'currency_symbol': cur_sym,
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
                    # Hafif refresh: dashboard + kpi + bookings + guest/room
                    # maps. The latter three MUST be refreshed every cycle —
                    # otherwise their 180s TTL outlives the warm copy and
                    # the bookings endpoint goes cold every other minute.
                    await asyncio.gather(
                        self.warm_dashboard_cache(tenant_id),
                        self.warm_kpi_cache(tenant_id),
                        self.warm_bookings_cache(tenant_id),
                        self.warm_guest_room_maps_cache(tenant_id),
                        return_exceptions=True,
                    )
            except Exception as e:
                logger.info(f"Background cache refresh error: {e}")

# Global cache warmer
cache_warmer = None
# Single background-refresh task per process. initialize_cache_warmer is
# called from BOTH the d_perf and g_channels bootstrap phases; without this
# guard each call replaced the global warmer and spawned ANOTHER
# background_refresh loop via create_task — the prior loop was never
# cancelled, so duplicate warmer loops accumulated in the one uvicorn event
# loop, each doing cross-tenant scans + a synchronous pass over up to 5000
# bookings every 120s. On the combined deployment a single uvicorn worker
# serves BOTH the API and the static SPA chunks, so those piled-up loops
# starve the event loop: the edge proxy can't reach the worker and the SPA
# entry chunk 502s -> production white screen. Keep exactly one loop.
_cache_warmer_task = None

async def initialize_cache_warmer(db, tenant_id: str = None):
    """Initialize and start cache warmer (idempotent across bootstrap phases)."""
    global cache_warmer, _cache_warmer_task

    # If a background refresh loop is already running in this process, reuse
    # it instead of replacing the warmer and spawning a duplicate loop.
    if _cache_warmer_task is not None and not _cache_warmer_task.done():
        return cache_warmer

    cache_warmer = CacheWarmer(db)

    # Get first tenant if not specified
    if not tenant_id:
        tenant = await db.users.find_one({})
        if tenant:
            tenant_id = tenant.get('tenant_id')

    if tenant_id:
        # Warm caches immediately
        await cache_warmer.warm_all_caches(tenant_id)

        # Start the single background refresh loop
        _cache_warmer_task = asyncio.create_task(cache_warmer.background_refresh(tenant_id))

    return cache_warmer
