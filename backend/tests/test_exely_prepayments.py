"""PMSConnect DepositPayments survive import without inventing PMS receipts."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_exely_channel_identity import PRIMARY, envelope
from test_exely_reservation_lifecycle import _add_mapping, fake_db  # noqa: F401

from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.response_parser import parse_read_rs


def payment(kind="ReceivedPayment", amount="160", currency="USD", index=' PaymentIndex="0"', extra=""):
    return f'<GuaranteePayment Type="{kind}"{index}><AmountPercent Amount="{amount}" CurrencyCode="{currency}" {extra}/></GuaranteePayment>'


def xml(payments=None):
    original = envelope(PRIMARY)
    start, end = original.index(b'<DepositPayments>'), original.index(b'</DepositPayments>') + len(b'</DepositPayments>')
    replacement = f'<DepositPayments>{payments}</DepositPayments>'.encode() if payments is not None else b''
    return original[:start] + replacement + original[end:]


def parsed(payments):
    result = parse_read_rs(xml(payments))
    assert result['success'], result
    return result['reservations'][0]


def test_received_expected_loyalty_and_multiple_installments_are_distinct():
    raw = parsed(payment(amount='1') + payment(amount='99', index=' PaymentIndex="1"')
                 + payment('ExpectedPayment', '150', index='') + payment('ReceivedLoyaltyPayment', '20', index=''))
    snapshot = raw['prepayment']
    assert snapshot['scope'] == 'reservation'
    assert snapshot['totals'] == [{'currency': 'USD', 'received_amount': 100, 'expected_amount': 150, 'loyalty_amount': 20}]
    assert snapshot['remaining_amount'] == 130  # 250 - 100 - 20; expected is not paid.
    assert [p['payment_index'] for p in snapshot['payments'][:2]] == ['0', '1']


def test_amount_is_already_total_not_percent_or_number_of_nights():
    raw = parsed(payment(extra='BasisType="Nights" NmbrOfNights="2" Percent="50"'))
    assert raw['prepayment']['totals'][0]['received_amount'] == 160
    assert raw['prepayment']['booking_total'] == 250
    assert raw['prepayment']['remaining_amount'] == 90


def test_card_guarantee_without_deposit_is_not_a_received_payment_or_a_raw_hash_change():
    raw = parse_read_rs(xml())['reservations'][0]
    assert 'prepayment' not in raw
    assert normalize_reservation(raw)['prepayment'] is None


def test_empty_deposit_and_single_legacy_unindexed_payment_are_supported():
    assert parsed('')['prepayment']['remaining_amount'] == 250
    assert parsed(payment(index=''))['prepayment']['totals'][0]['received_amount'] == 160


def test_foreign_currency_is_preserved_without_guessing_an_exchange_rate():
    snapshot = parsed(payment(currency='EUR'))['prepayment']
    assert snapshot['totals'][0]['currency'] == 'EUR'
    assert snapshot['remaining_amount'] is None
    assert snapshot['overpayment_amount'] is None


def test_overpayment_is_visible_without_a_negative_due():
    snapshot = parsed(payment(amount='300'))['prepayment']
    assert snapshot['remaining_amount'] == 0
    assert snapshot['overpayment_amount'] == 50


def test_decimal_installments_are_summed_before_float_serialization():
    snapshot = parsed(payment(amount='0.1') + payment(amount='0.2', index=' PaymentIndex="1"'))['prepayment']
    assert snapshot['totals'][0]['received_amount'] == 0.3
    assert snapshot['remaining_amount'] == 249.7


def test_one_bad_reservation_blocks_the_entire_read_batch():
    valid = xml(payment())
    invalid = xml(payment(amount='NaN'))
    element = invalid[invalid.index(b'<HotelReservation '):invalid.index(b'</HotelReservation>') + len(b'</HotelReservation>')]
    result = parse_read_rs(valid.replace(b'</ReservationsList>', element + b'</ReservationsList>'))
    assert result['success'] is False
    assert result['reservations'] == []


def test_allowlist_discards_card_details_and_payment_transaction_secrets():
    value = payment().replace('</GuaranteePayment>', '<PaymentTransactionID>secret-reference</PaymentTransactionID><PaymentCard CardNumber="do-not-copy"/></GuaranteePayment>')
    raw = parsed(value)
    assert 'secret-reference' not in str(raw)
    assert 'do-not-copy' not in str(raw)


@pytest.mark.parametrize('payments', [
    payment(amount='NaN'), payment(amount='Infinity'), payment(amount='-1'), payment(amount=''),
    payment(amount='1000000000001'), payment(currency=''), payment(currency='US'),
    payment('UnexpectedPayment'), payment(index=' PaymentIndex="-1"'),
    payment() + payment(), payment(index='') + payment(index=''),
    '<GuaranteePayment Type="ReceivedPayment"/>',
])
def test_malformed_payment_blocks_the_whole_read_without_leaking_money_details(payments):
    result = parse_read_rs(xml(payments))
    assert result['success'] is False
    assert result['result_class'] == 'MALFORMED'
    assert result['reservations'] == []
    assert 'PaymentIndex' not in str(result)


@pytest.mark.asyncio
async def test_snapshot_replaces_prior_version_and_ack_requires_durable_payment_readback(fake_db):  # noqa: F811
    await _add_mapping(fake_db)
    item = normalize_reservation({**parsed(payment('ExpectedPayment', '160', index='')), 'property_id': 'property'})
    await lifecycle.persist_exely_event('tenant', item, 'reservation', 'event-one', 'hash-one')
    current = fake_db.exely_reservations.documents[0]
    assert (await pms_lifecycle.process_reservation_version('tenant', current))['success']
    booking = fake_db.bookings.documents[0]
    assert booking['provider_prepayment']['remaining_amount'] == 250
    booking['paid_amount'] = 25  # Independent money previously collected in the PMS.
    item = normalize_reservation({**parsed(payment(amount='1') + payment(amount='99', index=' PaymentIndex="1"')), 'property_id': 'property'})
    item['provider_last_modified_at'] = '2030-10-01T13:00:00'
    await lifecycle.persist_exely_event('tenant', item, 'modification', 'event-two', 'hash-two')
    current = fake_db.exely_reservations.documents[0]
    assert (await pms_lifecycle.process_reservation_version('tenant', current))['success']
    snapshot = booking['provider_prepayment']
    assert snapshot['totals'][0]['received_amount'] == 100
    assert snapshot['totals'][0]['expected_amount'] == 0
    assert snapshot['remaining_amount'] == 150
    assert booking['total_amount'] == 220
    assert booking['paid_amount'] == 25
    assert (await pms_lifecycle.process_reservation_version('tenant', current))['success']
    assert len(fake_db.bookings.documents) == 1
    assert (await lifecycle.persist_exely_event('tenant', item, 'modification', 'repeat', 'hash-two'))['reason'] == 'duplicate_payload'
    version = fake_db.exely_reservation_versions.documents[-1]
    assert version['prepayment'] == snapshot == current['prepayment']
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    saved = deepcopy(snapshot)
    booking['provider_prepayment'] = None
    assert not await lifecycle._durable_readback(version)
    assert not (await pms_lifecycle.process_reservation_version('tenant', current))['success']
    assert (await lifecycle.acknowledge_durable_version(provider, current))['provider_write_count'] == 0
    provider.confirm_delivery.assert_not_awaited()
    booking['provider_prepayment'] = saved
    assert await lifecycle._durable_readback(version)
    # Failed readback puts the delivery back into the normal repair lifecycle.
    assert (await pms_lifecycle.process_reservation_version('tenant', current))['success']
    assert (await lifecycle.acknowledge_durable_version(provider, current))['provider_write_count'] == 1
    assert (await lifecycle.acknowledge_durable_version(provider, current))['provider_write_count'] == 0


@pytest.mark.asyncio
async def test_group_payment_is_not_allocated_or_duplicated_as_room_receipts(fake_db):  # noqa: F811
    await _add_mapping(fake_db)
    item = normalize_reservation({**parsed(payment()), 'property_id': 'property'})
    second = deepcopy(item['rooms'][0])
    second['index_number'] = '2'
    item['rooms'].append(second)
    item['total_rooms'] = 2
    await lifecycle.persist_exely_event('tenant', item, 'reservation', 'group-event', 'group-hash')
    assert (await pms_lifecycle.process_reservation_version('tenant', fake_db.exely_reservations.documents[0]))['success']
    assert len(fake_db.bookings.documents) == 2
    assert sum(b['paid_amount'] for b in fake_db.bookings.documents) == 0
    for booking in fake_db.bookings.documents:
        assert booking['provider_prepayment']['scope'] == 'reservation'
        assert booking['provider_prepayment']['totals'][0]['received_amount'] == 160
        assert booking['provider_group_reservation_id'] == 'exely-group'
