import asyncio
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from shared_kernel.gl_periods import calendar_periods, ensure_calendar_year_periods
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_concurrent_lazy_period_initializers_keep_exactly_one_calendar(ledger_db):  # noqa: F811
    await asyncio.gather(*(ensure_calendar_year_periods(ledger_db, 't', 2026) for _ in range(8)))
    assert await ledger_db.gl_periods.count_documents({'tenant_id': 't'}) == 12
    await ledger_db.gl_periods.update_one({'period_no': 11}, {'$set': {'status': 'closed'}})
    await ensure_calendar_year_periods(ledger_db, 't', 2026)
    assert (await ledger_db.gl_periods.find_one({'period_no': 11}))['status'] == 'closed'


async def test_duplicate_error_needs_matching_tenant_period_and_never_overwrites_closed_status():
    from types import SimpleNamespace
    expected = {**calendar_periods('t', 2026)[0], 'status': 'closed'}
    collection = SimpleNamespace(update_one=AsyncMock(side_effect=DuplicateKeyError('race')), find_one=AsyncMock(return_value=expected))
    db = SimpleNamespace(gl_periods=collection)
    # First exact period is accepted; second period cannot match January.
    with pytest.raises(DuplicateKeyError):
        await ensure_calendar_year_periods(db, 't', 2026)
    assert collection.update_one.await_count == 2
    assert expected['status'] == 'closed'
