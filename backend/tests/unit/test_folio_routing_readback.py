"""Automatic posting metadata must not invalidate the routing list response."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from domains.pms import folio_routing_router as api


def instruction(**extra):
    return {'id': 'rule', 'tenant_id': 'hotel', 'created_by': 'operator',
            'created_at': '2026-11-22T12:00:00+00:00', 'active': True,
            'source_folio_id': 'source', 'dest_folio_id': 'target',
            'charge_codes': ['LAUNDRY'], 'from_date': '2026-11-12',
            'to_date': '2026-11-12', 'apply_to_future': True, **extra}


@pytest.mark.asyncio
async def test_used_rule_can_be_listed_without_exposing_storage_metadata(monkeypatch):
    stored = instruction(posting_revision=2, internal_storage_marker='not-an-api-field')
    queries = []

    class Collection:
        def find(self, query):
            queries.append(query)
            return self

        def sort(self, *_args):
            return self

        async def to_list(self, _limit):
            return [deepcopy(stored)]

    monkeypatch.setattr(api, '_ensure_indexes', AsyncMock())
    monkeypatch.setattr(api, 'get_system_db', lambda: SimpleNamespace(folio_routing=Collection()))
    app = FastAPI()

    @app.get('/routing', response_model=list[api.RoutingInstruction])
    async def readback():
        return await api.list_routing('source', SimpleNamespace(tenant_id='hotel'), None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/routing')
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row['id'] == 'rule' and row['apply_to_future'] is True
    assert row['charge_codes'] == ['LAUNDRY']
    assert 'posting_revision' not in row and 'internal_storage_marker' not in row
    assert stored['posting_revision'] == 2
    assert queries == [{'tenant_id': 'hotel', 'active': True,
                        '$or': [{'source_folio_id': 'source'}, {'dest_folio_id': 'source'}]}]


def test_create_still_rejects_internal_metadata_and_unknown_input():
    payload = {'source_folio_id': 'source', 'dest_folio_id': 'target', 'posting_revision': 2}
    with pytest.raises(ValidationError, match='extra_forbidden'):
        api.RoutingInstructionCreate.model_validate(payload)


@pytest.mark.parametrize('fields', [
    {'source_folio_id': 'target'},
    {'from_date': '2026-11-13', 'to_date': '2026-11-12'},
])
def test_response_still_rejects_invalid_routing_semantics(fields):
    with pytest.raises(ValidationError):
        api.RoutingInstruction.model_validate(instruction(posting_revision=1, **fields))
