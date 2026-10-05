import { describe, expect, it } from 'vitest';

import {
  displayableGuestPhone,
  normalizeDepartureResponse,
  partitionDeparturesForBulkCheckout,
} from '../DepartureList';

describe('DepartureList response contract', () => {
  it('reads the canonical front-desk departure response', () => {
    const row = { id: 'booking-1', balance: 50 };
    expect(normalizeDepartureResponse({ departures: [row] })).toEqual([row]);
  });

  it('fails closed on malformed response objects', () => {
    expect(normalizeDepartureResponse({ departures: { id: 'bad' } })).toEqual([]);
  });

  it('never renders encrypted guest contact payloads as phone numbers', () => {
    expect(displayableGuestPhone('SYR1:encrypted-ciphertext')).toBe('');
    expect(displayableGuestPhone('+90 555 123 45 67')).toBe('+90 555 123 45 67');
  });

  it('keeps debt rows out of safe bulk checkout', () => {
    expect(partitionDeparturesForBulkCheckout([
      { id: 'paid', balance: 0 },
      { id: 'credit', balance: -20 },
      { id: 'debt', balance: 150 },
    ])).toEqual({
      eligible: [{ id: 'paid', balance: 0 }, { id: 'credit', balance: -20 }],
      blocked: [{ id: 'debt', balance: 150 }],
    });
  });
});
