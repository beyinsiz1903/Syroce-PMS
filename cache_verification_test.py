#!/usr/bin/env python3
"""
Cache Verification Test - Multiple calls to verify cache hit rate
"""

import asyncio
import aiohttp
import time
import redis
from statistics import mean

BACKEND_URL = "https://guest-unified.preview.emergentagent.com/api"
REDIS_URL = "redis://localhost:6379/0"

async def test_cache_performance():
    """Test cache performance with multiple calls"""
    
    # Setup
    session = aiohttp.ClientSession()
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Authenticate
    login_data = {"email": "admin@hotel.com", "password": "admin123"}
    async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
        data = await response.json()
        token = data.get("access_token")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test endpoints
    endpoints = [
        "/pms/dashboard",
        "/housekeeping/room-status", 
        "/dashboard/role-based",
        "/dashboard/employee-performance",
        "/dashboard/guest-satisfaction-trends"
    ]
    
    print("🚀 Cache Performance Verification Test")
    print("=" * 50)
    
    # Clear cache
    redis_client.flushdb()
    print("🧹 Cache cleared")
    
    # Get initial stats
    initial_info = redis_client.info()
    initial_hits = initial_info.get('keyspace_hits', 0)
    initial_misses = initial_info.get('keyspace_misses', 0)
    
    # Test each endpoint with 5 calls
    for endpoint in endpoints:
        print(f"\n📊 Testing {endpoint}")
        times = []
        
        for i in range(5):
            start = time.time()
            async with session.get(f"{BACKEND_URL}{endpoint}", headers=headers) as response:
                await response.json()
                response_time = (time.time() - start) * 1000
                times.append(response_time)
                print(f"  Call {i+1}: {response_time:.2f}ms")
        
        # Calculate improvement
        first_call = times[0]
        subsequent_calls = times[1:]
        avg_subsequent = mean(subsequent_calls)
        improvement = ((first_call - avg_subsequent) / first_call) * 100
        
        print(f"  📈 First call (miss): {first_call:.2f}ms")
        print(f"  📈 Avg subsequent (hits): {avg_subsequent:.2f}ms") 
        print(f"  📈 Improvement: {improvement:.1f}%")
    
    # Final stats
    final_info = redis_client.info()
    final_hits = final_info.get('keyspace_hits', 0)
    final_misses = final_info.get('keyspace_misses', 0)
    
    total_hits = final_hits - initial_hits
    total_misses = final_misses - initial_misses
    total_requests = total_hits + total_misses
    hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
    
    print(f"\n🎯 FINAL CACHE STATISTICS:")
    print(f"  Total Requests: {total_requests}")
    print(f"  Cache Hits: {total_hits}")
    print(f"  Cache Misses: {total_misses}")
    print(f"  Hit Rate: {hit_rate:.1f}%")
    
    # Check cache keys
    cache_keys = redis_client.keys("cache:*")
    print(f"  Cache Keys Created: {len(cache_keys)}")
    
    await session.close()
    
    return hit_rate >= 70  # Target hit rate

if __name__ == "__main__":
    success = asyncio.run(test_cache_performance())
    print(f"\n✅ Cache test {'PASSED' if success else 'FAILED'}")