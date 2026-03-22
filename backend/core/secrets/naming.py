"""
Secret naming and identity model.

Deterministic, environment-safe naming convention:
  /{prefix}/{env}/channel-manager/{tenant_id}/{provider}/{property_id}

Examples:
  syroce/production/channel-manager/t_abc123/exely/hotel_501694
  syroce/development/channel-manager/t_demo/hotelrunner/hr_12345
"""
import re
from dataclasses import dataclass


# Only alphanumeric, hyphens, underscores allowed in path segments
_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_-]+$")


def _sanitize(segment: str) -> str:
    """Sanitize a path segment for use in secret names."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", segment)
    return cleaned[:128]  # AWS limit per segment


@dataclass(frozen=True)
class SecretIdentity:
    """Uniquely identifies a secret across environments and tenants."""
    prefix: str
    environment: str
    tenant_id: str
    provider: str
    property_id: str

    @property
    def path(self) -> str:
        """Full secret path for AWS Secrets Manager or Vault."""
        parts = [
            _sanitize(self.prefix),
            _sanitize(self.environment),
            "channel-manager",
            _sanitize(self.tenant_id),
            _sanitize(self.provider),
            _sanitize(self.property_id),
        ]
        return "/".join(parts)

    @property
    def flat_key(self) -> str:
        """Flat key for local dev storage (collection field)."""
        return self.path.replace("/", "::")

    @classmethod
    def from_path(cls, path: str, prefix: str = "syroce") -> "SecretIdentity":
        """Parse a secret path back into an identity."""
        parts = path.split("/")
        if len(parts) != 6:
            raise ValueError(f"Invalid secret path: {path} (expected 6 segments)")
        return cls(
            prefix=parts[0],
            environment=parts[1],
            tenant_id=parts[3],
            provider=parts[4],
            property_id=parts[5],
        )

    def to_metadata(self) -> dict:
        """Return metadata dict for tagging in AWS."""
        return {
            "tenant_id": self.tenant_id,
            "provider": self.provider,
            "property_id": self.property_id,
            "environment": self.environment,
            "managed_by": "syroce-secrets-manager",
        }
