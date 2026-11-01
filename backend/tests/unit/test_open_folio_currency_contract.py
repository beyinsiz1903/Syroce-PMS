"""New folio currencies follow their reservation, never the report currency."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.schemas import FolioCreate
from modules.folio.services import open_folio_service as module


@pytest.mark.asyncio
@pytest.mark.parametrize('booking_currency,tenant_currency,expected', [
    ('EUR', 'TRY', 'EUR'), ('usd', 'TRY', 'USD'), (None, 'EUR', 'EUR'),
])
async def test_open_folio_preserves_currency_in_ledger_event_and_response(monkeypatch, booking_currency, tenant_currency, expected):
    repository = SimpleNamespace(**{name: AsyncMock() for name in (
        'acquire_idempotency_lock', 'get_booking_for_tenant', 'get_guest_for_tenant',
        'get_open_folio_for_booking', 'insert_folio', 'insert_outbox_event',
        'complete_idempotency_lock', 'fail_idempotency_lock',
    )})
    repository.acquire_idempotency_lock.return_value = {'status': 'acquired', 'lock_id': 'local-lock'}
    repository.get_booking_for_tenant.return_value = {'id': 'local-booking', 'guest_id': 'local-guest', 'currency': booking_currency}
    repository.get_guest_for_tenant.return_value = {'id': 'local-guest'}
    repository.get_open_folio_for_booking.return_value = None
    monkeypatch.setattr(module, 'load_tenant_doc', AsyncMock(return_value={'currency': tenant_currency}))
    monkeypatch.setattr(module, 'generate_folio_number', AsyncMock(return_value='F-LOCAL'))
    monkeypatch.setattr(module, 'audit_log', AsyncMock())
    result = await module.OpenFolioService(repository).create(
        FolioCreate(booking_id='local-booking', folio_type='guest'),
        SimpleNamespace(id='local-actor', tenant_id='local-tenant', role='front_desk'),
        SimpleNamespace(headers={'Idempotency-Key': 'local-only-folio'}),
    )
    assert repository.insert_folio.call_args.args[0]['currency'] == expected
    assert repository.insert_outbox_event.call_args.args[0]['payload']['currency'] == expected
    assert result['currency'] == expected
    assert repository.complete_idempotency_lock.call_args.args[2]['currency'] == expected
    repository.fail_idempotency_lock.assert_not_called()
