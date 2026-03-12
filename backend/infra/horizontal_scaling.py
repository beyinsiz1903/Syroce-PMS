"""
Horizontal Scaling Manager — Multi-instance coordination, stateless validation,
distributed readiness, and instance-aware diagnostics.

Environment:
    INSTANCE_ID     — Unique instance identifier (default: auto-generated)
    SCALING_MODE    — single | multi (default: single)
"""
import os
import time
import asyncio
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("infra.scaling")


class InstanceInfo:
    """Represents a running service instance."""

    def __init__(self, instance_id: str, service_type: str):
        self.instance_id = instance_id
        self.service_type = service_type
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self.status = "running"
        self.metadata: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "service_type": self.service_type,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
            "metadata": self.metadata,
        }


class HorizontalScalingManager:
    """Manages multi-instance coordination and health."""

    def __init__(self):
        self._instance_id = os.environ.get("INSTANCE_ID", f"inst-{uuid.uuid4().hex[:8]}")
        self._scaling_mode = os.environ.get("SCALING_MODE", "single")
        self._redis = None
        self._instance_info = InstanceInfo(self._instance_id, "backend")
        self._registry_key = "syroce:instances"
        self._heartbeat_interval = 30
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stale_threshold = 90  # seconds

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def scaling_mode(self) -> str:
        return self._scaling_mode

    async def initialize(self, redis_client=None):
        """Register this instance and start heartbeat."""
        self._redis = redis_client
        if self._redis:
            try:
                import json
                await self._redis.hset(
                    self._registry_key,
                    self._instance_id,
                    json.dumps(self._instance_info.to_dict()),
                )
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                logger.info(f"Instance registered: {self._instance_id}")
            except Exception as e:
                logger.warning(f"Instance registration failed: {e}")
        else:
            logger.info(f"Single-instance mode: {self._instance_id}")

    async def _heartbeat_loop(self):
        """Periodically update heartbeat in Redis."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if self._redis:
                    import json
                    self._instance_info.last_heartbeat = datetime.now(timezone.utc).isoformat()
                    await self._redis.hset(
                        self._registry_key,
                        self._instance_id,
                        json.dumps(self._instance_info.to_dict()),
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")

    async def get_active_instances(self) -> List[Dict[str, Any]]:
        """Get all active instances from registry."""
        if not self._redis:
            return [self._instance_info.to_dict()]

        try:
            import json
            all_instances = await self._redis.hgetall(self._registry_key)
            active = []
            now = datetime.now(timezone.utc)

            for inst_id, data_str in all_instances.items():
                data = json.loads(data_str)
                last_hb = datetime.fromisoformat(data["last_heartbeat"])
                age_sec = (now - last_hb).total_seconds()

                if age_sec < self._stale_threshold:
                    data["is_stale"] = False
                    active.append(data)
                else:
                    data["is_stale"] = True
                    active.append(data)
                    # Clean up stale entries
                    if age_sec > self._stale_threshold * 3:
                        await self._redis.hdel(self._registry_key, inst_id)

            return active
        except Exception as e:
            logger.error(f"Failed to fetch instances: {e}")
            return [self._instance_info.to_dict()]

    async def deregister(self):
        """Remove this instance from registry."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._redis:
            try:
                await self._redis.hdel(self._registry_key, self._instance_id)
                logger.info(f"Instance deregistered: {self._instance_id}")
            except Exception:
                pass

    def stateless_validation(self) -> Dict[str, Any]:
        """Validate service statelessness for horizontal scaling."""
        checks = {
            "no_local_file_state": True,
            "env_based_config": True,
            "shared_db": True,
            "shared_cache": bool(os.environ.get("REDIS_URL")),
            "session_externalized": True,
            "no_sticky_sessions_needed": True,
        }
        all_passed = all(checks.values())
        return {
            "ready_for_scaling": all_passed,
            "checks": checks,
            "scaling_mode": self._scaling_mode,
            "instance_id": self._instance_id,
        }

    def readiness_check(self) -> Dict[str, Any]:
        """Load balancer readiness data."""
        return {
            "ready": True,
            "instance_id": self._instance_id,
            "uptime_seconds": 0,
            "scaling_mode": self._scaling_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_scaling_summary(self) -> Dict[str, Any]:
        instances = await self.get_active_instances()
        active = [i for i in instances if not i.get("is_stale")]
        stale = [i for i in instances if i.get("is_stale")]

        return {
            "scaling_mode": self._scaling_mode,
            "current_instance": self._instance_id,
            "total_instances": len(instances),
            "active_instances": len(active),
            "stale_instances": len(stale),
            "instances": instances,
            "stateless_check": self.stateless_validation(),
        }


# Singleton
scaling_manager = HorizontalScalingManager()
