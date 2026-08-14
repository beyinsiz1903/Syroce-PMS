import { describe, expect, it } from 'vitest';

import { normalizeDepartureResponse } from '../DepartureList';

describe('DepartureList response contract', () => {
  it('reads the canonical front-desk departure response', () => {
    const row = { id: 'booking-1', balance: 50 };
    expect(normalizeDepartureResponse({ departures: [row] })).toEqual([row]);
  });

  it('fails closed on malformed response objects', () => {
    expect(normalizeDepartureResponse({ departures: { id: 'bad' } })).toEqual([]);
  });
});
