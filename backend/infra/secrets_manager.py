"""
Secrets Manager — Production secrets abstraction layer.
Supports AWS Secrets Manager, HashiCorp Vault, and local env fallback.

Environment:
    SECRETS_PROVIDER   — aws | vault | env (default: env)
    AWS_REGION         — AWS region for Secrets Manager
    VAULT_ADDR         — HashiCorp Vault address
    VAULT_TOKEN        — HashiCorp Vault token
"""
import os
import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("infra.secrets")


class SecretsProvider:
    """Base secrets provider interface."""

    async def get_secret(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def get_secret_json(self, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def health_check(self) -> Dict[str, Any]:
        raise NotImplementedError


class EnvSecretsProvider(SecretsProvider):
    """Local environment variable secrets provider (development fallback)."""

    async def get_secret(self, key: str) -> Optional[str]:
        return os.environ.get(key)

    async def get_secret_json(self, key: str) -> Optional[Dict[str, Any]]:
        val = os.environ.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    async def health_check(self) -> Dict[str, Any]:
        return {"provider": "env", "status": "healthy", "mode": "development"}


class AWSSecretsProvider(SecretsProvider):
    """AWS Secrets Manager provider."""

    def __init__(self):
        self._client = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}
        self._region = os.environ.get("AWS_REGION", "eu-west-1")

    def _get_client(self):
        if not self._client:
            try:
                import boto3
                self._client = boto3.client(
                    "secretsmanager", region_name=self._region
                )
            except Exception as e:
                logger.error(f"AWS Secrets Manager client init failed: {e}")
        return self._client

    async def get_secret(self, key: str) -> Optional[str]:
        # Check cache
        if key in self._cache:
            if time.time() - self._cache_timestamps.get(key, 0) < self._cache_ttl:
                return self._cache[key]

        client = self._get_client()
        if not client:
            return None
        try:
            response = client.get_secret_value(SecretId=key)
            value = response.get("SecretString")
            self._cache[key] = value
            self._cache_timestamps[key] = time.time()
            return value
        except Exception as e:
            logger.error(f"AWS get_secret({key}) failed: {e}")
            return None

    async def get_secret_json(self, key: str) -> Optional[Dict[str, Any]]:
        val = await self.get_secret(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    async def health_check(self) -> Dict[str, Any]:
        client = self._get_client()
        if not client:
            return {"provider": "aws", "status": "unavailable", "error": "client not initialized"}
        try:
            client.list_secrets(MaxResults=1)
            return {"provider": "aws", "status": "healthy", "region": self._region}
        except Exception as e:
            return {"provider": "aws", "status": "unhealthy", "error": str(e)}


class VaultSecretsProvider(SecretsProvider):
    """HashiCorp Vault secrets provider."""

    def __init__(self):
        self._addr = os.environ.get("VAULT_ADDR", "")
        self._token = os.environ.get("VAULT_TOKEN", "")
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300
        self._cache_timestamps: Dict[str, float] = {}

    async def get_secret(self, key: str) -> Optional[str]:
        if key in self._cache:
            if time.time() - self._cache_timestamps.get(key, 0) < self._cache_ttl:
                return self._cache[key]

        if not self._addr or not self._token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._addr}/v1/secret/data/{key}",
                    headers={"X-Vault-Token": self._token},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    value = json.dumps(data.get("data", {}).get("data", {}))
                    self._cache[key] = value
                    self._cache_timestamps[key] = time.time()
                    return value
        except Exception as e:
            logger.error(f"Vault get_secret({key}) failed: {e}")
        return None

    async def get_secret_json(self, key: str) -> Optional[Dict[str, Any]]:
        val = await self.get_secret(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    async def health_check(self) -> Dict[str, Any]:
        if not self._addr:
            return {"provider": "vault", "status": "not_configured"}
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._addr}/v1/sys/health", timeout=5
                )
                return {
                    "provider": "vault",
                    "status": "healthy" if resp.status_code == 200 else "unhealthy",
                    "addr": self._addr,
                }
        except Exception as e:
            return {"provider": "vault", "status": "unhealthy", "error": str(e)}


class SecretsManager:
    """Unified secrets manager with provider selection and audit."""

    def __init__(self):
        provider_name = os.environ.get("SECRETS_PROVIDER", "env")
        if provider_name == "aws":
            self._provider = AWSSecretsProvider()
        elif provider_name == "vault":
            self._provider = VaultSecretsProvider()
        else:
            self._provider = EnvSecretsProvider()
        self._provider_name = provider_name
        self._access_log: list = []
        self._max_log = 200
        self._metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "errors": 0,
        }

    async def get_secret(self, key: str, requester: str = "system") -> Optional[str]:
        self._metrics["total_requests"] += 1
        self._log_access(key, requester)
        try:
            return await self._provider.get_secret(key)
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error(f"Secret fetch error ({key}): {e}")
            return None

    async def get_secret_json(self, key: str, requester: str = "system") -> Optional[Dict[str, Any]]:
        self._metrics["total_requests"] += 1
        self._log_access(key, requester)
        try:
            return await self._provider.get_secret_json(key)
        except Exception:
            self._metrics["errors"] += 1
            return None

    def _log_access(self, key: str, requester: str):
        self._access_log.append({
            "key": key,
            "requester": requester,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": self._provider_name,
        })
        if len(self._access_log) > self._max_log:
            self._access_log = self._access_log[-self._max_log:]

    async def health_check(self) -> Dict[str, Any]:
        result = await self._provider.health_check()
        result["metrics"] = self._metrics
        return result

    def get_access_log(self, limit: int = 50) -> list:
        # Mask secret keys for security
        return [
            {**entry, "key": entry["key"][:3] + "***"}
            for entry in self._access_log[-limit:]
        ]

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "provider": self._provider_name,
            **self._metrics,
            "access_log_size": len(self._access_log),
        }


# Singleton
secrets_manager = SecretsManager()
