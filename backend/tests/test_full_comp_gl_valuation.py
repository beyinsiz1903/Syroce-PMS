from copy import deepcopy

import pytest

from core.integrations import operational_gl_valuation as v
from tests.test_operational_gl_source_valuation import DAY, MAPPING, RATES

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)


def source(**changes):
    return {'id': 'comp', 'tenant_id': 't', 'currency': 'TRY', 'business_date': DAY,
            'total': 0, 'vat_amount': 0, 'tax_amount': 0, 'is_complimentary': True,
            'complimentary_scope': 'full', 'complimentary_original_amount': 150,
            'complimentary_original_tax_snapshot': {'net_amount': 125, 'vat_amount': 25,
                                                   'tax_amount': 0, 'currency': 'TRY'}, **changes}


def plan(row, mapping=None):
    return v.build_plan([row], [], mapping or {**MAPPING, 'adjustment_account_code': '611'},
                        v.normalized_valuation(DAY, RATES))


def test_full_comp_retains_proven_net_gross_discount_without_tax_cash_or_receivable():
    row = source()
    before = deepcopy(row)
    result = plan(row)
    assert row == before
    effects = {line['account_code']: (line.get('debit', 0), line.get('credit', 0)) for line in result['lines']}
    assert effects == {'600': (0, 125), '611': (125, 0)}
    assert result['charge_total_try'] == result['payment_total_try'] == 0
    assert result['manifest']['sources'][0]['complimentary_original_net_minor'] == 12500


@pytest.mark.parametrize('snapshot', [None, {}, {'net_amount': 150, 'vat_amount': 25, 'tax_amount': 0},
    {'net_amount': 125, 'vat_amount': 25, 'tax_amount': 0, 'currency': 'EUR'}])
def test_unknown_or_inconsistent_original_comp_basis_never_becomes_zero(snapshot):
    with pytest.raises(v.OperationalValuationError, match='original'):
        plan(source(complimentary_original_tax_snapshot=snapshot))


def test_full_comp_requires_distinct_adjustment_account():
    with pytest.raises(v.OperationalValuationError):
        plan(source(), {**MAPPING, 'adjustment_account_code': '600'})


@pytest.mark.asyncio
async def test_daily_sources_keeps_zero_comp_and_deduplicates_manual_extra_mirror(ledger_db):
    row = source(source_extra_charge_id='extra')
    await ledger_db.folio_charges.insert_one(deepcopy(row))
    await ledger_db.extra_charges.insert_one(source(id='extra', amount=0))
    charges, payments, security = await v.daily_sources(ledger_db, 't', DAY)
    assert [charge['id'] for charge in charges] == ['comp']
    assert payments == security == []


def test_free_zero_list_price_is_not_a_concession_and_foreign_net_uses_explicit_day_rate():
    free = source(complimentary_original_amount=0)
    assert not v.is_full_comp_source(free)
    foreign = source(currency='EUR', complimentary_original_tax_snapshot={
        'net_amount': 125, 'vat_amount': 25, 'tax_amount': 0, 'currency': 'EUR'})
    assert {line.get('debit', 0) or line.get('credit', 0) for line in plan(foreign)['lines']} == {6875}


@pytest.mark.asyncio
async def test_full_comp_correction_is_append_only_replay_safe_and_snapshot_bound(ledger_db):
    from shared_kernel.gl_posting import verify_journal_entry_hash
    from tests.test_operational_gl_source_valuation import seed

    old = await seed(ledger_db)
    await ledger_db.gl_accounts.insert_one({'tenant_id': 'hotel', 'code': '611', 'active': True})
    await ledger_db.gl_operational_mappings.update_one({'tenant_id': 'hotel'}, {'$set': {'adjustment_account_code': '611'}})
    row = source(tenant_id='hotel')
    await ledger_db.folio_charges.insert_one(deepcopy(row))
    preview = await v.preview_daily_valuation(ledger_db, 'hotel', 'run', RATES)
    result = await v.post_daily_valuation(ledger_db, 'hotel', 'run', RATES, preview['preview_hash'], 'finance')
    replay = await v.post_daily_valuation(ledger_db, 'hotel', 'run', RATES, preview['preview_hash'], 'finance')
    assert result['entry_id'] == replay['entry_id']
    entry = await ledger_db.gl_journal_entries.find_one({'id': result['entry_id']}, {'_id': 0})
    assert verify_journal_entry_hash(entry)
    assert await ledger_db.gl_journal_entries.find_one({'id': old['id']}, {'_id': 0}) == old
    assert await ledger_db.folio_charges.find_one({'id': 'comp'}, {'_id': 0}) == row
    assert await ledger_db.gl_journal_entries.count_documents({'source': 'night_audit_correction'}) == 1
