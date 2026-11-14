import { describe, expect, it } from 'vitest';
import { reservationDisplaySummary, reservationPaymentSummary } from '../paymentSummary';

describe('reservationPaymentSummary — server amounts, presentation only', () => {
  it('separates whole-stay debt from posted folio debt', () => {
    const source = Object.freeze({
      reservation_total_due: 8200, balance: 3400, folio_balance: 3400,
      unposted_room_amount: 4800, total_payments: 5800, prepayment_total: 4800,
    });
    expect(reservationPaymentSummary(source)).toMatchObject({
      kind: 'due', label: 'Toplam kalan ödeme', totalDue: 8200, displayAmount: 8200,
      folioBalance: 3400, pendingRoomAmount: 4800, hasAllocatedPrepayment: false,
    });
  });

  it('prefers explicit folio_balance for migrated reservations', () => {
    expect(reservationPaymentSummary({ reservation_total_due: 8200, balance: 8200, folio_balance: 3400 }))
      .toMatchObject({ totalDue: 8200, folioBalance: 3400 });
  });

  it('supports a legacy response with only balance and does not invent pending charges', () => {
    expect(reservationPaymentSummary({ balance: '350.25' }))
      .toMatchObject({ kind: 'due', totalDue: 350.25, folioBalance: 350.25, pendingRoomAmount: null });
  });

  it.each([undefined, null, '', ' ', false, true, 'invalid', NaN, Infinity, [], [0], {}])('does not turn an unavailable or invalid amount (%s) into a paid zero', value => {
    expect(reservationPaymentSummary({ reservation_total_due: value, balance: value }))
      .toMatchObject({ kind: 'unknown', displayAmount: null, label: 'Ödeme bilgisi alınamadı' });
  });

  it('does not replace a malformed explicit total with another amount', () => {
    expect(reservationPaymentSummary({ reservation_total_due: 'invalid', balance: 3400 }))
      .toMatchObject({ kind: 'unknown', totalDue: null, folioBalance: 3400 });
  });

  it.each([0, '0', 0.01, -0.01])('preserves zero and existing one-cent settlement tolerance (%s)', value => {
    expect(reservationPaymentSummary({ reservation_total_due: value })).toMatchObject({ kind: 'settled' });
  });

  it('does not treat advance payment allocated to pending room nights as a guest refund', () => {
    expect(reservationPaymentSummary({ reservation_total_due: 0, folio_balance: -4800, unposted_room_amount: 4800 }))
      .toMatchObject({ kind: 'settled', displayAmount: 0, hasAllocatedPrepayment: true });
  });

  it('shows a genuine whole-stay credit as a positive guest receivable', () => {
    expect(reservationPaymentSummary({ reservation_total_due: -200, balance: -200 }))
      .toMatchObject({ kind: 'credit', label: 'Misafir alacağı', displayAmount: 200 });
  });

  it('never presents a pricing discrepancy as collected or payable guest debt', () => {
    expect(reservationPaymentSummary({
      reservation_total_due: 15.03, balance: 15.03,
      pricing_reconciliation_required: true, pricing_reconciliation_difference: 15.03,
    })).toMatchObject({ kind: 'reconciliation', label: 'Fiyat / tahakkuk farkı', displayAmount: 15.03 });
  });
});

describe('Exely reservation and local ledger scopes', () => {
  const booking = { channel: 'exely', currency: 'USD', provider_prepayment: {
    schema_version: 1, scope: 'reservation', booking_currency: 'USD', booking_total: 460,
    remaining_amount: 300, totals: [{ currency: 'USD', received_amount: 160 }],
  } };
  const summary = Object.freeze({ reservation_total_due: 160, gross_total: 160, cash_collection_total: 0 });

  it('uses the services-inclusive provider balance for the headline without changing PMS amounts', () => {
    expect(reservationDisplaySummary(summary, booking)).toMatchObject({
      label: 'Exely’de kalan tutar', displayAmount: 300, currency: 'USD', providerScope: true, kind: 'due',
    });
    expect(reservationPaymentSummary(summary, booking)).toMatchObject({
      label: 'PMS kayıt bakiyesi', totalDue: 160, pmsOnly: true,
    });
    expect(summary.cash_collection_total).toBe(0);
  });

  it('does not add local extras or multiply a shared provider balance across rooms', () => {
    for (const room of ['standard', 'deluxe']) {
      expect(reservationDisplaySummary({ ...summary, reservation_total_due: 210 }, { ...booking, id: room }).displayAmount).toBe(300);
    }
  });

  it('keeps the source currency when it differs from the folio currency', () => {
    expect(reservationDisplaySummary(summary, { ...booking, currency: 'TRY' })).toMatchObject({ displayAmount: 300, currency: 'USD' });
  });

  it.each([null, undefined, '', 'invalid', -1, Infinity])('does not substitute a local balance for an unknown source balance (%s)', remaining_amount => {
    expect(reservationDisplaySummary(summary, { ...booking, provider_prepayment: { ...booking.provider_prepayment, remaining_amount } }))
      .toMatchObject({ kind: 'unknown', displayAmount: null });
  });

  it('does not treat a missing snapshot or a card guarantee as a settled payment', () => {
    expect(reservationDisplaySummary(summary, { channel: 'exely', payment_method: 'BankCardGuarantee' }))
      .toMatchObject({ kind: 'unknown', displayAmount: null });
  });

  it('preserves a fully prepaid provider balance even while the local folio is not settled', () => {
    expect(reservationDisplaySummary(summary, { ...booking, provider_prepayment: { ...booking.provider_prepayment, remaining_amount: 0 } }))
      .toMatchObject({ kind: 'settled', displayAmount: 0 });
    expect(reservationPaymentSummary(summary, booking).totalDue).toBe(160);
  });

  it('keeps a PMS price discrepancy visible instead of hiding it behind the source payment', () => {
    expect(reservationDisplaySummary({ ...summary, pricing_reconciliation_required: true, pricing_reconciliation_difference: 20 }, booking))
      .toMatchObject({ kind: 'reconciliation', displayAmount: 20 });
  });

  it('preserves the normal overview for direct bookings', () => {
    expect(reservationDisplaySummary(summary, { channel: 'direct' })).toEqual(reservationPaymentSummary(summary));
  });
});
