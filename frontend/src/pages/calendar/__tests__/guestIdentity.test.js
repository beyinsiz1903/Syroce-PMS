import { describe, expect, it } from 'vitest';

import {
  deduplicateGuestSearchResults,
  guestIdentityTokens,
  maskGuestDocument,
} from '../guestIdentity';

describe('guest identity suggestions', () => {
  it('shows the strongest profile once for the same identity', () => {
    const results = deduplicateGuestSearchResults([
      { id: 'old', name: 'Salih Bey', id_number: '12345678901', total_stays: 1 },
      { id: 'canonical', name: 'salih bey', id_number: '123 456 789 01', total_stays: 5 },
      { id: 'other', name: 'Salih Bey', id_number: '99999999999' },
    ]);

    expect(results.map(guest => guest.id)).toEqual(['canonical', 'other']);
  });

  it('collapses historical name-only quick-booking duplicates in suggestions', () => {
    const results = deduplicateGuestSearchResults([
      { id: 'one', name: 'Salih Bey' },
      { id: 'two', name: ' salih  bey ', total_stays: 2 },
    ]);

    expect(results).toHaveLength(1);
    expect(results[0].id).toBe('two');
  });

  it('ignores placeholder e-mail and masks document numbers', () => {
    expect(guestIdentityTokens({ email: 'walk-in-123@placeholder.local' })).toEqual([]);
    expect(maskGuestDocument('12345678901')).toBe('******8901');
  });
});
