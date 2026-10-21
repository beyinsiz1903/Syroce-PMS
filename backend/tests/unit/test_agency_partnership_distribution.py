"""No real hotel data, provider calls or outbound messages in these checks."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.pending_actions import contract_items
from domains.channel_manager import unified_rate_manager_router as rates
from routers import agency_contracts as contracts
from tests.unit.test_agency_statements_symmetric import _Coll, _match

HOTEL = SimpleNamespace(id='u1', email='hotel@example.invalid', tenant_id='t1', role='admin', roles=[])
AGENCY = {'agency_id': 'a1', 'agency_name': 'Test Agency', 'contact_email': 'agency@example.invalid'}
BASE = {'id': 'c1', 'contract_code': 'TEST-1', 'tenant_id': 't1', 'agency_id': 'a1', 'status': 'pending',
        'commission_pct': 12, 'valid_from': '2026-01-01', 'valid_to': '2027-12-31', 'currency': 'EUR',
        'agency_name': 'Test Agency', 'hotel_name': 'Test Hotel', 'agency_confirmed_at': '2026-01-01', 'awaiting_party': 'hotel'}


class Collection(_Coll):
    async def create_index(self, *args, **kwargs):
        return 'test_index'

    async def update_one(self, query, update):
        found = await self.find_one_and_update(query, update)
        return SimpleNamespace(matched_count=int(found is not None), modified_count=int(found is not None))

    async def update_many(self, query, update):
        count = 0
        for row in self.rows:
            if _match(row, query):
                row.update(copy.deepcopy(update.get('$set', {})))
                count += 1
        return SimpleNamespace(modified_count=count)


@pytest.fixture
def world(monkeypatch):
    db = SimpleNamespace(agency_contracts=Collection([BASE]), agency_contract_events=Collection(),
                         agency_partnership_requests=Collection(), marketplace_agencies=Collection([
                             {'id': 'a1', 'name': 'Test Agency', 'status': 'active'},
                             {'id': 'a2', 'name': 'Disabled', 'status': 'inactive'},
                         ]))
    monkeypatch.setattr(contracts, 'get_system_db', lambda: db)
    monkeypatch.setattr(contracts, '_notify_contract_decision', AsyncMock())
    monkeypatch.setattr(contracts, '_auto_expire_overdue', AsyncMock(return_value=0))
    monkeypatch.setattr(contracts, '_listing_dep', AsyncMock(return_value={'hotel_name': 'Test Hotel'}))
    monkeypatch.setattr(contracts, '_ensure_indexes', AsyncMock())
    monkeypatch.setattr(rates, 'db', SimpleNamespace(agency_contracts=Collection()))
    return db


@pytest.mark.asyncio
async def test_hotel_invitation_does_not_grant_a_contract_or_rate_access(world):
    world.agency_contracts.rows.clear()
    result = await contracts.hotel_request_partnership(contracts.PartnershipRequestCreate(agency_id='a1'), HOTEL, None)
    assert result['request']['status'] == 'pending'
    assert world.agency_contracts.rows == []
    assert await contracts.has_active_contract('a1', 't1') is None
    assert len((await contracts.agency_partnership_requests(AGENCY))['requests']) == 1
    assert not (await contracts.agency_partnership_requests({'agency_id': 'other'}))['requests']
    with pytest.raises(HTTPException) as other:
        await contracts.agency_decline_partnership(result['request']['id'], {'agency_id': 'other'})
    assert other.value.status_code == 404
    await contracts.agency_decline_partnership(result['request']['id'], AGENCY)
    assert not (await contracts.agency_partnership_requests(AGENCY))['requests']


@pytest.mark.asyncio
@pytest.mark.parametrize('agency_id', ['missing', 'a2'])
async def test_hotel_cannot_invite_missing_or_disabled_agencies(world, agency_id):
    with pytest.raises(HTTPException) as failure:
        await contracts.hotel_request_partnership(contracts.PartnershipRequestCreate(agency_id=agency_id), HOTEL, None)
    assert failure.value.status_code == 404
    assert not world.agency_partnership_requests.rows


@pytest.mark.asyncio
async def test_existing_pending_contract_prevents_duplicate_invitation(world):
    with pytest.raises(HTTPException) as failure:
        await contracts.hotel_request_partnership(contracts.PartnershipRequestCreate(agency_id='a1'), HOTEL, None)
    assert failure.value.status_code == 409


@pytest.mark.asyncio
async def test_unchanged_proposal_is_mutually_approved(world):
    result = await contracts.hotel_approve_request('c1', contracts.ApproveRequest(), HOTEL, None)
    assert result['contract']['status'] == 'approved'
    assert result['contract']['agency_confirmed_at']
    assert result['contract']['hotel_confirmed_at']


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'commission_pct_override': 10}, {'allow_base_rate_fallback': True}, {'credit_limit': 500, 'credit_currency': 'EUR'}])
async def test_changed_terms_do_not_open_sales_until_the_agency_accepts(world, change):
    offered = await contracts.hotel_approve_request('c1', contracts.ApproveRequest(**change), HOTEL, None)
    assert offered['contract']['status'] == 'pending'
    assert offered['contract']['awaiting_party'] == 'agency'
    assert await contracts.has_active_contract('a1', 't1') is None
    assert contract_items(offered['contract'], 'agency')[0]['owner'] == 'yours'
    assert contract_items(offered['contract'], 'hotel')[0]['owner'] == 'theirs'
    with pytest.raises(HTTPException) as self_approval:
        await contracts.hotel_approve_request('c1', contracts.ApproveRequest(), HOTEL, None)
    assert self_approval.value.status_code == 409
    with pytest.raises(HTTPException) as foreign:
        await contracts.agency_accept_counteroffer('c1', {'agency_id': 'other'})
    assert foreign.value.status_code == 409
    accepted = await contracts.agency_accept_counteroffer('c1', AGENCY)
    assert accepted['contract']['status'] == 'approved'
    assert accepted['contract']['awaiting_party'] is None
    with pytest.raises(HTTPException):
        await contracts.agency_accept_counteroffer('c1', AGENCY)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['pending', 'terminated', 'expired', 'rejected', 'withdrawn'])
async def test_rates_require_an_actual_approved_contract(world, monkeypatch, status):
    world.agency_contracts.rows[0]['status'] = status
    monkeypatch.setattr(rates, '_active_agency_docs_for_tenant', AsyncMock(return_value=[{'id': 'a1'}]))
    with pytest.raises(HTTPException) as failure:
        await rates._require_contracted_agency_targets('t1', ['a1'], '2026-11-01', '2026-11-30')
    assert failure.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'tenant_id': 'other'}, {'valid_to': '2026-11-10'}, {'valid_from': '2026-12-01'}])
async def test_rate_targets_are_scoped_to_hotel_and_entire_date_range(world, monkeypatch, changes):
    world.agency_contracts.rows[0].update(status='approved', **changes)
    monkeypatch.setattr(rates, '_active_agency_docs_for_tenant', AsyncMock(return_value=[{'id': 'a1'}]))
    with pytest.raises(HTTPException):
        await rates._require_contracted_agency_targets('t1', ['a1'], '2026-11-01', '2026-11-30')


@pytest.mark.asyncio
async def test_mixed_invalid_targets_block_before_any_calendar_or_channel_write(world, monkeypatch):
    world.agency_contracts.rows[0]['status'] = 'approved'
    monkeypatch.setattr(rates, '_active_agency_docs_for_tenant', AsyncMock(return_value=[{'id': 'a1'}, {'id': 'no-contract'}]))
    monkeypatch.setattr(rates, '_detect_active_provider', AsyncMock(return_value={'provider': 'exely', 'connection': {}}))
    monkeypatch.setattr(rates, 'require_tenant_module', AsyncMock())
    push = AsyncMock()
    monkeypatch.setattr(rates, '_push_to_exely', push)
    calendar = SimpleNamespace(bulk_write=AsyncMock())
    monkeypatch.setattr(rates, 'db', SimpleNamespace(rate_calendar=calendar, agency_contracts=Collection()))
    request = rates.UnifiedBulkUpdateRequest(start_date='2026-11-01', end_date='2026-11-30',
        agency_ids=['a1', 'no-contract'], room_type_codes=['Standard'], rate_plan_codes=['AGENCY'], rate=100, update_fields=['rate'])
    with pytest.raises(HTTPException) as failure:
        await rates.unified_bulk_grid_update(request, HOTEL, None)
    assert failure.value.status_code == 403
    push.assert_not_awaited()
    calendar.bulk_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_channel_and_no_contract_still_opens_the_agency_workspace(monkeypatch):
    monkeypatch.setattr(rates, '_detect_active_provider', AsyncMock(return_value={'provider': None, 'connection': {}}))
    monkeypatch.setattr(rates, 'db', SimpleNamespace(rooms=SimpleNamespace(distinct=AsyncMock(return_value=['Standard']))))
    result = await rates.detect_provider(HOTEL)
    assert result['provider'] == 'agency' and result['has_connection'] is False


def test_directory_routes_are_not_shadowed_by_contract_id_route():
    paths = [r.path for r in contracts.hotel_router.routes]
    assert paths.index('/api/marketplace/incoming-requests/agency-candidates') < paths.index('/api/marketplace/incoming-requests/{contract_id}')


@pytest.mark.asyncio
async def test_only_the_hotel_that_requested_a_partnership_can_withdraw_it(world):
    world.agency_contracts.rows.clear()
    result = await contracts.hotel_request_partnership(contracts.PartnershipRequestCreate(agency_id='a1'), HOTEL, None)
    request_id = result['request']['id']
    foreign = SimpleNamespace(**{**vars(HOTEL), 'tenant_id': 'other'})
    with pytest.raises(HTTPException) as failure:
        await contracts.hotel_withdraw_partnership(request_id, foreign, None)
    assert failure.value.status_code == 404
    await contracts.hotel_withdraw_partnership(request_id, HOTEL, None)
    assert not (await contracts.agency_partnership_requests(AGENCY))['requests']


@pytest.mark.asyncio
async def test_agency_cannot_approve_its_own_original_offer(world):
    with pytest.raises(HTTPException) as failure:
        await contracts.agency_accept_counteroffer('c1', AGENCY)
    assert failure.value.status_code == 409


@pytest.mark.asyncio
async def test_recorded_legacy_agreement_is_required_not_just_an_active_agency(world, monkeypatch):
    world.agency_contracts.rows.clear()
    local = Collection([{'id': 'legacy', 'tenant_id': 't1', 'agency_id': 'a1', 'is_active': True,
                         'start_date': '2026-01-01', 'end_date': '2027-12-31'}])
    monkeypatch.setattr(rates, 'db', SimpleNamespace(agency_contracts=local))
    monkeypatch.setattr(rates, '_active_agency_docs_for_tenant', AsyncMock(return_value=[{'id': 'a1'}]))
    await rates._require_contracted_agency_targets('t1', ['a1'], '2026-11-01', '2026-11-30')
    local.rows[0]['is_active'] = False
    with pytest.raises(HTTPException):
        await rates._require_contracted_agency_targets('t1', ['a1'], '2026-11-01', '2026-11-30')


@pytest.mark.asyncio
async def test_legacy_portal_rejects_price_queries_and_new_sales_without_agreement(monkeypatch):
    from routers import agency_portal as portal
    user = SimpleNamespace(tenant_id='t1', agency_id='a1')
    monkeypatch.setattr(portal, '_require_agency_user', lambda _user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a1'}))
    monkeypatch.setattr(portal, 'db', SimpleNamespace(agency_contracts=Collection()))
    assert await portal.agency_portal_content(user) == {'published': False, 'hotel_content': None}
    with pytest.raises(HTTPException) as query:
        await portal.agency_portal_availability('2026-11-01', '2026-11-02', 2, 0, user)
    assert query.value.status_code == 403
    with pytest.raises(HTTPException) as sale:
        await portal.agency_portal_create_reservation(SimpleNamespace(check_in='2026-11-01', check_out='2026-11-02'), user)
    assert sale.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('event', ['rates.updated', 'availability.updated'])
async def test_queued_rate_webhooks_stop_when_the_contract_is_no_longer_valid(monkeypatch, event):
    from core import tenant_db
    from integrations.xchange import safety
    from routers import webhook_retry_service as delivery
    database = SimpleNamespace(webhook_deliveries=Collection())
    monkeypatch.setattr(tenant_db, 'get_system_db', lambda: database)
    monkeypatch.setattr(delivery, 'emit_ops_event', AsyncMock())
    monkeypatch.setattr(rates, '_require_contracted_agency_targets', AsyncMock(side_effect=HTTPException(403, 'No agreement')))
    send = AsyncMock()
    monkeypatch.setattr(safety, 'safe_post_async', send)
    result = await delivery.deliver_webhook_with_retry({'id': 'wh1', 'tenant_id': 't1', 'agency_id': 'a1', 'url': 'https://example.invalid'}, event, {})
    assert result['status'] == 'blocked' and result['error'] == 'AGENCY_CONTRACT_REQUIRED'
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_agency_grid_uses_hotel_sale_currency_instead_of_hardcoded_try(monkeypatch):
    empty = SimpleNamespace(find=lambda *_args: SimpleNamespace(to_list=AsyncMock(return_value=[])))
    monkeypatch.setattr(rates, 'db', SimpleNamespace(rooms=empty, rate_calendar=empty, pricing_settings=empty))
    monkeypatch.setattr(rates, '_get_room_counts', AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(rates, '_get_active_bookings', AsyncMock(return_value=[]))
    currency = AsyncMock(return_value='EUR')
    monkeypatch.setattr(rates, '_agency_rate_currency', currency)
    result = await rates._build_agency_grid('t1', '2026-11-01', '2026-11-02')
    assert result['currency'] == 'EUR'
    assert currency.await_args.args[-1] is True


@pytest.mark.asyncio
async def test_webhook_retry_rechecks_agreement_after_an_unsuccessful_attempt(monkeypatch):
    from core import tenant_db
    from integrations.xchange import safety
    from routers import webhook_retry_service as delivery
    database = SimpleNamespace(webhook_deliveries=Collection())
    monkeypatch.setattr(tenant_db, 'get_system_db', lambda: database)
    monkeypatch.setattr(delivery, 'emit_ops_event', AsyncMock())
    monkeypatch.setattr(delivery.asyncio, 'sleep', AsyncMock())
    check = AsyncMock(side_effect=[None, HTTPException(403, 'Terminated while queued')])
    monkeypatch.setattr(rates, '_require_contracted_agency_targets', check)
    send = AsyncMock(return_value=SimpleNamespace(status_code=500))
    monkeypatch.setattr(safety, 'safe_post_async', send)
    result = await delivery.deliver_webhook_with_retry({'id': 'wh1', 'tenant_id': 't1', 'agency_id': 'a1', 'url': 'https://example.invalid'}, 'rates.updated', {})
    assert result['status'] == 'blocked'
    assert check.await_count == 2
    send.assert_awaited_once()
