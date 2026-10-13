from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import agency_content as content
from routers import agency_contracts


def complete():
    return {'hotel_name': 'Hotel', 'city': 'Kartepe', 'country': 'TR', 'address': 'Address',
            'description': 'Description', 'meal_plans': ['RO'], 'images': ['/cover.jpg'],
            'room_types': [{'room_type': 'standard', 'images': ['/room.jpg']}], 'content_version': 3}


def test_complete_content_is_not_a_sales_permission():
    result = content.content_readiness(complete(), {'property_name': 'Hotel'})
    assert result['ready'] and result['can_publish']
    assert 'is_listed' not in result


def test_missing_catalog_fields_and_name_mismatch_are_explicit():
    row = complete()
    row.update(city='', meal_plans=[], images=[], hotel_name='Test Hotel Updated')
    result = content.content_readiness(row, {'property_name': 'Syroce Demo Hotel'})
    assert not result['ready'] and result['can_publish']
    assert len(result['warnings']) == 4
    assert result['tenant_name'] == 'Syroce Demo Hotel'
    assert not content.content_readiness({}, {})['can_publish']


@pytest.mark.asyncio
async def test_readiness_is_tenant_scoped_read_only_and_separates_access(monkeypatch):
    tenant = SimpleNamespace(hotel_content=SimpleNamespace(find_one=AsyncMock(return_value=complete())),
        tenants=SimpleNamespace(find_one=AsyncMock(return_value={'property_name': 'Hotel'})),
        agencies=SimpleNamespace(count_documents=AsyncMock(return_value=0)))
    listings = SimpleNamespace(find_one=AsyncMock(return_value={'is_listed': True}))
    monkeypatch.setattr(content, 'db', tenant)
    monkeypatch.setattr(content, 'get_system_db', lambda: SimpleNamespace(marketplace_listings=listings))
    partners = AsyncMock(return_value=['a', 'b'])
    monkeypatch.setattr(agency_contracts, 'list_active_agencies_for_tenant', partners)
    user = SimpleNamespace(tenant_id='t', role='admin', roles=[])
    result = await content.get_content_readiness(user)
    assert result['access'] == {'hotel_portal_published_count': 0, 'marketplace_listed': True, 'marketplace_active_contract_count': 2}
    partners.assert_awaited_once_with('t')
    assert tenant.hotel_content.find_one.call_args.args[0] == {'tenant_id': 't'}
    assert listings.find_one.call_args.args[0] == {'tenant_id': 't'}


@pytest.mark.asyncio
async def test_agency_cannot_inspect_staff_readiness():
    with pytest.raises(HTTPException) as error:
        await content.get_content_readiness(SimpleNamespace(tenant_id='t', role='agency_agent', roles=[]))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_empty_selection_requires_explicit_revoke_and_does_not_touch_marketplace(monkeypatch):
    agencies = SimpleNamespace(update_many=AsyncMock(return_value=SimpleNamespace(modified_count=1)), count_documents=AsyncMock(return_value=0))
    monkeypatch.setattr(content, 'db', SimpleNamespace(hotel_content=SimpleNamespace(find_one=AsyncMock(return_value=None)), agencies=agencies))
    user = SimpleNamespace(tenant_id='t', id='u', role='admin', roles=[])
    with pytest.raises(HTTPException):
        await content.distribute_content(content.ContentDistributeRequest(agency_ids=[]), user)
    agencies.update_many.assert_not_awaited()
    result = await content.distribute_content(content.ContentDistributeRequest(agency_ids=[], unpublish_omitted=True), user)
    assert result['removed'] == 1
    assert agencies.update_many.call_args.args[0]['tenant_id'] == 't'
    assert agencies.update_many.call_args.args[1]['$set']['published_content'] is False


@pytest.mark.asyncio
async def test_changed_content_requires_new_confirmation(monkeypatch):
    agencies = SimpleNamespace(update_many=AsyncMock())
    monkeypatch.setattr(content, 'db', SimpleNamespace(hotel_content=SimpleNamespace(find_one=AsyncMock(return_value=complete())), agencies=agencies))
    with pytest.raises(HTTPException) as error:
        await content.distribute_content(content.ContentDistributeRequest(agency_ids=['a'], expected_content_version=2),
                                         SimpleNamespace(tenant_id='t', role='admin', roles=[]))
    assert error.value.status_code == 409
    agencies.update_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_preview_reports_last_published_agency(monkeypatch):
    class Cursor:
        def __aiter__(self):
            async def rows():
                yield {'id': 'a'}
            return rows()
    queries = []
    def find(query, projection):
        queries.append(query)
        return Cursor()
    monkeypatch.setattr(content, 'db', SimpleNamespace(agencies=SimpleNamespace(find=find)))
    result = await content.distribute_preview('', SimpleNamespace(tenant_id='t', role='admin', roles=[]))
    assert result == {'to_add': 0, 'to_remove': 1, 'currently_published': 1, 'selected': 0}
    assert queries == [{'tenant_id': 't', 'published_content': True}]
