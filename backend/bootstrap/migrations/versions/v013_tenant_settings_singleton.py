"""Make each tenant's settings document a database-enforced singleton."""

from __future__ import annotations

import pymongo.errors

from bootstrap.migrations.base import Migration

UNIQUE_INDEX = "ux_tenant_settings_tenant"
LEGACY_INDEX = "idx_tenant_settings_tenant"


class TenantSettingsSingletonMigration(Migration):
    version = "V013"
    description = "Enforce one tenant_settings document per tenant"

    async def up(self, db) -> None:
        collection = db.tenant_settings
        indexes = await collection.index_information()
        existing_unique = indexes.get(UNIQUE_INDEX) or {}
        if existing_unique.get("unique") is True:
            return

        duplicate = await collection.aggregate(
            [
                {"$match": {"tenant_id": {"$type": "string", "$ne": ""}}},
                {"$group": {"_id": "$tenant_id", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 1},
            ]
        ).to_list(length=1)
        if duplicate:
            tenant_id = duplicate[0].get("_id")
            raise RuntimeError(
                f"Duplicate tenant_settings rows for tenant {tenant_id!r}; "
                "resolve them before enabling singleton enforcement"
            )

        # MongoDB rejects an equivalent key pattern with different options.
        # Remove only the known legacy non-unique index after proving there are
        # no duplicate documents; the migration runner restores it on failure.
        if LEGACY_INDEX in indexes:
            await collection.drop_index(LEGACY_INDEX)
        await collection.create_index(
            [("tenant_id", 1)],
            name=UNIQUE_INDEX,
            unique=True,
        )

    async def down(self, db) -> None:
        collection = db.tenant_settings
        try:
            await collection.drop_index(UNIQUE_INDEX)
        except pymongo.errors.OperationFailure as exc:
            if exc.code != 27:
                raise
        indexes = await collection.index_information()
        if LEGACY_INDEX not in indexes:
            await collection.create_index(
                [("tenant_id", 1)],
                name=LEGACY_INDEX,
            )


MIGRATION = TenantSettingsSingletonMigration()
