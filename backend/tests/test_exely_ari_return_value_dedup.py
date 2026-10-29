"""Offline regression: A -> B -> A is a new state, not a duplicate of old A."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.ari import repositories as repo


def change(value=3, *, minute=0, **updates):
    payload = {'operation': 'availability', 'availability': value}
    row = {'id': f'cs-{minute}-{value}', 'tenant_id': 'tenant', 'provider': 'exely',
        'property_id': 'property', 'room_type_code': 'room', 'rate_plan_code': 'rate',
        'date_from': '2026-11-10', 'date_to': '2026-11-11', 'change_scope': 'availability',
        'compacted_payload': payload, 'status': 'acked',
        'last_provider_ack_at': (datetime.now(UTC) - timedelta(minutes=minute)).isoformat()}
    row.update(updates)
    row['provider_delta_hash'] = repo.compute_outbound_delta_hash(
        row['provider'], row['property_id'], row['room_type_code'], row['rate_plan_code'],
        row['date_from'], row['date_to'], row['compacted_payload'])
    return row


def matches(row, query):
    for key, wanted in query.items():
        if key == '$or':
            if not any(matches(row, part) for part in wanted):
                return False
            continue
        value = row
        for part in key.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(wanted, dict):
            for op, other in wanted.items():
                if op == '$gte' and (value is None or value < other):
                    return False
                if op == '$lte' and (value is None or value > other):
                    return False
                if op == '$ne' and value == other:
                    return False
                if op == '$exists' and (value is not None) != other:
                    return False
        elif value != wanted:
            return False
    return True


class MemoryCollection:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.queries = []

    async def find_one(self, query, projection=None, *, sort=None):
        self.queries.append(deepcopy(query))
        rows = [r for r in self.rows if matches(r, query)]
        for field, direction in reversed(sort or []):
            rows.sort(key=lambda row: row.get(field, ''), reverse=direction < 0)
        return deepcopy(rows[0]) if rows else None


@pytest.fixture
def history(monkeypatch):
    def use(rows):
        collection = MemoryCollection(rows)
        monkeypatch.setattr(repo, 'db', {repo.COLL_ARI_CHANGE_SETS: collection})
        return collection
    return use


async def check(cs):
    return await repo.check_outbound_idempotency(
        cs['provider'], cs['property_id'], cs['provider_delta_hash'], change_set=cs)


@pytest.mark.asyncio
async def test_return_to_prior_value_must_be_sent(history):
    history([change(3, minute=5), change(2, minute=2)])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_identical_current_value_is_still_suppressed(history):
    history([change(2, minute=5), change(3, minute=2)])
    assert await check(change(3)) is True


@pytest.mark.asyncio
@pytest.mark.parametrize('foreign', [{'tenant_id': 'other'}, {'provider': 'hotelrunner'},
    {'property_id': 'other'}, {'room_type_code': 'other'},
    {'date_from': '2026-12-01', 'date_to': '2026-12-02'}])
async def test_foreign_or_disjoint_history_cannot_suppress(history, foreign):
    history([change(3, minute=2, **foreign)])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_partial_overlapping_newer_value_invalidates_old_full_range(history):
    history([change(3, minute=5), change(2, minute=2, date_to='2026-11-10')])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_availability_changed_through_another_rate_is_still_newer(history):
    history([change(3, minute=5), change(2, minute=2, rate_plan_code='other')])
    assert await check(change(3)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['pending', 'pushed', 'manual_review', 'skipped', 'failed_permanent'])
async def test_only_confirmed_ack_can_establish_equal_state(history, status):
    history([change(3, minute=2, status=status)])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_ack_timestamp_not_insertion_order_is_used(history):
    history([change(3, minute=2), change(2, minute=5)])
    assert await check(change(3)) is True


@pytest.mark.asyncio
async def test_equal_timestamp_with_conflicting_payload_cannot_prove_duplicate(history):
    first = change(3, minute=2)
    second = change(2, minute=2, last_provider_ack_at=first['last_provider_ack_at'])
    history([first, second])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_old_ack_does_not_suppress_a_fresh_operation(history):
    history([change(3, minute=61)])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_latest_full_range_can_reestablish_original_value(history):
    history([change(3, minute=9), change(2, minute=5), change(3, minute=2)])
    assert await check(change(3)) is True


@pytest.mark.asyncio
async def test_exely_context_is_required_without_database_access(history):
    collection = history([change(3, minute=2)])
    with pytest.raises(ValueError, match='exact tenant-scoped'):
        await repo.check_outbound_idempotency('exely', 'property', change()['provider_delta_hash'])
    assert not collection.queries


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [{'tenant_id': ''}, {'room_type_code': ''},
    {'provider': 'other'}, {'property_id': 'other'}, {'provider_delta_hash': 'wrong'},
    {'change_scope': 'other'}, {'date_from': 'bad'},
    {'date_from': '2026-11-12', 'date_to': '2026-11-10'}])
async def test_malformed_context_fails_before_lookup(history, invalid):
    collection = history([])
    current = change()
    current.update(invalid)
    with pytest.raises(ValueError):
        await repo.check_outbound_idempotency('exely', 'property', change()['provider_delta_hash'],
                                             change_set=current)
    assert not collection.queries


def scoped_change(scope, value, *, operation=None, **updates):
    operation = operation or ('rate' if scope == 'rate' else 'cta')
    key = 'base_rate' if scope == 'rate' else operation
    return change(compacted_payload={'operation': operation, key: value},
                  change_scope=scope, **updates)


@pytest.mark.asyncio
@pytest.mark.parametrize('scope', ['rate', 'restriction'])
async def test_rate_and_restriction_return_values_are_not_historical_duplicates(history, scope):
    history([scoped_change(scope, 3, minute=5), scoped_change(scope, 2, minute=2)])
    assert await check(scoped_change(scope, 3)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize('scope', ['rate', 'restriction'])
async def test_another_rate_does_not_override_current_rate_state(history, scope):
    history([scoped_change(scope, 3, minute=5),
             scoped_change(scope, 2, minute=2, rate_plan_code='other')])
    assert await check(scoped_change(scope, 3)) is True


@pytest.mark.asyncio
async def test_independent_restriction_operation_is_not_a_state_change(history):
    history([scoped_change('restriction', False, operation='cta', minute=5),
             scoped_change('restriction', True, operation='ctd', minute=2)])
    assert await check(scoped_change('restriction', False, operation='cta')) is True


@pytest.mark.asyncio
async def test_legacy_unspecified_restriction_cannot_prove_current_equal_state(history):
    legacy = scoped_change('restriction', True, minute=2)
    legacy['compacted_payload'].pop('operation')
    legacy['provider_delta_hash'] = 'unknown-legacy'
    history([scoped_change('restriction', False, minute=5), legacy])
    assert await check(scoped_change('restriction', False)) is False


@pytest.mark.asyncio
async def test_other_provider_keeps_legacy_call_contract(history):
    current = change(provider='hotelrunner')
    history([change(provider='hotelrunner', minute=2)])
    assert await repo.check_outbound_idempotency(
        current['provider'], current['property_id'], current['provider_delta_hash']) is True


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['worker', 'manual'])
@pytest.mark.parametrize('current_value,expected_calls', [(2, 1), (3, 0)])
async def test_both_push_paths_use_current_state_and_keep_duplicate_guard(
    history, monkeypatch, path, current_value, expected_calls,
):
    from domains.channel_manager.ari import hard_fail_gate, outbound_service, push_loop_worker
    from domains.channel_manager.ari.events import ProviderResult

    # Requested A=3. Latest B=2 must send; latest A=3 must still be skipped.
    history([change(3, minute=5), change(current_value, minute=2)])
    current = change(status='pending', outbound_change_id='one-new-operation')
    monkeypatch.setattr(repo, 'get_pending_change_sets', AsyncMock(return_value=[current]))
    status = AsyncMock()
    monkeypatch.setattr(repo, 'update_change_set_status', status)
    gate = AsyncMock(return_value=hard_fail_gate.HardFailVerdict(passed=True))
    monkeypatch.setattr(hard_fail_gate, 'enforce_hard_fail_gate', gate)
    monkeypatch.setattr(push_loop_worker, 'enforce_hard_fail_gate', gate)
    monkeypatch.setattr(outbound_service.rate_limiter, 'acquire', AsyncMock(return_value=True))
    monkeypatch.setattr(push_loop_worker.rate_limiter, 'acquire', AsyncMock(return_value=True))
    ack = AsyncMock(return_value='acked')
    monkeypatch.setattr(outbound_service, 'process_ack', ack)
    monkeypatch.setattr(push_loop_worker, 'process_ack', ack)
    adapter = AsyncMock()
    adapter.push_availability.return_value = ProviderResult(success=True, provider='exely', status_code=200)
    if path == 'worker':
        worker = push_loop_worker.PushLoopWorker()
        worker.register_adapter('exely', adapter)
        await worker._process_tenant('tenant')
    else:
        monkeypatch.setattr(outbound_service, '_PROVIDER_ADAPTERS', {'exely': adapter})
        await outbound_service.push_pending_changes('tenant', 'exely')
    assert adapter.push_availability.await_count == expected_calls
    assert ack.await_count == expected_calls
    if not expected_calls:
        status.assert_awaited_once_with(current['id'], 'skipped')
