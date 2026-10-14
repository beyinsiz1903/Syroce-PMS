"""Hotel-side legacy contracts share `agency_contracts` without a contract_code."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.agency_contracts import CONTRACT_CODE_INDEX, CONTRACT_CODE_PARTIAL, _ensure_contract_code_index


def _collection(existing):
    return SimpleNamespace(
        index_information=AsyncMock(return_value=existing),
        drop_index=AsyncMock(),
        create_index=AsyncMock(),
    )


def _assert_partial_unique(coll):
    args, kwargs = coll.create_index.await_args
    assert args == ([("contract_code", 1)],)
    assert kwargs == {"unique": True, "partialFilterExpression": CONTRACT_CODE_PARTIAL, "name": CONTRACT_CODE_INDEX}


@pytest.mark.asyncio
async def test_full_unique_index_is_replaced_by_partial_index():
    coll = _collection({CONTRACT_CODE_INDEX: {"key": [("contract_code", 1)], "unique": True}})
    await _ensure_contract_code_index(coll)
    coll.drop_index.assert_awaited_once_with(CONTRACT_CODE_INDEX)
    _assert_partial_unique(coll)


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [{}, {CONTRACT_CODE_INDEX: {"partialFilterExpression": CONTRACT_CODE_PARTIAL}}])
async def test_missing_or_current_index_is_not_dropped(existing):
    coll = _collection(existing)
    await _ensure_contract_code_index(coll)
    coll.drop_index.assert_not_awaited()
    _assert_partial_unique(coll)


def test_partial_filter_excludes_contracts_without_code():
    # Legacy hotel contracts have no contract_code at all; only string codes are unique.
    assert CONTRACT_CODE_PARTIAL == {"contract_code": {"$type": "string"}}
