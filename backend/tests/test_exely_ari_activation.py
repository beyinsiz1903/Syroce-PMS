from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.channel_manager.providers.exely import exely_router


def _user():
    return SimpleNamespace(tenant_id="tenant-1", name="Operator")


def _db(*, connection=None, mapping=None):
    return SimpleNamespace(
        exely_connections=SimpleNamespace(
            find_one=AsyncMock(return_value=connection),
            update_one=AsyncMock(),
        ),
        exely_room_mappings=SimpleNamespace(find_one=AsyncMock(return_value=mapping)),
    )


@pytest.mark.asyncio
async def test_exely_ari_activation_requires_exact_confirmation(monkeypatch):
    database = _db(connection={"is_active": True}, mapping={"_id": "mapping-1"})
    monkeypatch.setattr(exely_router, "db", database)

    with pytest.raises(HTTPException) as exc:
        await exely_router.update_ari_write_state(
            exely_router.ExelyARIWriteActivation(enabled=True, confirmation="yes"),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 400
    database.exely_connections.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_exely_ari_activation_is_tenant_scoped_and_probes_connection(monkeypatch):
    database = _db(
        connection={"tenant_id": "tenant-1", "is_active": True},
        mapping={"_id": "mapping-1"},
    )
    provider = SimpleNamespace(test_connection=AsyncMock(return_value=SimpleNamespace(success=True)))
    get_client = AsyncMock(return_value=(provider, {}))
    log_sync = AsyncMock()
    monkeypatch.setattr(exely_router, "db", database)
    monkeypatch.setattr(exely_router, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr(exely_router, "_get_client", get_client)
    monkeypatch.setattr(exely_router, "log_sync", log_sync)

    result = await exely_router.update_ari_write_state(
        exely_router.ExelyARIWriteActivation(
            enabled=True,
            confirmation="ENABLE_EXELY_ARI_WRITE",
        ),
        current_user=_user(),
        _perm=None,
    )

    assert result["ari_write_enabled"] is True
    database.exely_connections.update_one.assert_awaited_once()
    query, update = database.exely_connections.update_one.await_args.args
    assert query == {"tenant_id": "tenant-1", "is_active": True}
    assert update["$set"]["ari_write_enabled"] is True
    get_client.assert_awaited_once_with("tenant-1")
    provider.test_connection.assert_awaited_once()
    log_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_exely_ari_activation_fails_closed_without_mapping(monkeypatch):
    database = _db(connection={"tenant_id": "tenant-1", "is_active": True}, mapping=None)
    monkeypatch.setattr(exely_router, "db", database)
    monkeypatch.setattr(exely_router, "ari_write_block_reason", lambda: "")

    with pytest.raises(HTTPException) as exc:
        await exely_router.update_ari_write_state(
            exely_router.ExelyARIWriteActivation(
                enabled=True,
                confirmation="ENABLE_EXELY_ARI_WRITE",
            ),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "EXELY_ARI_MAPPING_REQUIRED"
    database.exely_connections.update_one.assert_not_awaited()
