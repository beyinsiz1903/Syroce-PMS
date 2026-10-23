from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from modules.pms_core.folio_selection import ensure_folio_transfer_amount, select_booking_folio


@pytest.mark.asyncio
async def test_ambiguous_target_cannot_silently_choose_first():
    database = SimpleNamespace(folios=SimpleNamespace(find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[{'id': 'a'}, {'id': 'b'}])))))
    with pytest.raises(HTTPException) as exc:
        await select_booking_folio(database, 't', 'b')
    assert exc.value.status_code == 409
    assert database.folios.find.call_args.args[0] == {'tenant_id': 't', 'booking_id': 'b', 'status': 'open'}


@pytest.mark.asyncio
@pytest.mark.parametrize('folio,code', [(None, 404), ({'id': 'f', 'status': 'closed'}, 409)])
async def test_foreign_or_closed_folio_rejected(folio, code):
    collection = SimpleNamespace(find_one=AsyncMock(return_value=folio))
    with pytest.raises(HTTPException) as exc:
        await select_booking_folio(SimpleNamespace(folios=collection), 't', 'b', 'f', session='session')
    assert exc.value.status_code == code
    collection.find_one.assert_awaited_once_with({'tenant_id': 't', 'booking_id': 'b', 'id': 'f'}, {'_id': 0}, session='session')


@pytest.mark.asyncio
async def test_explicit_target_returned_without_first_folio_fallback():
    folio = {'id': 'second', 'status': 'open'}
    db = SimpleNamespace(folios=SimpleNamespace(find_one=AsyncMock(return_value=folio)))
    assert await select_booking_folio(db, 't', 'b', 'second') == folio


@pytest.mark.asyncio
async def test_transfer_cannot_take_debt_from_another_window(monkeypatch):
    from modules.pms_core import receivable_reporting
    read = AsyncMock(return_value={'f': {'currency': 'TRY', 'balance_by_currency': {'TRY': 6000}}})
    monkeypatch.setattr(receivable_reporting, 'folio_snapshots', read)
    await ensure_folio_transfer_amount('db', 't', {'id': 'f'}, 6000, 'TRY', session='session')
    with pytest.raises(HTTPException):
        await ensure_folio_transfer_amount('db', 't', {'id': 'f'}, 10000, 'TRY', session='session')
    assert read.call_args.kwargs['session'] == 'session'
