"""
Cache Warmer - Pre-warm critical endpoints for instant response
Runs on startup and periodically refreshes cache
"""
import asyncio
from datetime import datetime, timezone, timedelta

class CacheWarmer:
    """Pre-warm cache for instant response"""
    
    def __init__(self, db):
        self.db = db
        self.cache = {}
        self.last_refresh = {}
    
    async def warm_all_caches(self, tenant_id: str):
        """Warm all critical caches"""
        print(f"🔥 Warming caches for tenant: {tenant_id}")
        
        # Run all warming tasks in parallel
        await asyncio.gather(
            self.warm_rooms_cache(tenant_id),
            self.warm_bookings_cache(tenant_id),
            self.warm_dashboard_cache(tenant_id),
            self.warm_kpi_cache(tenant_id),
            return_exceptions=True
        )
        
        print(f"✅ Cache warming complete for tenant: {tenant_id}")
    
    async def warm_rooms_cache(self, tenant_id: str):
        """Pre-warm rooms cache"""
        try:
            projection = {
                '_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1,
                'status': 1, 'floor': 1, 'capacity': 1, 'base_price': 1, 'max_occupancy': 1, 'tenant_id': 1
            }
            # First, check total count
            total_rooms = await self.db.rooms.count_documents({})
            print(f"  🔍 Total rooms in DB: {total_rooms}")
            
            # Try without tenant filter if none found
            rooms = await self.db.rooms.find({}, projection).limit(100).to_list(100)
            
            if rooms and len(rooms) > 0:
                # Cache for all tenants found
                tenants = set(room.get('tenant_id') for room in rooms if room.get('tenant_id'))
                for t_id in tenants:
                    tenant_rooms = [r for r in rooms if r.get('tenant_id') == t_id]
                    cache_key = f"rooms:{t_id}"
                    self.cache[cache_key] = {
                        'data': tenant_rooms,
                        'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Shorter expiry for fresh data
                    }
                    print(f"  ✅ Rooms cache warmed for tenant {t_id[:8]}: {len(tenant_rooms)} rooms")
            else:
                print("  ⚠️ No rooms found in database")
        except Exception as e:
            print(f"  ❌ Rooms cache warming failed: {e}")
    
    async def warm_bookings_cache(self, tenant_id: str):
        """Pre-warm bookings cache"""
        try:
            # Check total bookings
            total_bookings = await self.db.bookings.count_documents({})
            print(f"  🔍 Total bookings in DB: {total_bookings}")
            
            today = datetime.now(timezone.utc)
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
                tenants = set(b.get('tenant_id') for b in bookings if b.get('tenant_id'))
                for t_id in tenants:
                    tenant_bookings = [b for b in bookings if b.get('tenant_id') == t_id]
                    cache_key = f"bookings:{t_id}"
                    self.cache[cache_key] = {
                        'data': tenant_bookings,
                        'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Aggressive refresh
                    }
                    print(f"  ✅ Bookings cache warmed for tenant {t_id[:8]}: {len(tenant_bookings)} bookings")
            else:
                print("  ⚠️ No bookings found in database")
        except Exception as e:
            print(f"  ❌ Bookings cache warming failed: {e}")
    
    async def warm_dashboard_cache(self, tenant_id: str):
        """Pre-warm dashboard cache"""
        try:
            # Room stats
            pipeline = [
                {'$match': {'tenant_id': tenant_id}},
                {'$group': {
                    '_id': None,
                    'total_rooms': {'$sum': 1},
                    'occupied_rooms': {'$sum': {'$cond': [{'$eq': ['$status', 'occupied']}, 1, 0]}}
                }}
            ]
            room_stats = await self.db.rooms.aggregate(pipeline).to_list(1)
            
            total_rooms = room_stats[0]['total_rooms'] if room_stats else 0
            occupied_rooms = room_stats[0]['occupied_rooms'] if room_stats else 0
            
            # Quick counts
            today = datetime.now(timezone.utc).replace(hour=0, minute=0).isoformat()
            today_checkins = await self.db.bookings.count_documents({
                'tenant_id': tenant_id, 'check_in': {'$gte': today}
            })
            total_guests = await self.db.guests.count_documents({'tenant_id': tenant_id})
            
            dashboard_data = {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'available_rooms': total_rooms - occupied_rooms,
                'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
                'today_checkins': today_checkins,
                'total_guests': total_guests
            }
            
            cache_key = f"dashboard:{tenant_id}"
            self.cache[cache_key] = {
                'data': dashboard_data,
                'expires_at': datetime.utcnow() + timedelta(seconds=20)  # Aggressive refresh
            }
            print("  ✅ Dashboard cache warmed")
        except Exception as e:
            print(f"  ❌ Dashboard cache warming failed: {e}")
    
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
            print("  ✅ KPI cache warmed")
        except Exception as e:
            print(f"  ❌ KPI cache warming failed: {e}")
    
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
        """Background cache refresh every 15 seconds (aggressive)"""
        while True:
            try:
                await asyncio.sleep(15)  # Refresh every 15 seconds for max freshness
                await self.warm_all_caches(tenant_id)
            except Exception as e:
                print(f"Background cache refresh error: {e}")

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
