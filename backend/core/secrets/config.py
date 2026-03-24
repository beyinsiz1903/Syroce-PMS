"""
Secrets configuration — validates environment and enforces safe defaults.

Required env vars for production:
  SECRETS_PROVIDER          — aws_secrets_manager | local_dev
  APP_ENV                   — production | staging | development
  AWS_REGION                — (required when SECRETS_PROVIDER=aws_secrets_manager)
  AWS_SECRET_PREFIX         — optional, defaults to "syroce"

Optional:
  ENABLE_LEGACY_SECRET_FALLBACK  — true/false (default: true during migration)
  SECRET_ACCESS_AUDIT_ENABLED    — true/false (default: true)
  CM_CREDENTIAL_KEY              — encryption key for local dev backend
"""
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("core.secrets.config")

VALID_PROVIDERS = {"aws_secrets_manager", "local_dev", "vault"}
PRODUCTION_ENVS = {"production", "staging"}


@dataclass(frozen=True)
class SecretsConfig:
    provider: str
    app_env: str
    aws_region: str
    aws_secret_prefix: str
    enable_legacy_fallback: bool
    audit_enabled: bool
    encryption_key: str

    @property
    def is_production(self) -> bool:
        return self.app_env in PRODUCTION_ENVS

    def validate(self) -> None:
        """Fail loudly on invalid configuration."""
        if self.provider not in VALID_PROVIDERS:
            raise RuntimeError(
                f"SECRETS_PROVIDER='{self.provider}' is not supported. "
                f"Valid: {VALID_PROVIDERS}"
            )

        if self.provider == "local_dev" and self.is_production:
            raise RuntimeError(
                "SECRETS_PROVIDER=local_dev is forbidden in production/staging. "
                "Set SECRETS_PROVIDER=aws_secrets_manager."
            )

        if self.provider == "aws_secrets_manager":
            if not self.aws_region:
                raise RuntimeError(
                    "AWS_REGION is required when SECRETS_PROVIDER=aws_secrets_manager"
                )

        if self.provider == "vault":
            vault_addr = os.environ.get("VAULT_ADDR", "")
            if not vault_addr:
                raise RuntimeError(
                    "VAULT_ADDR is required when SECRETS_PROVIDER=vault"
                )


_cached_config: SecretsConfig | None = None


def get_secrets_config() -> SecretsConfig:
    """Build and validate config from environment. Cached after first call."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config = SecretsConfig(
        provider=os.environ.get("SECRETS_PROVIDER", "local_dev"),
        app_env=os.environ.get("APP_ENV", "development"),
        aws_region=os.environ.get("AWS_REGION", ""),
        aws_secret_prefix=os.environ.get("AWS_SECRET_PREFIX", "syroce"),
        enable_legacy_fallback=os.environ.get(
            "ENABLE_LEGACY_SECRET_FALLBACK", "true"
        ).lower() == "true",
        audit_enabled=os.environ.get(
            "SECRET_ACCESS_AUDIT_ENABLED", "true"
        ).lower() == "true",
        encryption_key=os.environ.get("CM_CREDENTIAL_KEY", ""),
    )

    config.validate()
    _cached_config = config
    logger.info(
        "Secrets config loaded: provider=%s env=%s legacy_fallback=%s audit=%s",
        config.provider, config.app_env,
        config.enable_legacy_fallback, config.audit_enabled,
    )
    return config


def reset_config_cache() -> None:
    """For testing only."""
    global _cached_config
    _cached_config = None
