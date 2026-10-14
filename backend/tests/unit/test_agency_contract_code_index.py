"""Hotel-side legacy contracts share `agency_contracts` without a contract_code."""

import os
import uuid

import pytest

from routers.agency_contracts import CONTRACT_CODE_INDEX, CONTRACT_CODE_PARTIAL, _ensure_contract_code_index

motor_asyncio = pytest.importorskip("motor.motor_asyncio")
from pymongo.errors import DuplicateKeyError  # noqa: E402


@pytest.fixture
async def contracts():
    client = motor_asyncio.AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1500
    )
    try:
        await client.server_info()
    except Exception:
        pytest.skip("MongoDB is not reachable")
    name = f"contract_code_{uuid.uuid4().hex[:8]}"
    yield client[name].agency_contracts
    await client.drop_database(name)
    client.close()


@pytest.mark.asyncio
async def test_legacy_contracts_without_code_coexist_and_codes_stay_unique(contracts):
    await _ensure_contract_code_index(contracts)

    await contracts.insert_one({"id": "legacy-1", "contract_type": "commission"})
    await contracts.insert_one({"id": "legacy-2", "contract_type": "net_rate"})
    await contracts.insert_one({"id": "m1", "contract_code": "SOZ-2026-0001"})
    with pytest.raises(DuplicateKeyError):
        await contracts.insert_one({"id": "m2", "contract_code": "SOZ-2026-0001"})


@pytest.mark.asyncio
async def test_existing_full_unique_index_is_replaced(contracts):
    await contracts.create_index([("contract_code", 1)], unique=True, name=CONTRACT_CODE_INDEX)

    await _ensure_contract_code_index(contracts)
    await _ensure_contract_code_index(contracts)  # idempotent

    info = (await contracts.index_information())[CONTRACT_CODE_INDEX]
    assert info["partialFilterExpression"] == CONTRACT_CODE_PARTIAL
