"""
Redis Cluster Manager — Production-grade Redis connection abstraction.
Supports standalone, sentinel, and cluster modes via environment config.
Provides connection pooling, health checks, failover, and metrics.

Environment:
    REDIS_URL        — Connection URL (required for redis mode)
    REDIS_MODE       — standalone | sentinel | cluster  (default: standalone)
    REDIS_SENTINEL_MASTER — Sentinel master name (sentinel mode)
    REDIS_MAX_CONNECTIONS — Pool size (default: 100)
"""
import os
import time
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("infra.redis_cluster")


class RedisClusterManager:
    """Cluster-aware Redis connection manager with health monitoring."""

    def __init__(self):
        self._redis = None
        self._pubsub_redis = None
        self._lock_redis = None
        self._mode = os.environ.get("REDIS_MODE", "standalone")
        self._url = os.environ.get("REDIS_URL", "")
        self._max_connections = int(os.environ.get("REDIS_MAX_CONNECTIONS", "100"))
        self._sentinel_master = os.environ.get("REDIS_SENTINEL_MASTER", "mymaster")
        self._connected = False
        self._reconnect_count = 0
        self._last_health_check: Optional[str] = None
        self._metrics = {
            "connections_created": 0,
            "connections_failed": 0,
            "reconnects": 0,
            "health_checks": 0,
            "health_failures": 0,
            "commands_sent": 0,
            "pubsub_messages": 0,
        }
        self._connect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> str:
        return self._mode

    async def connect(self) -> bool:
        """Establish Redis connection based on configured mode."""
        async with self._connect_lock:
            if self._connected and self._redis:
                try:
                    await self._redis.ping()
                    return True
                except Exception:
                    self._connected = False

            if not self._url:
                logger.info("REDIS_URL not set — Redis disabled")
                return False

            try:
                import redis.asyncio as aioredis

                pool_kwargs = {
                    "decode_responses": True,
                    "socket_connect_timeout": 5,
                    "socket_timeout": 10,
                    "retry_on_timeout": True,
                    "health_check_interval": 30,
                    "max_connections": self._max_connections,
                }

                if self._mode == "cluster":
                    from redis.asyncio.cluster import RedisCluster
                    self._redis = RedisCluster.from_url(
                        self._url, **pool_kwargs
                    )
                elif self._mode == "sentinel":
                    from redis.asyncio.sentinel import Sentinel
                    sentinel_hosts = self._parse_sentinel_hosts()
                    sentinel = Sentinel(sentinel_hosts, socket_timeout=5)
                    self._redis = sentinel.master_for(
                        self._sentinel_master, **pool_kwargs
                    )
                else:
                    self._redis = aioredis.from_url(self._url, **pool_kwargs)

                await self._redis.ping()
                self._connected = True
                self._metrics["connections_created"] += 1
                logger.info(f"Redis connected: mode={self._mode}")

                # Create dedicated connections for pubsub and locks
                self._pubsub_redis = aioredis.from_url(
                    self._url, decode_responses=True,
                    socket_connect_timeout=5, socket_timeout=30,
                )
                self._lock_redis = aioredis.from_url(
                    self._url, decode_responses=True,
                    socket_connect_timeout=5, socket_timeout=10,
                )
                return True

            except Exception as e:
                self._connected = False
                self._metrics["connections_failed"] += 1
                logger.error(f"Redis connection failed ({self._mode}): {e}")
                return False

    def _parse_sentinel_hosts(self):
        """Parse sentinel hosts from REDIS_URL like sentinel://host1:26379,host2:26379"""
        url = self._url.replace("sentinel://", "").replace("redis://", "")
        hosts = []
        for part in url.split(","):
            host_port = part.strip().split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 26379
            hosts.append((host, port))
        return hosts

    async def reconnect_with_backoff(self, max_retries: int = 10) -> bool:
        """Reconnect with exponential backoff."""
        for attempt in range(max_retries):
            backoff = min(1.0 * (2 ** attempt), 30.0)
            logger.info(f"Redis reconnect attempt {attempt + 1}/{max_retries} in {backoff}s")
            await asyncio.sleep(backoff)
            if await self.connect():
                self._reconnect_count += 1
                self._metrics["reconnects"] += 1
                return True
        logger.error(f"Redis reconnect failed after {max_retries} attempts")
        return False

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check."""
        self._metrics["health_checks"] += 1
        result = {
            "status": "disconnected",
            "mode": self._mode,
            "connected": self._connected,
            "reconnect_count": self._reconnect_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if not self._connected or not self._redis:
            self._metrics["health_failures"] += 1
            return result

        try:
            start = time.time()
            await self._redis.ping()
            latency_ms = round((time.time() - start) * 1000, 2)

            info = await self._redis.info("server", "memory", "clients", "stats")
            result.update({
                "status": "healthy",
                "latency_ms": latency_ms,
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            })

            if self._mode == "cluster":
                try:
                    cluster_info = await self._redis.info("cluster")
                    result["cluster"] = {
                        "state": cluster_info.get("cluster_enabled", 0),
                        "known_nodes": cluster_info.get("cluster_known_nodes", 0),
                        "size": cluster_info.get("cluster_size", 0),
                    }
                except Exception:
                    pass

            self._last_health_check = result["timestamp"]

        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            self._metrics["health_failures"] += 1

        return result

    def get_client(self):
        """Get the main Redis client."""
        return self._redis

    def get_pubsub_client(self):
        """Get dedicated pub/sub Redis client."""
        return self._pubsub_redis or self._redis

    def get_lock_client(self):
        """Get dedicated lock Redis client."""
        return self._lock_redis or self._redis

    def get_metrics(self) -> Dict[str, Any]:
        """Get connection metrics."""
        return {
            **self._metrics,
            "mode": self._mode,
            "connected": self._connected,
            "reconnect_count": self._reconnect_count,
            "last_health_check": self._last_health_check,
            "max_connections": self._max_connections,
        }

    async def close(self):
        """Close all connections."""
        for client in [self._redis, self._pubsub_redis, self._lock_redis]:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass
        self._connected = False
        logger.info("Redis connections closed")


# Singleton instance
redis_cluster = RedisClusterManager()
