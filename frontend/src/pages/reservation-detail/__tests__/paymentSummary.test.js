import { describe, expect, it } from 'vitest';
import { reservationPaymentSummary } from '../paymentSummary';

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
