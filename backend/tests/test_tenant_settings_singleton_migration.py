from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bootstrap.migrations.registry import discover_migrations
from bootstrap.migrations.versions.v013_tenant_settings_singleton import (
    LEGACY_INDEX,
    UNIQUE_INDEX,
    TenantSettingsSingletonMigration,
)


def _db(*, indexes, duplicates=()):
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=list(duplicates)))
    collection = SimpleNamespace(
        index_information=AsyncMock(return_value=indexes),
        aggregate=MagicMock(return_value=cursor),
        drop_index=AsyncMock(),
        create_index=AsyncMock(),
    )
    return SimpleNamespace(tenant_settings=collection), collection


def test_migration_is_discoverable_after_exely_migrations():
    versions = [migration.version for migration in discover_migrations()]
    assert "V013" in versions
    assert versions.index("V013") > versions.index("V012")


@pytest.mark.asyncio
async def test_migration_replaces_legacy_index_only_after_duplicate_check():
    database, collection = _db(indexes={LEGACY_INDEX: {"key": [("tenant_id", 1)]}})

    await TenantSettingsSingletonMigration().up(database)

    collection.drop_index.assert_awaited_once_with(LEGACY_INDEX)
    collection.create_index.assert_awaited_once_with(
        [("tenant_id", 1)],
        name=UNIQUE_INDEX,
        unique=True,
    )


@pytest.mark.asyncio
async def test_migration_fails_closed_without_deleting_duplicate_settings():
    database, collection = _db(
        indexes={LEGACY_INDEX: {"key": [("tenant_id", 1)]}},
        duplicates=[{"_id": "tenant-1", "count": 2}],
    )

    with pytest.raises(RuntimeError, match="Duplicate tenant_settings"):
        await TenantSettingsSingletonMigration().up(database)

    collection.drop_index.assert_not_awaited()
    collection.create_index.assert_not_awaited()
