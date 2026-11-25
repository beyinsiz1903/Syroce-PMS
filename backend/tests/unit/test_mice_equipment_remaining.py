"""Full-operation buttons complete partial movements without duplicating them."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import mice

USER = SimpleNamespace(tenant_id='hotel', username='operator', id='user', role='admin', roles=['admin'])


@pytest.fixture
def ledger(monkeypatch):
    task = {'id': 'equipment', 'kind': 'equipment', 'quantity': 2, 'status': 'acknowledged',
            'department': 'av', 'title': 'Projector', 'delivered_quantity': 2, 'returned_quantity': 1,
            'handovers': [{'request_id': 'deliver-once', 'action': 'deliver', 'quantity': 2},
                          {'request_id': 'return-once', 'action': 'return', 'quantity': 1}]}
    event = {'id': 'event', 'tenant_id': 'hotel', 'status': 'tentative', 'operations_tasks': [task]}

    class Events:
        async def find_one(self, query, *args, **kwargs):
            assert query == {'id': 'event', 'tenant_id': 'hotel'}
            return deepcopy(event)

        async def update_one(self, query, update, **kwargs):
            assert query == {'id': 'event', 'tenant_id': 'hotel'}
            for key, value in update['$set'].items():
                if key == 'operations_tasks.0':
                    event['operations_tasks'][0] = deepcopy(value)
                else:
                    event[key] = value
            return SimpleNamespace(matched_count=1)

    db = SimpleNamespace(mice_events=Events())
    monkeypatch.setattr(mice, 'get_system_db', lambda: db)
    monkeypatch.setattr(mice, 'task_notice', AsyncMock())

    async def locked(database, tid, kind, eid, callback):
        assert database is db and tid == 'hotel' and eid == 'event'
        return await callback(object())

    monkeypatch.setattr(mice, '_catalog_lock', locked)
    return event


@pytest.mark.asyncio
async def test_full_return_after_partial_returns_only_one_and_retry_is_idempotent(ledger):
    body = mice.OperationTaskTransitionIn(status='completed')
    first = await mice.transition_operation_task('event', 'equipment', body, USER)
    task = first['task']
    assert (task['delivered_quantity'], task['returned_quantity'], task['status']) == (2, 2, 'completed')
    assert task['handovers'][-1]['quantity'] == 1
    replay = await mice.transition_operation_task('event', 'equipment', body, USER)
    assert replay['replayed'] is True
    assert len(ledger['operations_tasks'][0]['handovers']) == 3


@pytest.mark.asyncio
async def test_full_delivery_finishes_partial_quantity_and_repeat_does_not_add_stock(ledger):
    task = ledger['operations_tasks'][0]
    task.update(delivered_quantity=1, returned_quantity=0, handovers=[{'request_id': 'partial', 'action': 'deliver', 'quantity': 1}])
    body = mice.OperationTaskTransitionIn(status='acknowledged')
    result = await mice.transition_operation_task('event', 'equipment', body, USER)
    assert result['task']['delivered_quantity'] == 2
    assert result['task']['handovers'][-1]['quantity'] == 1
    assert (await mice.transition_operation_task('event', 'equipment', body, USER))['replayed']
    assert len(ledger['operations_tasks'][0]['handovers']) == 2


@pytest.mark.asyncio
async def test_cannot_complete_return_before_any_delivery(ledger):
    ledger['operations_tasks'][0].update(status='pending', delivered_quantity=0, returned_quantity=0, handovers=[])
    with pytest.raises(HTTPException) as error:
        await mice.transition_operation_task('event', 'equipment', mice.OperationTaskTransitionIn(status='completed'), USER)
    assert error.value.status_code == 409
    assert ledger['operations_tasks'][0]['status'] == 'pending'


@pytest.mark.asyncio
async def test_existing_completed_partial_flow_is_unchanged(ledger):
    ledger['operations_tasks'][0].update(status='completed', returned_quantity=2)
    assert await mice.transition_operation_task('event', 'equipment', mice.OperationTaskTransitionIn(status='completed'), USER) == {'ok': True, 'unchanged': True}
