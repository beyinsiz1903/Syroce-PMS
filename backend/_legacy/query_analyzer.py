"""
Database Query Analyzer
Analyzes and reports on slow queries, index usage, and optimization opportunities
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime
import json

class QueryAnalyzer:
    """Analyze database queries for performance optimization"""
    
    def __init__(self):
        mongo_url = os.environ.get('MONGO_URL')
        db_name = os.environ.get('DB_NAME')
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        
    async def enable_profiling(self, level=1, slow_ms=100):
        """
        Enable database profiling
        Level 0: Off
        Level 1: Slow operations only
        Level 2: All operations
        """
        try:
            await self.db.command('profile', level, slowms=slow_ms)
            print(f"✅ Profiling enabled (level={level}, slow_ms={slow_ms})")
            return True
        except Exception as e:
            print(f"❌ Failed to enable profiling: {e}")
            return False
    
    async def get_slow_queries(self, limit=20):
        """Get slowest queries from system.profile"""
        try:
            queries = await self.db.system.profile.find({
                'millis': {'$gt': 100}
            }).sort('millis', -1).limit(limit).to_list(limit)
            
            print(f"\n🐌 TOP {len(queries)} SLOW QUERIES")
            print("=" * 80)
            
            for i, query in enumerate(queries, 1):
                print(f"\n#{i} - Duration: {query.get('millis', 0)}ms")
                print(f"  Operation: {query.get('op', 'unknown')}")
                print(f"  Namespace: {query.get('ns', 'unknown')}")
                print(f"  Query: {json.dumps(query.get('command', {}), indent=2)[:200]}")
                print(f"  Timestamp: {query.get('ts', 'unknown')}")
                
                # Check if index was used
                if 'planSummary' in query:
                    print(f"  Plan: {query['planSummary']}")
                    if 'COLLSCAN' in query['planSummary']:
                        print("  ⚠️  WARNING: Collection scan detected!")
            
            return queries
            
        except Exception as e:
            print(f"❌ Failed to get slow queries: {e}")
            return []
    
    async def analyze_index_usage(self):
        """Analyze index usage across collections"""
        collections = [
            'bookings', 'rooms', 'guests', 'folios', 'folio_charges',
            'payments', 'housekeeping_tasks', 'users'
        ]
        
        print("\n📊 INDEX USAGE ANALYSIS")
        print("=" * 80)
        
        index_stats = {}
        
        for coll_name in collections:
            try:
                # Get index stats
                stats = await self.db.command('aggregate', coll_name, pipeline=[
                    {'$indexStats': {}}
                ], cursor={})
                
                indexes = stats.get('cursor', {}).get('firstBatch', [])
                
                if indexes:
                    print(f"\n📁 {coll_name}:")
                    index_stats[coll_name] = []
                    
                    for idx in indexes:
                        name = idx.get('name', 'unknown')
                        accesses = idx.get('accesses', {})
                        ops = accesses.get('ops', 0)
                        since = accesses.get('since', None)
                        
                        index_stats[coll_name].append({
                            'name': name,
                            'ops': ops,
                            'since': since
                        })
                        
                        print(f"  • {name}: {ops} operations")
                        
                        if ops == 0:
                            print("    ⚠️  WARNING: Unused index!")
                            
            except Exception as e:
                print(f"  ⚠️  Could not get index stats for {coll_name}: {e}")
        
        return index_stats
    
    async def analyze_collection_stats(self):
        """Get collection statistics"""
        collections = [
            'bookings', 'rooms', 'guests', 'folios', 'folio_charges',
            'payments', 'housekeeping_tasks', 'audit_logs'
        ]
        
        print("\n📦 COLLECTION STATISTICS")
        print("=" * 80)
        
        stats = {}
        
        for coll_name in collections:
            try:
                coll_stats = await self.db.command('collStats', coll_name)
                
                count = coll_stats.get('count', 0)
                size = coll_stats.get('size', 0)
                avg_obj_size = coll_stats.get('avgObjSize', 0)
                storage_size = coll_stats.get('storageSize', 0)
                indexes = coll_stats.get('nindexes', 0)
                total_index_size = coll_stats.get('totalIndexSize', 0)
                
                stats[coll_name] = {
                    'count': count,
                    'size_mb': round(size / (1024 * 1024), 2),
                    'avg_obj_size_kb': round(avg_obj_size / 1024, 2),
                    'storage_size_mb': round(storage_size / (1024 * 1024), 2),
                    'indexes': indexes,
                    'index_size_mb': round(total_index_size / (1024 * 1024), 2)
                }
                
                print(f"\n📁 {coll_name}:")
                print(f"  Documents: {count:,}")
                print(f"  Data Size: {stats[coll_name]['size_mb']} MB")
                print(f"  Avg Doc Size: {stats[coll_name]['avg_obj_size_kb']} KB")
                print(f"  Storage Size: {stats[coll_name]['storage_size_mb']} MB")
                print(f"  Indexes: {indexes} ({stats[coll_name]['index_size_mb']} MB)")
                
                # Recommendations
                if count > 100000:
                    print("  💡 Large collection - consider archival strategy")
                
                if total_index_size > size:
                    print("  ⚠️  Index size exceeds data size - review indexes")
                    
            except Exception as e:
                print(f"  ⚠️  Could not get stats for {coll_name}: {e}")
        
        return stats
    
    async def find_missing_indexes(self):
        """Identify potential missing indexes based on common query patterns"""
        print("\n🔍 MISSING INDEX ANALYSIS")
        print("=" * 80)
        
        recommendations = []
        
        # Analyze bookings
        print("\n📁 Analyzing bookings collection...")
        
        # Check for queries without indexes
        explain = await self.db.bookings.find({
            'status': 'confirmed'
        }).explain()
        
        if 'COLLSCAN' in str(explain):
            recommendations.append({
                'collection': 'bookings',
                'field': 'status',
                'reason': 'Collection scan detected for status queries'
            })
            print("  ⚠️  Recommendation: Add index on 'status'")
        
        # Check compound queries
        explain = await self.db.bookings.find({
            'tenant_id': 'test',
            'check_in': {'$gte': datetime.now()}
        }).explain()
        
        if 'COLLSCAN' in str(explain):
            recommendations.append({
                'collection': 'bookings',
                'field': 'tenant_id + check_in',
                'reason': 'Collection scan for date range queries'
            })
            print("  ⚠️  Recommendation: Add compound index on tenant_id + check_in")
        
        return recommendations
    
    async def generate_optimization_report(self):
        """Generate comprehensive optimization report"""
        print("\n" + "=" * 80)
        print("📊 DATABASE OPTIMIZATION REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Enable profiling
        await self.enable_profiling(level=1, slow_ms=100)
        
        # Collect data
        slow_queries = await self.get_slow_queries(limit=10)
        index_usage = await self.analyze_index_usage()
        collection_stats = await self.analyze_collection_stats()
        missing_indexes = await self.find_missing_indexes()
        
        # Summary
        print("\n📋 SUMMARY")
        print("=" * 80)
        print(f"  Slow Queries (>100ms): {len(slow_queries)}")
        print(f"  Collections Analyzed: {len(collection_stats)}")
        print(f"  Index Recommendations: {len(missing_indexes)}")
        
        # Top recommendations
        print("\n💡 TOP RECOMMENDATIONS")
        print("=" * 80)
        
        if len(slow_queries) > 0:
            print(f"  1. Optimize {len(slow_queries)} slow queries")
        
        unused_indexes = 0
        for coll, indexes in index_usage.items():
            for idx in indexes:
                if idx['ops'] == 0:
                    unused_indexes += 1
        
        if unused_indexes > 0:
            print(f"  2. Remove {unused_indexes} unused indexes")
        
        if len(missing_indexes) > 0:
            print(f"  3. Add {len(missing_indexes)} recommended indexes")
        
        large_collections = [
            name for name, stats in collection_stats.items()
            if stats['count'] > 100000
        ]
        
        if large_collections:
            print(f"  4. Consider archival for {len(large_collections)} large collections")
        
        print("\n" + "=" * 80)
        print("✅ Analysis Complete!")
        print("=" * 80)
        
        await self.client.close()

async def main():
    """Run query analyzer"""
    analyzer = QueryAnalyzer()
    await analyzer.generate_optimization_report()

if __name__ == "__main__":
    asyncio.run(main())
