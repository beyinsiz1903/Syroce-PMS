"""
MappingRule - Links PMS entities to external provider entities.
Central to the connector-first architecture: all sync flows depend on valid mappings.

Indexes:
  - (tenant_id, connector_id, entity_type, pms_entity_id): unique
  - (tenant_id, connector_id, entity_type, external_entity_id): unique
  - (tenant_id, status)
  - (tenant_id, connector_id, validation_status)
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MappingStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INVALID = "invalid"
    DISABLED = "disabled"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"


class MappingDirection(str, Enum):
    BIDIRECTIONAL = "bidirectional"
    PMS_TO_EXTERNAL = "pms_to_external"
    EXTERNAL_TO_PMS = "external_to_pms"


class MappingEntityType(str, Enum):
    ROOM_TYPE = "room_type"
    RATE_PLAN = "rate_plan"
    MEAL_PLAN = "meal_plan"
    CANCELLATION_POLICY = "cancellation_policy"
    TAX_MODE = "tax_mode"
    OCCUPANCY = "occupancy"


# Required mapping types for sync readiness
REQUIRED_MAPPING_TYPES = [
    MappingEntityType.ROOM_TYPE,
    MappingEntityType.RATE_PLAN,
]

# All supported mapping types for validation
SUPPORTED_MAPPING_TYPES = [
    MappingEntityType.ROOM_TYPE,
    MappingEntityType.RATE_PLAN,
    MappingEntityType.OCCUPANCY,
    MappingEntityType.MEAL_PLAN,
    MappingEntityType.TAX_MODE,
]


class MappingRule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    entity_type: MappingEntityType
    direction: MappingDirection = MappingDirection.BIDIRECTIONAL
    status: MappingStatus = MappingStatus.DRAFT

    # PMS side
    pms_entity_id: str
    pms_entity_name: str = ""
    pms_entity_meta: dict[str, Any] = Field(default_factory=dict)

    # External/Provider side
    external_entity_id: str
    external_entity_name: str = ""
    external_entity_meta: dict[str, Any] = Field(default_factory=dict)

    # Transformation rules
    occupancy_offset: int = 0  # e.g., PMS max_occ=3 but OTA expects 2
    rate_modifier: float | None = None  # multiply rate by this before push
    rate_offset: float | None = None  # add this to rate before push

    # Validation
    validation_status: ValidationStatus = ValidationStatus.PENDING
    last_validated_at: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    invalid_reason: str | None = None

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_by: str | None = None
    updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MappingRule":
        doc.pop("_id", None)
        return cls(**doc)
