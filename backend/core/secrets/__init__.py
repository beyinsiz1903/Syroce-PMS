"""
core.secrets — Production-grade Secrets Management Architecture.

Provides a unified, multi-backend secrets manager with:
  - AWS Secrets Manager (production)
  - Local MongoDB-backed dev storage (development only)
  - HashiCorp Vault placeholder (future)
  - Tenant-aware, provider-aware secret resolution
  - Access auditing
  - Migration support from legacy stores
"""
from .config import SecretsConfig, get_secrets_config
from .manager import SecretsManager, get_secrets_manager
from .naming import SecretIdentity

__all__ = [
    "get_secrets_manager",
    "SecretsManager",
    "SecretsConfig",
    "get_secrets_config",
    "SecretIdentity",
]
