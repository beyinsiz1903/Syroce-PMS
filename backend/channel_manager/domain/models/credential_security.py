"""
Credential Security Models — Data models for encrypted credential storage,
secret rotation, and secure credential lifecycle management.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class ConnectorCredential(BaseModel):
    """Encrypted credential record for a connector."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    provider: str = "hotelrunner"
    encrypted_payload: str = ""
    encryption_algorithm: str = "AES-256-GCM"
    key_version: int = 1
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = ""
    last_validated_at: Optional[str] = None
    validation_status: str = "pending"

    def to_doc(self) -> Dict[str, Any]:
        doc = self.model_dump()
        doc.pop("_id", None)
        return doc


class EncryptedSecret(BaseModel):
    """Individual encrypted secret field."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    field_name: str
    encrypted_value: str
    nonce: str = ""
    tag: str = ""
    algorithm: str = "AES-256-GCM"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        doc = self.model_dump()
        doc.pop("_id", None)
        return doc


class SecretRotationLog(BaseModel):
    """Audit log for credential rotation events."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    rotation_type: str = "manual"  # manual, automated, emergency
    rotated_by: str = ""
    rotated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    old_key_version: int = 0
    new_key_version: int = 0
    fields_rotated: List[str] = Field(default_factory=list)
    validation_after_rotation: str = "pending"  # pending, passed, failed
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_doc(self) -> Dict[str, Any]:
        doc = self.model_dump()
        doc.pop("_id", None)
        return doc
