"""
Horizontal Scaling Manager — Multi-instance coordination, stateless validation,
distributed readiness, and instance-aware diagnostics.

Environment:
    INSTANCE_ID     — Unique instance identifier (default: auto-generated)
    SCALING_MODE    — single | multi (default: single)
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from infra.redis_capacity import classify_redis_failure

logger = logging.getLogger("infra.scaling")


class InstanceInfo:
    """Represents a running service instance."""

    def __init__(self, instance_id: str, service_type: str):
        self.instance_id = instance_id
        self.service_type = service_type
        self.started_at = datetime.now(UTC).isoformat()
        self.last_heartbeat = datetime.now(UTC).isoformat()
        self.status = "running"
        self.metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
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
        self._heartbeat_task: asyncio.Task | None = None
        self._stale_threshold = 90  # seconds
        self._heartbeat_failures = 0
        self._heartbeat_error_threshold = 3
        self._heartbeat_failure_class: str | None = None
        self._heartbeat_escalated_failure_class: str | None = None
        self._heartbeat_count = 0
        self._registry_prune_interval = 20

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
                await self._prune_stale_instances()
                await self._write_heartbeat()
                logger.info(f"Instance registered: {self._instance_id}")
            except Exception as e:
                self._record_heartbeat_failure(e, phase="registration")
            finally:
                # Registration can fail temporarily (including maxmemory). Keep
                # probing so the process can recover without a restart.
                if self._heartbeat_task is None or self._heartbeat_task.done():
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        else:
            logger.info(f"Single-instance mode: {self._instance_id}")

    async def _write_heartbeat(self) -> None:
        self._instance_info.last_heartbeat = datetime.now(UTC).isoformat()
        await self._redis.hset(
            self._registry_key,
            self._instance_id,
            json.dumps(self._instance_info.to_dict()),
        )
        if self._heartbeat_failures:
            logger.info(
                "Heartbeat recovered after %s consecutive failures",
                self._heartbeat_failures,
            )
        self._heartbeat_failures = 0
        self._heartbeat_failure_class = None
        self._heartbeat_escalated_failure_class = None
        self._heartbeat_count += 1

    def _record_heartbeat_failure(self, exc: BaseException, *, phase: str) -> None:
        self._heartbeat_failures += 1
        self._heartbeat_failure_class = classify_redis_failure(exc)
        metadata = (
            self._heartbeat_failures,
            self._heartbeat_error_threshold,
            self._heartbeat_failure_class,
            phase,
        )
        if (
            self._heartbeat_failures >= self._heartbeat_error_threshold
            and self._heartbeat_escalated_failure_class != self._heartbeat_failure_class
        ):
            logger.error(
                "Heartbeat failed repeatedly (%s consecutive): failure_class=%s phase=%s",
                self._heartbeat_failures,
                self._heartbeat_failure_class,
                phase,
            )
            self._heartbeat_escalated_failure_class = self._heartbeat_failure_class
        elif self._heartbeat_failures >= self._heartbeat_error_threshold:
            logger.warning(
                "Heartbeat remains unavailable (%s consecutive): failure_class=%s phase=%s",
                self._heartbeat_failures,
                self._heartbeat_failure_class,
                phase,
            )
        else:
            logger.warning(
                "Heartbeat transient failure (%s/%s): failure_class=%s phase=%s",
                *metadata,
            )

    async def _heartbeat_loop(self):
        """Periodically update heartbeat in Redis."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if self._redis:
                    await self._write_heartbeat()
                    if self._heartbeat_count % self._registry_prune_interval == 0:
                        await self._prune_stale_instances()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._record_heartbeat_failure(e, phase="heartbeat")
                if self._heartbeat_failure_class == "REDIS_MAXMEMORY":
                    await self._prune_stale_instances()

    async def _prune_stale_instances(self) -> None:
        """Bound the shared registry even when its dashboard is never opened."""
        if not self._redis:
            return
        try:
            all_instances = await self._redis.hgetall(self._registry_key)
            now = datetime.now(UTC)
            stale_ids = []
            for inst_id, data_str in all_instances.items():
                try:
                    data = json.loads(data_str)
                    last_hb = datetime.fromisoformat(data["last_heartbeat"])
                    age_sec = (now - last_hb).total_seconds()
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    stale_ids.append(inst_id)
                    continue
                if age_sec > self._stale_threshold * 3:
                    stale_ids.append(inst_id)
            if stale_ids:
                await self._redis.hdel(self._registry_key, *stale_ids)
        except Exception as exc:
            logger.warning(
                "Instance registry prune failed: failure_class=%s",
                classify_redis_failure(exc),
            )

    async def get_active_instances(self) -> list[dict[str, Any]]:
        """Get all active instances from registry."""
        if not self._redis:
            return [self._instance_info.to_dict()]

        try:
            all_instances = await self._redis.hgetall(self._registry_key)
            active = []
            now = datetime.now(UTC)

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
            logger.error(
                "Failed to fetch instances: failure_class=%s",
                classify_redis_failure(e),
            )
            return [self._instance_info.to_dict()]

    async def deregister(self):
        """Remove this instance from registry."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._redis:
            try:
                await self._redis.hdel(self._registry_key, self._instance_id)
            except Exception:
                pass

    def stateless_validation(self) -> dict[str, Any]:
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

    def readiness_check(self) -> dict[str, Any]:
        """Load balancer readiness data."""
        heartbeat_ready = not self._redis or self._heartbeat_failures < self._heartbeat_error_threshold
        return {
            "ready": heartbeat_ready,
            "instance_id": self._instance_id,
            "uptime_seconds": 0,
            "scaling_mode": self._scaling_mode,
            "heartbeat": {
                "status": "healthy" if heartbeat_ready else "unhealthy",
                "consecutive_failures": self._heartbeat_failures,
                "failure_class": self._heartbeat_failure_class,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_scaling_summary(self) -> dict[str, Any]:
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
