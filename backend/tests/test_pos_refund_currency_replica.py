"""Source-currency evidence for old/new POS refunds, never current defaults."""
import pytest

from domains.pms.pos_fnb.daily_closure import preview, summarize
from tests.test_pos_final_consistency_replica import ctx, db, paid, service  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize('native', ['TRY', 'USD', 'EUR'])
async def test_new_refund_seals_original_currency_even_after_property_change(db, service, native):
    await paid(db)
    await db.pos_transactions.update_one({'id': 'sale-paid'}, {'$set': {'currency': native}})
    await db.hotel_settings.update_one({'tenant_id': 't'}, {'$set': {'currency': 'GBP'}})
    result = await service.refund_order(ctx(), 'paid', 55, 'Misafir iadesi', 'same-refund')
    assert result.ok
    row = await db.pos_transactions.find_one({'id': result.data['refund_id']})
    assert row['currency'] == native and row['original_transaction_id'] == 'sale-paid'
    assert (await service.refund_order(ctx(), 'paid', 55, 'Misafir iadesi', 'same-refund')).data['idempotent']
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('property_currency', ['TRY', None])
async def test_later_day_legacy_refund_inherits_source_currency_read_only(db, property_currency):
    await paid(db)
    await db.hotel_settings.update_one({'tenant_id': 't'}, {'$set': {'currency': property_currency}})
    original = {'id': 'legacy', 'tenant_id': 't', 'original_transaction_id': 'sale-paid', 'order_id': 'paid',
        'status': 'refunded', 'payment_type': 'refund', 'payment_method': 'cash', 'total_amount': -55,
        'transaction_date': '2026-10-19'}
    await db.pos_transactions.insert_one(dict(original))
    result = await preview(db, 't', '2026-10-19')
    assert result['currency'] == 'EUR' and result['net_sales'] == -55 and result['refund_total'] == 55
    assert set(result['totals_by_currency']) == {'EUR'} and result['transaction_count'] == 1
    assert await db.pos_transactions.find_one({'id': 'legacy'}, {'_id': 0}) == original


@pytest.mark.asyncio
async def test_source_currency_conflict_is_not_overwritten_or_sealed(db):
    await paid(db)
    await db.pos_transactions.insert_one({'id': 'conflict', 'tenant_id': 't', 'original_transaction_id': 'sale-paid',
        'order_id': 'paid', 'currency': 'USD', 'payment_method': 'cash', 'status': 'refunded', 'payment_type': 'refund',
        'total_amount': -55, 'transaction_date': '2026-10-19'})
    with pytest.raises(ValueError, match='UNVERIFIED_POS_REFUND_SOURCE'):
        await preview(db, 't', '2026-10-19')
    assert (await db.pos_transactions.find_one({'id': 'conflict'}))['currency'] == 'USD'


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['other-tenant', 'wrong-id', 'wrong-order'])
async def test_missing_or_inconsistent_source_never_uses_property_default(db, source):
    await paid(db)
    if source == 'other-tenant':
        await db.pos_transactions.update_one({'id': 'sale-paid'}, {'$set': {'tenant_id': 'private'}})
    row = {'id': 'unverified', 'tenant_id': 't', 'order_id': 'different' if source == 'wrong-order' else 'paid',
        'original_transaction_id': 'wrong' if source == 'wrong-id' else 'sale-paid',
        'status': 'refunded', 'payment_type': 'refund', 'payment_method': 'cash', 'total_amount': -55,
        'tax_amount': -5, 'tip_amount': 0, 'category_amounts': {'drinks': -50}, 'transaction_date': '2026-10-19'}
    await db.pos_transactions.insert_one(dict(row))
    with pytest.raises(ValueError, match='MISSING_POS_CURRENCY'):
        await preview(db, 't', '2026-10-19')
    assert 'currency' not in await db.pos_transactions.find_one({'id': 'unverified'})


def test_refund_without_currency_cannot_assume_hotel_base_currency():
    row = {'id': 'legacy', 'status': 'refunded', 'payment_type': 'refund', 'total_amount': -10, 'payment_method': 'cash'}
    with pytest.raises(ValueError, match='MISSING_POS_CURRENCY'):
        summarize([row], default_currency='TRY')
    result = summarize([{**row, 'source_sale': {'currency': 'EUR'}}], default_currency='TRY')
    assert result['currency'] == 'EUR' and result['net_sales'] == -10
