import { describe, expect, it } from 'vitest';

import { bookingSourceLabel } from '../bookingSource';

describe('bookingSourceLabel', () => {
  it.each([
    ['agodaycs5', 'Agoda'],
    ['booking_com_ycs5', 'Booking.com'],
    ['Expedia-Collect', 'Expedia'],
    ['tatilbudurapi', 'Tatilbudur'],
    ['etsapi', 'Etstur'],
    ['hotels.com', 'Hotels.com'],
  ])('turns technical agency code %s into %s', (channel, label) => {
    expect(bookingSourceLabel({ channel })).toBe(label);
  });

  it('prefers the configured agency name for agency reservations', () => {
    expect(bookingSourceLabel({ channel: 'agency', agency_id: 'a1', agency_name: 'Atlas Turizm' }))
      .toBe('Acente · Atlas Turizm');
  });

  it('keeps an unknown meaningful source instead of inventing a brand', () => {
    expect(bookingSourceLabel({ source_channel: 'Yerel Partner' })).toBe('Yerel Partner');
  });

  it('shows the actual channel as well as Exely provenance without changing the raw provider', () => {
    expect(bookingSourceLabel({ booking_source: 'exely', ota_channel: 'exely', provider_channel_name: 'Liberty Channel' }))
      .toBe('Liberty Channel · Exely');
  });
});
