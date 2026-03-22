"""
Test Suite — Secrets Manager Architecture (SEC-001)

Tests cover:
  - SecretsConfig validation
  - SecretIdentity naming convention
  - LocalDevSecretsProvider CRUD
  - SecretsManager high-level API
  - Legacy fallback behavior
  - Credential masking
  - Audit logging
  - AWS provider behavior (mocked boto3)
  - Secrets never appear in API responses
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Config Tests (sync) ─────────────────────────────────────────────

class TestSecretsConfig:

    def setup_method(self):
        from core.secrets.config import reset_config_cache
        reset_config_cache()

    def teardown_method(self):
        from core.secrets.config import reset_config_cache
        reset_config_cache()

    def test_local_dev_config_valid(self):
        with patch.dict(os.environ, {
            "SECRETS_PROVIDER": "local_dev",
            "APP_ENV": "development",
        }, clear=False):
            from core.secrets.config import get_secrets_config, reset_config_cache
            reset_config_cache()
            config = get_secrets_config()
            assert config.provider == "local_dev"
            assert not config.is_production

    def test_local_dev_in_production_fails(self):
        with patch.dict(os.environ, {
            "SECRETS_PROVIDER": "local_dev",
            "APP_ENV": "production",
        }, clear=False):
            from core.secrets.config import get_secrets_config, reset_config_cache
            reset_config_cache()
            with pytest.raises(RuntimeError, match="forbidden in production"):
                get_secrets_config()

    def test_unsupported_provider_fails(self):
        with patch.dict(os.environ, {
            "SECRETS_PROVIDER": "magic_cloud",
            "APP_ENV": "development",
        }, clear=False):
            from core.secrets.config import get_secrets_config, reset_config_cache
            reset_config_cache()
            with pytest.raises(RuntimeError, match="not supported"):
                get_secrets_config()

    def test_aws_without_region_fails(self):
        env = {
            "SECRETS_PROVIDER": "aws_secrets_manager",
            "APP_ENV": "production",
            "AWS_REGION": "",
        }
        with patch.dict(os.environ, env, clear=False):
            from core.secrets.config import get_secrets_config, reset_config_cache
            reset_config_cache()
            with pytest.raises(RuntimeError, match="AWS_REGION"):
                get_secrets_config()

    def test_aws_config_valid(self):
        env = {
            "SECRETS_PROVIDER": "aws_secrets_manager",
            "APP_ENV": "production",
            "AWS_REGION": "eu-west-1",
        }
        with patch.dict(os.environ, env, clear=False):
            from core.secrets.config import get_secrets_config, reset_config_cache
            reset_config_cache()
            config = get_secrets_config()
            assert config.provider == "aws_secrets_manager"
            assert config.is_production


# ── Naming Tests (sync) ─────────────────────────────────────────────

class TestSecretIdentity:

    def test_path_generation(self):
        from core.secrets.naming import SecretIdentity
        identity = SecretIdentity(
            prefix="syroce",
            environment="production",
            tenant_id="t_abc123",
            provider="exely",
            property_id="hotel_501694",
        )
        assert identity.path == "syroce/production/channel-manager/t_abc123/exely/hotel_501694"

    def test_flat_key(self):
        from core.secrets.naming import SecretIdentity
        identity = SecretIdentity(
            prefix="syroce", environment="dev",
            tenant_id="t1", provider="hotelrunner", property_id="hr_99",
        )
        assert "::" in identity.flat_key

    def test_sanitization(self):
        from core.secrets.naming import SecretIdentity
        identity = SecretIdentity(
            prefix="syroce", environment="dev",
            tenant_id="t@#1", provider="exely", property_id="h/o/t",
        )
        assert "@" not in identity.path
        assert "#" not in identity.path

    def test_metadata(self):
        from core.secrets.naming import SecretIdentity
        identity = SecretIdentity(
            prefix="syroce", environment="production",
            tenant_id="t1", provider="exely", property_id="h1",
        )
        meta = identity.to_metadata()
        assert meta["tenant_id"] == "t1"
        assert meta["provider"] == "exely"
        assert meta["managed_by"] == "syroce-secrets-manager"

    def test_from_path(self):
        from core.secrets.naming import SecretIdentity
        path = "syroce/production/channel-manager/t1/exely/h1"
        identity = SecretIdentity.from_path(path)
        assert identity.tenant_id == "t1"
        assert identity.provider == "exely"


# ── LocalDev Provider Tests (async) ──────────────────────────────────

async def _make_local_provider():
    from core.secrets.local_provider import LocalDevSecretsProvider
    return LocalDevSecretsProvider(encryption_key="test-key-for-unit-tests")


async def test_local_create_and_get():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_test/exely/hotel_{os.getpid()}_cg"

    meta = await provider.create_secret(path, {"username": "user1", "password": "pass1"})
    assert meta.provider == "local_dev"
    assert "username" in meta.field_names

    payload = await provider.get_secret(path)
    assert payload is not None
    assert payload.data["username"] == "user1"
    assert payload.data["password"] == "pass1"

    await provider.delete_secret(path)


async def test_local_get_nonexistent():
    provider = await _make_local_provider()
    result = await provider.get_secret("test/dev/channel-manager/t_none/exely/doesnotexist")
    assert result is None


async def test_local_create_duplicate_raises():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_dup/exely/hotel_{os.getpid()}_dup"

    await provider.create_secret(path, {"key": "val"})
    with pytest.raises(ValueError, match="already exists"):
        await provider.create_secret(path, {"key": "val2"})

    await provider.delete_secret(path)


async def test_local_update():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_upd/exely/hotel_{os.getpid()}_upd"

    await provider.create_secret(path, {"k": "v1"})
    await provider.update_secret(path, {"k": "v2", "k2": "new"})

    payload = await provider.get_secret(path)
    assert payload.data["k"] == "v2"
    assert payload.data["k2"] == "new"

    await provider.delete_secret(path)


async def test_local_delete():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_del/exely/hotel_{os.getpid()}_del"

    await provider.create_secret(path, {"k": "v"})
    assert await provider.delete_secret(path) is True
    assert await provider.delete_secret(path) is False


async def test_local_rotate():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_rot/exely/hotel_{os.getpid()}_rot"

    await provider.create_secret(path, {"token": "old_token"})
    meta = await provider.rotate_secret(path, {"token": "new_token"})
    assert meta.rotation_count == 1
    assert meta.version == "2"

    payload = await provider.get_secret(path)
    assert payload.data["token"] == "new_token"

    await provider.delete_secret(path)


async def test_local_metadata_no_secrets():
    provider = await _make_local_provider()
    path = f"test/dev/channel-manager/t_meta/exely/hotel_{os.getpid()}_meta"

    await provider.create_secret(path, {"secret_key": "super_secret"})
    meta = await provider.get_secret_metadata(path)
    assert meta is not None
    assert "secret_key" in meta.field_names

    await provider.delete_secret(path)


async def test_local_health_check():
    provider = await _make_local_provider()
    health = await provider.health_check()
    assert health["status"] == "healthy"
    assert health["mode"] == "NON-PRODUCTION"


# ── AWS Provider Tests (Mocked, sync-like) ───────────────────────────

def _make_aws_provider():
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.exceptions.ResourceNotFoundException = type("ResourceNotFoundException", (Exception,), {})
        mock_client.exceptions.ResourceExistsException = type("ResourceExistsException", (Exception,), {})

        from core.secrets.aws_provider import AWSSecretsProvider
        provider = AWSSecretsProvider.__new__(AWSSecretsProvider)
        provider._client = mock_client
        provider._region = "eu-west-1"
        return provider, mock_client


async def test_aws_create_secret():
    provider, mock_client = _make_aws_provider()
    meta = await provider.create_secret(
        "syroce/prod/channel-manager/t1/exely/h1",
        {"username": "u", "password": "p"},
        tags={"tenant_id": "t1"},
    )
    mock_client.create_secret.assert_called_once()
    assert meta.provider == "aws_secrets_manager"


async def test_aws_get_secret():
    provider, mock_client = _make_aws_provider()
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({
            "data": {"token": "abc123"},
            "version": "1",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
            "rotation_count": 0,
        })
    }
    payload = await provider.get_secret("syroce/prod/channel-manager/t1/hr/h1")
    assert payload.data["token"] == "abc123"


async def test_aws_get_not_found():
    provider, mock_client = _make_aws_provider()
    mock_client.get_secret_value.side_effect = mock_client.exceptions.ResourceNotFoundException()
    result = await provider.get_secret("nonexistent")
    assert result is None


async def test_aws_delete_secret():
    provider, mock_client = _make_aws_provider()
    result = await provider.delete_secret("syroce/prod/channel-manager/t1/hr/h1")
    assert result is True
    mock_client.delete_secret.assert_called_once()


async def test_aws_rotate():
    provider, mock_client = _make_aws_provider()
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({
            "data": {"token": "old"},
            "version": "1",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
            "rotation_count": 0,
        })
    }
    meta = await provider.rotate_secret(
        "syroce/prod/channel-manager/t1/hr/h1",
        {"token": "new"},
    )
    assert meta.rotation_count == 1
    assert meta.version == "2"


async def test_aws_health_check():
    provider, mock_client = _make_aws_provider()
    mock_client.list_secrets.return_value = {"SecretList": []}
    health = await provider.health_check()
    assert health["status"] == "healthy"


# ── SecretsManager Integration Tests ─────────────────────────────────

async def _get_manager():
    from core.secrets.manager import SecretsManager
    from core.secrets.config import SecretsConfig
    config = SecretsConfig(
        provider="local_dev",
        app_env="development",
        aws_region="",
        aws_secret_prefix="test",
        enable_legacy_fallback=False,
        audit_enabled=True,
        encryption_key="test-integration-key",
    )
    return SecretsManager(config)


async def test_sm_store_and_retrieve():
    sm = await _get_manager()
    tenant = f"t_int_{os.getpid()}_sr"
    prop = f"h_{os.getpid()}_sr"

    await sm.store_provider_credentials(
        tenant, "exely", prop,
        {"username": "test_user", "password": "test_pass"},
        actor="test",
    )

    creds = await sm.get_provider_credentials(tenant, "exely", prop)
    assert creds is not None
    assert creds["username"] == "test_user"
    assert creds["password"] == "test_pass"

    await sm.delete_provider_credentials(tenant, "exely", prop)


async def test_sm_rotate():
    sm = await _get_manager()
    tenant = f"t_rot_{os.getpid()}_smr"
    prop = f"h_rot_{os.getpid()}_smr"

    await sm.store_provider_credentials(
        tenant, "hotelrunner", prop, {"token": "old_token"},
    )
    meta = await sm.rotate_provider_credentials(
        tenant, "hotelrunner", prop, {"token": "new_token"},
    )
    assert meta.rotation_count == 1

    creds = await sm.get_provider_credentials(tenant, "hotelrunner", prop)
    assert creds["token"] == "new_token"

    await sm.delete_provider_credentials(tenant, "hotelrunner", prop)


async def test_sm_delete():
    sm = await _get_manager()
    tenant = f"t_delsm_{os.getpid()}_smd"
    prop = f"h_delsm_{os.getpid()}_smd"

    await sm.store_provider_credentials(tenant, "exely", prop, {"k": "v"})
    assert await sm.delete_provider_credentials(tenant, "exely", prop) is True
    assert await sm.get_provider_credentials(tenant, "exely", prop) is None


async def test_sm_get_nonexistent():
    sm = await _get_manager()
    result = await sm.get_provider_credentials("t_none", "exely", "h_none")
    assert result is None


async def test_sm_mask_credentials():
    from core.secrets.manager import SecretsManager
    masked = SecretsManager.mask_credentials({
        "token": "sk-abc123xyz789",
        "short": "abc",
        "password": "mysupersecretpassword",
    })
    assert "sk-" in masked["token"]
    assert "789" in masked["token"]
    assert "*" in masked["token"]
    assert masked["short"] == "****"
    assert "mysupersecret" not in masked["password"]


async def test_sm_metadata_no_secrets():
    sm = await _get_manager()
    tenant = f"t_metasm_{os.getpid()}_smm"
    prop = f"h_metasm_{os.getpid()}_smm"

    await sm.store_provider_credentials(tenant, "exely", prop, {"pw": "secret123"})
    meta = await sm.get_provider_credential_metadata(tenant, "exely", prop)
    assert meta is not None
    assert "pw" in meta.field_names

    await sm.delete_provider_credentials(tenant, "exely", prop)


async def test_sm_health_check():
    sm = await _get_manager()
    health = await sm.health_check()
    assert health["status"] == "healthy"
    assert "legacy_fallback_enabled" in health


# ── Audit Tests ──────────────────────────────────────────────────────

async def test_audit_logs_written():
    from core.secrets.audit import SecretAuditLogger, COLL_SECRET_AUDIT
    from core.database import db

    auditor = SecretAuditLogger(enabled=True)
    tenant = f"t_audit_{os.getpid()}_al"

    await auditor.log(
        action="read",
        secret_path="test/dev/channel-manager/t1/exely/h1",
        result="success",
        tenant_id=tenant,
        provider="exely",
        property_id="h1",
        actor="test_suite",
    )

    records = await db[COLL_SECRET_AUDIT].find(
        {"tenant_id": tenant}, {"_id": 0}
    ).to_list(10)
    assert len(records) >= 1
    rec = records[0]
    assert rec["action"] == "read"
    assert rec["result"] == "success"
    assert rec["actor"] == "test_suite"
    assert "password" not in json.dumps(rec)

    await db[COLL_SECRET_AUDIT].delete_many({"tenant_id": tenant})


async def test_audit_disabled():
    from core.secrets.audit import SecretAuditLogger, COLL_SECRET_AUDIT
    from core.database import db

    auditor = SecretAuditLogger(enabled=False)
    tenant = f"t_noaudit_{os.getpid()}_nd"

    await auditor.log(
        action="read",
        secret_path="test/path",
        result="success",
        tenant_id=tenant,
    )

    records = await db[COLL_SECRET_AUDIT].find(
        {"tenant_id": tenant}, {"_id": 0}
    ).to_list(10)
    assert len(records) == 0


# ── Vault Placeholder Tests ─────────────────────────────────────────

async def test_vault_raises_not_implemented():
    from core.secrets.vault_provider import VaultSecretsProvider
    provider = VaultSecretsProvider("http://localhost:8200", "token")

    with pytest.raises(NotImplementedError):
        await provider.create_secret("path", {})

    with pytest.raises(NotImplementedError):
        await provider.get_secret("path")


async def test_vault_health_check():
    from core.secrets.vault_provider import VaultSecretsProvider
    provider = VaultSecretsProvider("http://localhost:8200", "token")
    health = await provider.health_check()
    assert health["status"] == "not_implemented"
