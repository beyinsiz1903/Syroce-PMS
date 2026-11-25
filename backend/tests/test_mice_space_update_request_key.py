"""Catalog edits must preserve creation idempotency under the real unique index."""
import pytest

from routers import mice
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.mark.asyncio
async def test_two_legacy_spaces_can_be_deactivated_without_inserting_null_request_keys(wired):  # noqa: F811
    await wired.mice_spaces.create_index(
        [("tenant_id", 1), ("client_request_id", 1)], unique=True,
        partialFilterExpression={"client_request_id": {"$exists": True}},
        name="uq_mice_spaces_tenant_client_req",
    )
    for sid in ("legacy-one", "legacy-two"):
        await wired.mice_spaces.insert_one({"id": sid, "tenant_id": "A", "name": "v11", "active": True})
    for sid in ("legacy-one", "legacy-two"):
        await mice.update_space(sid, mice.FunctionSpaceIn(name="v11", active=False), USER)
    for sid in ("legacy-one", "legacy-two"):
        saved = await wired.mice_spaces.find_one({"id": sid, "tenant_id": "A"})
        assert saved["active"] is False
        assert "client_request_id" not in saved


@pytest.mark.asyncio
@pytest.mark.parametrize("submitted", [None, "another-creation-key"])
async def test_edit_cannot_clear_or_replace_the_original_creation_key(wired, submitted):  # noqa: F811
    await wired.mice_spaces.insert_one({"id": "hall", "tenant_id": "A", "name": "Hall",
                                        "client_request_id": "original-creation-key"})
    await mice.update_space("hall", mice.FunctionSpaceIn(name="Renamed", client_request_id=submitted), USER)
    saved = await wired.mice_spaces.find_one({"id": "hall", "tenant_id": "A"})
    assert saved["name"] == "Renamed"
    assert saved["client_request_id"] == "original-creation-key"
