"""PII access regression checks for the mobile unified search."""

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import search


@pytest.mark.asyncio
async def test_unified_search_requires_guest_list_permission():
    dependency = inspect.signature(search.unified_search).parameters["_guest_access"].default.dependency

    with pytest.raises(HTTPException) as error:
        await dependency(SimpleNamespace(role="housekeeping", granted_permissions=None))

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_unified_search_allows_frontdesk_guest_access():
    dependency = inspect.signature(search.unified_search).parameters["_guest_access"].default.dependency

    await dependency(SimpleNamespace(role="front_desk", granted_permissions=None))
