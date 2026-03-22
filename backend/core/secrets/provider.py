"""
Abstract secrets provider interface.

All backends must implement this interface.
Secret payloads are always JSON dicts. Providers must never log secret values.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class SecretPayload:
    """Encrypted secret content + metadata."""
    data: Dict[str, str]
    version: str = "1"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    rotation_count: int = 0


@dataclass
class SecretMetadata:
    """Non-sensitive metadata about a secret."""
    secret_path: str
    provider: str
    field_names: list
    version: str
    created_at: str
    updated_at: str
    rotation_count: int
    tags: Dict[str, str] = field(default_factory=dict)
    exists: bool = True


class SecretsProviderBase(ABC):
    """Abstract interface for all secrets backends."""

    @abstractmethod
    async def create_secret(
        self,
        path: str,
        payload: Dict[str, str],
        tags: Optional[Dict[str, str]] = None,
    ) -> SecretMetadata:
        """Create a new secret. Raises if already exists."""
        ...

    @abstractmethod
    async def get_secret(self, path: str) -> Optional[SecretPayload]:
        """Retrieve and decrypt a secret. Returns None if not found."""
        ...

    @abstractmethod
    async def update_secret(
        self,
        path: str,
        payload: Dict[str, str],
    ) -> SecretMetadata:
        """Update an existing secret. Raises if not found."""
        ...

    @abstractmethod
    async def delete_secret(self, path: str) -> bool:
        """Delete a secret. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    async def rotate_secret(
        self,
        path: str,
        new_payload: Dict[str, str],
    ) -> SecretMetadata:
        """Rotate a secret to new values, incrementing rotation_count."""
        ...

    @abstractmethod
    async def get_secret_metadata(self, path: str) -> Optional[SecretMetadata]:
        """Get metadata without retrieving secret values."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Validate provider connectivity and readiness."""
        ...
