"""
Monitoring and Health Check System
Performance tracking, metrics, and system health
"""

from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Dict, Any, List
import psutil
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

monitoring_router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])


class SystemMonitor:
    """System performance monitor"""
    
    @staticmethod
    def get_cpu_usage() -> float:
        """Get CPU usage percentage"""
        return psutil.cpu_percent(interval=0)  # Instant reading for fast response
    
    @staticmethod
    def get_memory_usage() -> Dict[str, Any]:
        """Get memory usage stats"""
        mem = psutil.virtual_memory()
        return {
            'total': mem.total,
            'available': mem.available,
            'used': mem.used,
            'percent': mem.percent,
            'total_gb': round(mem.total / (1024**3), 2),
            'available_gb': round(mem.available / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2)
        }
    
    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """Get disk usage stats"""
        disk = psutil.disk_usage('/')
        return {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent,
            'total_gb': round(disk.total / (1024**3), 2),
            'used_gb': round(disk.used / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2)
        }
    
    @staticmethod
    def get_network_io() -> Dict[str, Any]:
        """Get network I/O stats"""
        net = psutil.net_io_counters()
        return {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
            'mb_sent': round(net.bytes_sent / (1024**2), 2),
            'mb_recv': round(net.bytes_recv / (1024**2), 2)
        }
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get overall system information"""
        return {
            'cpu_count': psutil.cpu_count(),
            'cpu_usage': SystemMonitor.get_cpu_usage(),
            'memory': SystemMonitor.get_memory_usage(),
            'disk': SystemMonitor.get_disk_usage(),
            'network': SystemMonitor.get_network_io(),
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


class DatabaseMonitor:
    """Database performance monitor"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get database connection stats"""
        try:
            server_status = await self.db.command('serverStatus')
            return {
                'connections': {
                    'current': server_status.get('connections', {}).get('current', 0),
                    'available': server_status.get('connections', {}).get('available', 0),
                    'total_created': server_status.get('connections', {}).get('totalCreated', 0)
                },
                'network': {
                    'bytes_in': server_status.get('network', {}).get('bytesIn', 0),
                    'bytes_out': server_status.get('network', {}).get('bytesOut', 0),
                    'num_requests': server_status.get('network', {}).get('numRequests', 0)
                }
            }
        except Exception as e:
            logger.error(f"Error getting DB connection stats: {e}")
            return {}
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get stats for all collections"""
        collections = [
            'bookings', 'rooms', 'guests', 'folios', 'folio_charges',
            'payments', 'housekeeping_tasks', 'users', 'companies'
        ]
        
        stats = {}
        for coll_name in collections:
            try:
                count = await self.db[coll_name].count_documents({})
                stats[coll_name] = {
                    'count': count,
                    'estimated_size_mb': round(count * 0.001, 2)  # Rough estimate
                }
            except Exception as e:
                logger.error(f"Error getting stats for {coll_name}: {e}")
                stats[coll_name] = {'error': str(e)}
        
        return stats
    
    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        """Get slow query information (requires profiling)"""
        try:
            # Check if profiling is enabled
            profile_level = await self.db.command('profile', -1)
            
            if profile_level.get('was', 0) > 0:
                # Get slow queries from system.profile
                slow_queries = await self.db.system.profile.find({
                    'millis': {'$gt': 100}  # Queries taking > 100ms
                }).sort('millis', -1).limit(10).to_list(10)
                
                return [
                    {
                        'operation': q.get('op', 'unknown'),
                        'namespace': q.get('ns', 'unknown'),
                        'duration_ms': q.get('millis', 0),
                        'timestamp': q.get('ts', datetime.now()).isoformat()
                    }
                    for q in slow_queries
                ]
            else:
                return []
        except Exception as e:
            logger.error(f"Error getting slow queries: {e}")
            return []
    
    async def get_index_usage(self) -> Dict[str, Any]:
        """Get index usage statistics"""
        try:
            # Get index stats for bookings (most critical)
            index_stats = await self.db.command('aggregate', 'bookings', pipeline=[
                {'$indexStats': {}}
            ])
            
            return {
                'bookings_indexes': index_stats.get('cursor', {}).get('firstBatch', [])
            }
        except Exception as e:
            logger.error(f"Error getting index usage: {e}")
            return {}


class PerformanceMetrics:
    """Track API performance metrics"""
    
    def __init__(self):
        self.request_counts = {}
        self.response_times = {}
        self.error_counts = {}
    
    def record_request(self, endpoint: str, duration_ms: float, status_code: int):
        """Record API request metrics"""
        # Count
        if endpoint not in self.request_counts:
            self.request_counts[endpoint] = 0
        self.request_counts[endpoint] += 1
        
        # Response time
        if endpoint not in self.response_times:
            self.response_times[endpoint] = []
        self.response_times[endpoint].append(duration_ms)
        
        # Errors
        if status_code >= 400:
            if endpoint not in self.error_counts:
                self.error_counts[endpoint] = 0
            self.error_counts[endpoint] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics"""
        metrics = {}
        
        for endpoint, times in self.response_times.items():
            if times:
                metrics[endpoint] = {
                    'request_count': self.request_counts.get(endpoint, 0),
                    'avg_response_ms': round(sum(times) / len(times), 2),
                    'min_response_ms': round(min(times), 2),
                    'max_response_ms': round(max(times), 2),
                    'error_count': self.error_counts.get(endpoint, 0),
                    'error_rate': round(
                        (self.error_counts.get(endpoint, 0) / self.request_counts.get(endpoint, 1)) * 100,
                        2
                    )
                }
        
        return metrics
    
    def reset(self):
        """Reset metrics"""
        self.request_counts = {}
        self.response_times = {}
        self.error_counts = {}


# Global metrics instance
performance_metrics = PerformanceMetrics()


# ============= API ENDPOINTS =============

@monitoring_router.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint - ULTRA FAST with Redis cache
    Returns system health status and key metrics
    """
    # Try Redis cache first for instant response
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cached = redis_cache.get("monitoring:health")
            if cached:
                return cached
    except:
        pass
    
    try:
        from cache_manager import cache
        
        # Get MongoDB client from environment
        mongo_url = os.environ['MONGO_URL']
        db_name = os.environ['DB_NAME']
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        
        # Test database connection
        await db.command('ping')
        db_status = 'healthy'
        
        # Test cache
        cache_status = cache.health_check()
        
        # Get system metrics
        system = SystemMonitor.get_system_info()
        
        # Overall health
        overall_status = 'healthy'
        if system['cpu_usage'] > 90:
            overall_status = 'degraded'
        if system['memory']['percent'] > 90:
            overall_status = 'degraded'
        if db_status != 'healthy':
            overall_status = 'unhealthy'
        
        client.close()
        
        result = {
            'status': overall_status,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'components': {
                'database': {
                    'status': db_status,
                    'type': 'MongoDB'
                },
                'cache': cache_status,
                'system': {
                    'status': 'healthy' if system['cpu_usage'] < 80 else 'warning',
                    'cpu_usage': system['cpu_usage'],
                    'memory_usage': system['memory']['percent'],
                    'disk_usage': system['disk']['percent']
                }
            },
            'system_info': system
        }
        
        # Cache for 5 seconds for ultra-fast subsequent calls
        try:
            from redis_cache import redis_cache
            if redis_cache:
                redis_cache.set("monitoring:health", result, ttl=5)
        except:
            pass
        
        return result
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


@monitoring_router.get("/metrics")
async def get_metrics():
    """Get performance metrics"""
    return {
        'metrics': performance_metrics.get_metrics(),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@monitoring_router.get("/system")
async def get_system_metrics():
    """Get detailed system metrics - ULTRA FAST with Redis cache"""
    # Try Redis cache first
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cached = redis_cache.get("monitoring:system")
            if cached:
                return cached
    except:
        pass
    
    result = SystemMonitor.get_system_info()
    
    # Cache for 3 seconds
    try:
        from redis_cache import redis_cache
        if redis_cache:
            redis_cache.set("monitoring:system", result, ttl=3)
    except:
        pass
    
    return result


@monitoring_router.get("/database")
async def get_database_metrics():
    """Get database metrics"""
    try:
        mongo_url = os.environ['MONGO_URL']
        db_name = os.environ['DB_NAME']
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        
        db_monitor = DatabaseMonitor(db)
        
        metrics = {
            'connections': await db_monitor.get_connection_stats(),
            'collections': await db_monitor.get_collection_stats(),
            'slow_queries': await db_monitor.get_slow_queries(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        client.close()
        
        return metrics
        
    except Exception as e:
        logger.error(f"Database metrics error: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


@monitoring_router.get("/alerts")
async def get_alerts():
    """Get system alerts and warnings"""
    alerts = []
    
    # Check system resources
    system = SystemMonitor.get_system_info()
    
    if system['cpu_usage'] > 80:
        alerts.append({
            'severity': 'warning' if system['cpu_usage'] < 90 else 'critical',
            'type': 'high_cpu',
            'message': f"High CPU usage: {system['cpu_usage']}%",
            'value': system['cpu_usage']
        })
    
    if system['memory']['percent'] > 80:
        alerts.append({
            'severity': 'warning' if system['memory']['percent'] < 90 else 'critical',
            'type': 'high_memory',
            'message': f"High memory usage: {system['memory']['percent']}%",
            'value': system['memory']['percent']
        })
    
    if system['disk']['percent'] > 80:
        alerts.append({
            'severity': 'warning' if system['disk']['percent'] < 90 else 'critical',
            'type': 'high_disk',
            'message': f"High disk usage: {system['disk']['percent']}%",
            'value': system['disk']['percent']
        })
    
    return {
        'alerts': alerts,
        'count': len(alerts),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@monitoring_router.post("/metrics/reset")
async def reset_metrics():
    """Reset performance metrics"""
    performance_metrics.reset()
    return {
        'message': 'Metrics reset successfully',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
