"""Reproduce the production index set, not only the POS index in isolation."""
from copy import deepcopy

import pytest
from pymongo.errors import DuplicateKeyError

from core import night_audit_hardened, pos_folio_consumer
from core.outbox_service import POS_CHARGE_POSTED
from domains.pms.pos_fnb.folio_lines import checkout_lines
from tests.test_pos_final_consistency_replica import db  # noqa: F401

DAY = '2026-10-25'
KEYS = [('tenant_id', 1), ('booking_id', 1), ('business_date', 1), ('charge_type', 1)]


def event(order_id='new'):
    sale = {'amount': 297, 'tax_amount': 27, 'order_items': [
        {'item_name': 'Türk Kahvesi', 'category': 'beverage', 'quantity': 1, 'total': 90, 'tax_rate': .1},
        {'item_name': 'Cheesecake', 'category': 'dessert', 'quantity': 1, 'total': 180, 'tax_rate': .1},
    ]}
    charges = [{**line, 'id': f'{order_id}-{i}', 'tenant_id': 't', 'folio_id': 'f', 'booking_id': 'b',
                'currency': 'TRY', 'charge_type': 'pos_fnb', 'business_date': DAY, 'voided': False,
                'source_pos_order_id': order_id} for i, line in enumerate(checkout_lines(sale))]
    return {'id': 'event-' + order_id, 'tenant_id': 't', 'event_type': POS_CHARGE_POSTED,
            'payload': {'folio_id': 'f', 'booking_id': 'b', 'source_pos_order_id': order_id, 'charges': charges}}


async def seed(db, monkeypatch):
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': DAY}})
    await db.folios.insert_one({'tenant_id': 't', 'id': 'f', 'booking_id': 'b', 'status': 'open', 'currency': 'TRY', 'balance': 11})
    await db.folio_charges.create_index(KEYS, name='idx_folio_charges_na_dedup', unique=True,
        partialFilterExpression={'business_date': {'$exists': True}, 'charge_type': {'$exists': True}, 'voided': False})
    await db.folio_charges.insert_one({'tenant_id': 't', 'id': 'old-charge', 'booking_id': 'b', 'folio_id': 'f',
        'business_date': DAY, 'charge_type': 'pos_fnb', 'voided': False, 'total': 11,
        'source_pos_order_id': 'old', 'line_no': 0})
    monkeypatch.setattr(pos_folio_consumer, 'get_system_db', lambda: db)
    monkeypatch.setattr(night_audit_hardened, 'db', db)


async def test_unrelated_unique_conflict_cannot_be_marked_delivered_and_upgrade_preserves_guards(db, monkeypatch):
    await seed(db, monkeypatch)
    posted = event()
    # Exactly the observed production failure: an older check already exists.
    ok, message = await pos_folio_consumer.handle_ic_pos_event(deepcopy(posted))
    assert not ok and message.startswith('retryable:')
    assert await db.folio_charges.count_documents({'source_pos_order_id': 'new'}) == 0
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 11

    await night_audit_hardened.ensure_night_audit_indexes()
    indexes = await db.folio_charges.index_information()
    assert 'idx_folio_charges_na_dedup' not in indexes
    assert indexes['idx_folio_charges_na_active_v2']['partialFilterExpression']['charge_type'] == {'$in': ['room_charge', 'no_show_fee']}
    for _ in range(2):
        assert (await pos_folio_consumer.handle_ic_pos_event(deepcopy(posted)))[0]
    assert await db.folio_charges.count_documents({'source_pos_order_id': 'new'}) == 2
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 308
    # Another check for the same booking, same day must also post in full.
    assert (await pos_folio_consumer.handle_ic_pos_event(event('another')))[0]
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 605

    # POS's own immutable source-line guard still rejects duplicates.
    with pytest.raises(DuplicateKeyError):
        await db.folio_charges.insert_one(dict(posted['payload']['charges'][0]))
    # Room/no-show concurrency guards remain active; voided corrections do not block replacements.
    for kind in ('room_charge', 'no_show_fee'):
        doc = {'tenant_id': 't', 'booking_id': 'b', 'folio_id': 'f', 'business_date': DAY, 'charge_type': kind, 'voided': False, 'total': 100}
        await db.folio_charges.insert_one(dict(doc))
        with pytest.raises(DuplicateKeyError):
            await db.folio_charges.insert_one(dict(doc))
        await db.folio_charges.update_one({'tenant_id': 't', 'charge_type': kind}, {'$set': {'voided': True}})
        await db.folio_charges.insert_one(dict(doc))


async def test_same_source_with_different_amount_is_not_a_safe_replay(db, monkeypatch):
    await seed(db, monkeypatch)
    await night_audit_hardened.ensure_night_audit_indexes()
    original = event()
    assert (await pos_folio_consumer.handle_ic_pos_event(deepcopy(original)))[0]
    changed = deepcopy(original)
    changed['payload']['charges'][0]['amount'] = 91
    changed['payload']['charges'][0]['total'] = 100
    ok, message = await pos_folio_consumer.handle_ic_pos_event(changed)
    assert not ok and message.startswith('permanent:')
    stored = await db.folio_charges.find_one({'tenant_id': 't', 'source_pos_order_id': 'new', 'line_no': 0})
    assert stored['amount'] == 90 and stored['total'] == 99
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 308
