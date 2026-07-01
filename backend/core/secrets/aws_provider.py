"""
AWS Secrets Manager backend.

Uses boto3 to store/retrieve JSON secrets with deterministic naming.
Handles: throttling (via retry), not-found, permission errors.
Never logs secret values.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from .provider import SecretMetadata, SecretPayload, SecretsProviderBase

logger = logging.getLogger("core.secrets.aws")


class AWSSecretsProvider(SecretsProviderBase):
    """Production secrets backend using AWS Secrets Manager."""

    def __init__(self, region: str):
        import boto3
        from botocore.config import Config as BotoConfig

        retry_config = BotoConfig(
            retries={"max_attempts": 3, "mode": "adaptive"},
            region_name=region,
        )
        self._client = boto3.client("secretsmanager", config=retry_config)
        self._region = region

    async def create_secret(
        self,
        path: str,
        payload: dict[str, str],
        tags: dict[str, str] | None = None,
    ) -> SecretMetadata:
        now = datetime.now(UTC).isoformat()
        secret_doc = {
            "data": payload,
            "version": "1",
            "created_at": now,
            "updated_at": now,
            "rotation_count": 0,
        }

        aws_tags = [{"Key": k, "Value": v} for k, v in (tags or {}).items()]

        try:
            self._client.create_secret(
                Name=path,
                SecretString=json.dumps(secret_doc),
                Tags=aws_tags,
            )
        except self._client.exceptions.ResourceExistsException:
            raise ValueError(f"Secret already exists: {path}")

        logger.info("Secret created: %s (fields=%s)", path, list(payload.keys()))
        return SecretMetadata(
            secret_path=path,
            provider="aws_secrets_manager",
            field_names=list(payload.keys()),
            version="1",
            created_at=now,
            updated_at=now,
            rotation_count=0,
            tags=tags or {},
        )

    async def get_secret(self, path: str) -> SecretPayload | None:
        try:
            response = self._client.get_secret_value(SecretId=path)
        except self._client.exceptions.ResourceNotFoundException:
            return None
        except Exception:
            logger.exception("Failed to retrieve secret: %s", path)
            raise

        raw = json.loads(response["SecretString"])
        return SecretPayload(
            data=raw.get("data", {}),
            version=raw.get("version", "1"),
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
            rotation_count=raw.get("rotation_count", 0),
        )

    async def update_secret(
        self,
        path: str,
        payload: dict[str, str],
    ) -> SecretMetadata:
        existing = await self.get_secret(path)
        if not existing:
            raise ValueError(f"Secret not found for update: {path}")

        now = datetime.now(UTC).isoformat()
        secret_doc = {
            "data": payload,
            "version": existing.version,
            "created_at": existing.created_at,
            "updated_at": now,
            "rotation_count": existing.rotation_count,
        }

        self._client.put_secret_value(
            SecretId=path,
            SecretString=json.dumps(secret_doc),
        )

        logger.info("Secret updated: %s (fields=%s)", path, list(payload.keys()))
        return SecretMetadata(
            secret_path=path,
            provider="aws_secrets_manager",
            field_names=list(payload.keys()),
            version=existing.version,
            created_at=existing.created_at,
            updated_at=now,
            rotation_count=existing.rotation_count,
        )

    async def delete_secret(self, path: str) -> bool:
        try:
            self._client.delete_secret(
                SecretId=path,
                ForceDeleteWithoutRecovery=False,
                RecoveryWindowInDays=7,
            )
            logger.info("Secret scheduled for deletion: %s", path)
            return True
        except self._client.exceptions.ResourceNotFoundException:
            return False

    async def rotate_secret(
        self,
        path: str,
        new_payload: dict[str, str],
    ) -> SecretMetadata:
        existing = await self.get_secret(path)
        if not existing:
            raise ValueError(f"Secret not found for rotation: {path}")

        now = datetime.now(UTC).isoformat()
        new_count = existing.rotation_count + 1
        new_version = str(int(existing.version) + 1)

        secret_doc = {
            "data": new_payload,
            "version": new_version,
            "created_at": existing.created_at,
            "updated_at": now,
            "rotation_count": new_count,
        }

        self._client.put_secret_value(
            SecretId=path,
            SecretString=json.dumps(secret_doc),
        )

        logger.info(
            "Secret rotated: %s (v%s, rotation #%d)",
            path,
            new_version,
            new_count,
        )
        return SecretMetadata(
            secret_path=path,
            provider="aws_secrets_manager",
            field_names=list(new_payload.keys()),
            version=new_version,
            created_at=existing.created_at,
            updated_at=now,
            rotation_count=new_count,
        )

    async def get_secret_metadata(self, path: str) -> SecretMetadata | None:
        try:
            response = self._client.describe_secret(SecretId=path)
        except self._client.exceptions.ResourceNotFoundException:
            return None

        tags_dict = {t["Key"]: t["Value"] for t in response.get("Tags", [])}

        # We need the payload for version/rotation info
        payload = await self.get_secret(path)
        if not payload:
            return None

        return SecretMetadata(
            secret_path=path,
            provider="aws_secrets_manager",
            field_names=list(payload.data.keys()),
            version=payload.version,
            created_at=payload.created_at,
            updated_at=payload.updated_at,
            rotation_count=payload.rotation_count,
            tags=tags_dict,
        )

    async def health_check(self) -> dict[str, Any]:
        try:
            self._client.list_secrets(MaxResults=1)
            return {
                "provider": "aws_secrets_manager",
                "status": "healthy",
                "region": self._region,
            }
        except Exception as e:
            return {
                "provider": "aws_secrets_manager",
                "status": "unhealthy",
                "error": str(e),
            }
