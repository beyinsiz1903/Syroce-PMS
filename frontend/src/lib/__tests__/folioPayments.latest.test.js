import { describe, expect, it } from 'vitest';
import { latestCollectionPayment } from '@/lib/folioPayments';

const cash = Object.freeze({ id: 'receipt', method: 'cash', amount: 1000, processed_at: '2026-10-24T16:42:00Z' });
describe('latestCollectionPayment — presentation only', () => {
  it.each(['discount', 'complimentary', 'correction', 'city_ledger', 'direct_bill', 'ar', 'security_deposit_application', 'gift_card_redemption', 'wallet', 'loyalty_redemption', 'barter', 'write_off'])(
    'does not select %s as a collection method', method => {
      const adjustment = { method, amount: 7200, processed_at: '2026-10-24T20:49:00Z' };
      expect(latestCollectionPayment([cash, adjustment])).toBe(cash);
      expect(latestCollectionPayment([adjustment])).toBeNull();
    },
  );
  it.each(['void', 'voided', 'failed', 'cancelled', 'canceled', 'rejected', 'pending', 'processing', 'initiated', 'authorized', 'expired', 'declined', 'requires_action'])(
    'ignores a %s receipt', status => {
      expect(latestCollectionPayment([cash, { method: 'card', amount: 50, status }])).toBe(cash);
    },
  );
  it('ignores cancelled rows, refunds, negative/zero/malformed amounts, missing methods and null rows', () => {
    expect(latestCollectionPayment([cash,
      { method: 'card', amount: 500, voided: true },
      { method: 'bank_transfer', amount: 100, payment_type: 'refund' },
      { method: 'card', amount: -100 }, { method: 'cash', amount: 0 },
      { method: 'cash', amount: 'invalid' }, { amount: 100 }, null,
    ])).toBe(cash);
  });
  it('selects the latest transaction timestamp, preserves source order and supports payment_method alias', () => {
    const earlier = Object.freeze({ method: 'bank_transfer', amount: 4800, created_at: '2026-10-24T16:33:00Z' });
    const latest = Object.freeze({ payment_method: 'CARD', amount: 50, paid_at: '2026-10-24T17:00:00Z' });
    const source = Object.freeze([latest, cash, earlier]);
    expect(latestCollectionPayment(source)).toBe(latest);
    expect(source).toEqual([latest, cash, earlier]);
  });
  it('retains response order for legacy rows without timestamps', () => {
    const card = { method: 'card', amount: 50 };
    expect(latestCollectionPayment([{ method: 'cash', amount: 20 }, card])).toBe(card);
  });
  it('does not invent a receipt when payment data is missing', () => {
    expect(latestCollectionPayment()).toBeNull();
    expect(latestCollectionPayment([])).toBeNull();
    expect(latestCollectionPayment({})).toBeNull();
  });
});
