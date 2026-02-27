#!/usr/bin/env python3
"""
Redis Cache Performance Test for Hotel PMS
Tests the 5 critical cached endpoints for performance improvements
"""

import asyncio
import aiohttp
import time
import json
import redis
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Configuration
BACKEND_URL = "https://pms-feature-test.preview.emergentagent.com/api"
REDIS_URL = "redis://localhost:6379/0"

# Test endpoints with their cache TTL
CACHED_ENDPOINTS = {
    "/pms/dashboard": {"ttl": 300, "description": "PMS Dashboard"},
    "/housekeeping/room-status": {"ttl": 60, "description": "Housekeeping Room Status"},
    "/dashboard/role-based": {"ttl": 300, "description": "Role-based Dashboard"},
    "/dashboard/employee-performance": {"ttl": 600, "description": "Employee Performance"},
    "/dashboard/guest-satisfaction-trends": {"ttl": 600, "description": "Guest Satisfaction Trends"}
}

class RedisCachePerformanceTest:
    def __init__(self):
        self.session = None
        self.redis_client = None
        self.auth_token = None
        self.results = {}
        
    async def setup(self):
        """Setup test environment"""
        print("🔧 Setting up Redis Cache Performance Test...")
        
        # Setup HTTP session
        self.session = aiohttp.ClientSession()
        
        # Setup Redis client
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            print("✅ Redis connection established")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False
            
        # Authenticate
        await self.authenticate()
        return True
        
    async def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        
        login_data = {
            "email": "admin@hotel.com",
            "password": "admin123"
        }
        
        try:
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get("access_token")
                    print("✅ Authentication successful")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
            
    async def clear_cache(self):
        """Clear Redis cache to ensure clean test"""
        try:
            # Clear all cache keys
            keys = self.redis_client.keys("cache:*")
            if keys:
                self.redis_client.delete(*keys)
                print(f"🧹 Cleared {len(keys)} cache keys")
            else:
                print("🧹 No cache keys to clear")
        except Exception as e:
            print(f"⚠️ Cache clear error: {e}")
            
    async def get_redis_stats(self) -> Dict:
        """Get Redis statistics"""
        try:
            info = self.redis_client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "total_keys": self.redis_client.dbsize(),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }
        except Exception as e:
            print(f"⚠️ Redis stats error: {e}")
            return {}
            
    async def make_request(self, endpoint: str) -> Tuple[float, int, Dict]:
        """Make HTTP request and measure response time"""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        start_time = time.time()
        try:
            async with self.session.get(f"{BACKEND_URL}{endpoint}", headers=headers) as response:
                response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                status = response.status
                data = await response.json() if response.status == 200 else {}
                return response_time, status, data
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            print(f"⚠️ Request error for {endpoint}: {e}")
            return response_time, 500, {}
            
    async def test_endpoint_performance(self, endpoint: str, config: Dict) -> Dict:
        """Test cache performance for a specific endpoint"""
        print(f"\n📊 Testing {config['description']} ({endpoint})")
        
        results = {
            "endpoint": endpoint,
            "description": config["description"],
            "ttl": config["ttl"],
            "calls": [],
            "cache_miss_time": 0,
            "cache_hit_times": [],
            "performance_improvement": 0,
            "cache_working": False
        }
        
        # Get initial Redis stats
        initial_stats = await self.get_redis_stats()
        initial_hits = initial_stats.get("keyspace_hits", 0)
        initial_misses = initial_stats.get("keyspace_misses", 0)
        
        # Call 1: Cache miss (should be slower)
        print("  📞 Call 1 (Cache Miss)...")
        time1, status1, data1 = await self.make_request(endpoint)
        results["calls"].append({
            "call": 1,
            "response_time_ms": round(time1, 2),
            "status": status1,
            "cache_expected": "miss"
        })
        results["cache_miss_time"] = time1
        
        if status1 != 200:
            print(f"  ❌ Call 1 failed with status {status1}")
            return results
            
        # Small delay to ensure cache is set
        await asyncio.sleep(0.1)
        
        # Call 2: Cache hit (should be faster)
        print("  📞 Call 2 (Cache Hit)...")
        time2, status2, data2 = await self.make_request(endpoint)
        results["calls"].append({
            "call": 2,
            "response_time_ms": round(time2, 2),
            "status": status2,
            "cache_expected": "hit"
        })
        results["cache_hit_times"].append(time2)
        
        # Call 3: Cache hit (should be faster)
        print("  📞 Call 3 (Cache Hit)...")
        time3, status3, data3 = await self.make_request(endpoint)
        results["calls"].append({
            "call": 3,
            "response_time_ms": round(time3, 2),
            "status": status3,
            "cache_expected": "hit"
        })
        results["cache_hit_times"].append(time3)
        
        # Calculate performance improvement
        if results["cache_hit_times"]:
            avg_cache_hit_time = sum(results["cache_hit_times"]) / len(results["cache_hit_times"])
            if results["cache_miss_time"] > 0:
                improvement = ((results["cache_miss_time"] - avg_cache_hit_time) / results["cache_miss_time"]) * 100
                results["performance_improvement"] = round(improvement, 1)
                results["avg_cache_hit_time"] = round(avg_cache_hit_time, 2)
        
        # Check if cache is working (subsequent calls should be faster)
        if len(results["cache_hit_times"]) >= 2:
            avg_hit_time = sum(results["cache_hit_times"]) / len(results["cache_hit_times"])
            results["cache_working"] = avg_hit_time < results["cache_miss_time"] * 0.8  # At least 20% improvement
        
        # Get final Redis stats
        final_stats = await self.get_redis_stats()
        final_hits = final_stats.get("keyspace_hits", 0)
        final_misses = final_stats.get("keyspace_misses", 0)
        
        results["redis_stats"] = {
            "hits_increase": final_hits - initial_hits,
            "misses_increase": final_misses - initial_misses,
            "total_keys": final_stats.get("total_keys", 0)
        }
        
        # Print results
        print(f"  ⏱️  Cache Miss Time: {round(time1, 2)}ms")
        print(f"  ⏱️  Cache Hit Times: {[round(t, 2) for t in results['cache_hit_times']]}ms")
        print(f"  📈 Performance Improvement: {results['performance_improvement']}%")
        print(f"  🎯 Cache Working: {'✅' if results['cache_working'] else '❌'}")
        
        return results
        
    async def test_cache_keys(self):
        """Test that cache keys are being created correctly"""
        print("\n🔑 Testing Cache Key Creation...")
        
        # Get all cache keys
        cache_keys = self.redis_client.keys("cache:*")
        print(f"📊 Total cache keys found: {len(cache_keys)}")
        
        # Group keys by prefix
        key_groups = {}
        for key in cache_keys:
            parts = key.split(":")
            if len(parts) >= 3:
                prefix = parts[2]  # cache:tenant_id:prefix:hash
                if prefix not in key_groups:
                    key_groups[prefix] = []
                key_groups[prefix].append(key)
        
        print("📋 Cache keys by prefix:")
        for prefix, keys in key_groups.items():
            print(f"  {prefix}: {len(keys)} keys")
            for key in keys[:3]:  # Show first 3 keys
                ttl = self.redis_client.ttl(key)
                print(f"    {key} (TTL: {ttl}s)")
                
        return key_groups
        
    async def calculate_cache_hit_rate(self) -> Dict:
        """Calculate overall cache hit rate"""
        try:
            info = self.redis_client.info()
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            
            if total > 0:
                hit_rate = (hits / total) * 100
            else:
                hit_rate = 0
                
            return {
                "hits": hits,
                "misses": misses,
                "total_requests": total,
                "hit_rate_percent": round(hit_rate, 2)
            }
        except Exception as e:
            print(f"⚠️ Cache hit rate calculation error: {e}")
            return {}
            
    async def run_performance_test(self):
        """Run complete performance test"""
        print("🚀 Starting Redis Cache Performance Test")
        print("=" * 60)
        
        # Setup
        if not await self.setup():
            return False
            
        # Clear cache for clean test
        await self.clear_cache()
        
        # Test each endpoint
        all_results = []
        for endpoint, config in CACHED_ENDPOINTS.items():
            result = await self.test_endpoint_performance(endpoint, config)
            all_results.append(result)
            
        # Test cache keys
        cache_keys = await self.test_cache_keys()
        
        # Calculate overall cache hit rate
        hit_rate_stats = await self.calculate_cache_hit_rate()
        
        # Generate summary report
        await self.generate_report(all_results, cache_keys, hit_rate_stats)
        
        return True
        
    async def generate_report(self, results: List[Dict], cache_keys: Dict, hit_rate_stats: Dict):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("📊 REDIS CACHE PERFORMANCE TEST REPORT")
        print("=" * 60)
        
        # Overall statistics
        total_endpoints = len(results)
        working_cache = sum(1 for r in results if r["cache_working"])
        avg_improvement = sum(r["performance_improvement"] for r in results if r["performance_improvement"] > 0) / max(1, len([r for r in results if r["performance_improvement"] > 0]))
        
        print(f"\n📈 OVERALL PERFORMANCE:")
        print(f"  Total Endpoints Tested: {total_endpoints}")
        print(f"  Endpoints with Working Cache: {working_cache}/{total_endpoints}")
        print(f"  Average Performance Improvement: {round(avg_improvement, 1)}%")
        
        # Cache hit rate
        if hit_rate_stats:
            print(f"\n🎯 CACHE HIT RATE:")
            print(f"  Total Requests: {hit_rate_stats.get('total_requests', 0)}")
            print(f"  Cache Hits: {hit_rate_stats.get('hits', 0)}")
            print(f"  Cache Misses: {hit_rate_stats.get('misses', 0)}")
            print(f"  Hit Rate: {hit_rate_stats.get('hit_rate_percent', 0)}%")
            
            hit_rate = hit_rate_stats.get('hit_rate_percent', 0)
            if hit_rate >= 80:
                print("  Status: ✅ EXCELLENT (>80%)")
            elif hit_rate >= 70:
                print("  Status: ✅ GOOD (>70%)")
            elif hit_rate >= 50:
                print("  Status: ⚠️ FAIR (>50%)")
            else:
                print("  Status: ❌ POOR (<50%)")
        
        # Detailed endpoint results
        print(f"\n📋 DETAILED ENDPOINT RESULTS:")
        for result in results:
            status = "✅ WORKING" if result["cache_working"] else "❌ NOT WORKING"
            print(f"\n  {result['description']} ({result['endpoint']}):")
            print(f"    Cache Status: {status}")
            print(f"    TTL: {result['ttl']} seconds")
            print(f"    Cache Miss Time: {round(result['cache_miss_time'], 2)}ms")
            if result["cache_hit_times"]:
                avg_hit = sum(result["cache_hit_times"]) / len(result["cache_hit_times"])
                print(f"    Avg Cache Hit Time: {round(avg_hit, 2)}ms")
            print(f"    Performance Improvement: {result['performance_improvement']}%")
            
            # Redis stats for this endpoint
            if "redis_stats" in result:
                stats = result["redis_stats"]
                print(f"    Redis Hits Increase: {stats.get('hits_increase', 0)}")
                print(f"    Redis Misses Increase: {stats.get('misses_increase', 0)}")
        
        # Cache keys summary
        print(f"\n🔑 CACHE KEYS SUMMARY:")
        total_keys = sum(len(keys) for keys in cache_keys.values())
        print(f"  Total Cache Keys: {total_keys}")
        for prefix, keys in cache_keys.items():
            print(f"    {prefix}: {len(keys)} keys")
        
        # Final assessment
        print(f"\n🏆 FINAL ASSESSMENT:")
        if working_cache == total_endpoints and avg_improvement >= 40:
            print("  ✅ EXCELLENT: All endpoints cached with significant performance improvement")
        elif working_cache >= total_endpoints * 0.8 and avg_improvement >= 30:
            print("  ✅ GOOD: Most endpoints cached with good performance improvement")
        elif working_cache >= total_endpoints * 0.6:
            print("  ⚠️ FAIR: Some endpoints cached but needs improvement")
        else:
            print("  ❌ POOR: Cache not working effectively")
            
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        if avg_improvement < 40:
            print("  - Consider optimizing cache keys and TTL values")
        if hit_rate_stats.get('hit_rate_percent', 0) < 70:
            print("  - Increase cache TTL for frequently accessed data")
        if working_cache < total_endpoints:
            print("  - Debug non-working cache endpoints")
        print("  - Monitor cache performance in production")
        
    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
        print("🧹 Cleanup completed")

async def main():
    """Main test function"""
    test = RedisCachePerformanceTest()
    try:
        success = await test.run_performance_test()
        return success
    finally:
        await test.cleanup()

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)