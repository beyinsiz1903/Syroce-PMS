import { describe, expect, it } from 'vitest';

import { buildRateUpdateReview, countTargetNights } from '@/pages/rate-manager/updateReview';

describe('rate update review', () => {
  it.each(['min_stay', 'min_los_arrival', 'max_stay'])('reviews %s removal explicitly for Exely', (field) => {
    const input = { dateFrom: '2030-01-01', dateTo: '2030-01-01', allDays: true,
      selections: { STD: new Set(['BAR']) }, enabledFields: new Set([field]), roomValues: { STD: { [field]: '0' } }, channelProvider: 'exely' };
    const review = buildRateUpdateReview(input);
    expect(review.errors).toEqual([]);
    expect(review.warnings.join(' ')).toContain('kısıtı kaldırılacak');
    expect(buildRateUpdateReview({ ...input, channelProvider: 'hotelrunner' }).errors.length).toBeGreaterThan(0);
    expect(buildRateUpdateReview({ ...input, agenciesOnly: true }).errors.length).toBeGreaterThan(0);
    expect(buildRateUpdateReview({ ...input, roomValues: { STD: { [field]: '' } } }).errors.length).toBeGreaterThan(0);
  });

  it('does not treat clearing max LOS as shorter than the retained minimum', () => {
    const review = buildRateUpdateReview({ dateFrom: '2030-01-01', dateTo: '2030-01-01', allDays: true,
      selections: { STD: new Set(['BAR']) }, enabledFields: new Set(['min_stay', 'max_stay']), roomValues: { STD: { min_stay: '3', max_stay: '0' } }, channelProvider: 'exely' });
    expect(review.errors).toEqual([]);
  });
  it('does not describe Exely broadcast as a PMS-only update when OTA selection is unavailable', () => {
    const review = buildRateUpdateReview({ channelProvider: 'exely', selectedChannelCodes: new Set() });
    expect(review.warnings.join(' ')).toContain('Gönderim hedefi Exely kanal yöneticisidir');
    expect(review.warnings.join(' ')).not.toContain('yalnızca PMS');
    expect(review.warnings.join(' ')).toContain('teslim sonucu ayrıca doğrulanmalıdır');
  });

  it('keeps the agency-only exclusion explicit even with a connected Exely provider', () => {
    const review = buildRateUpdateReview({ channelProvider: 'exely', agenciesOnly: true });
    expect(review.warnings.join(' ')).toContain('kanal yöneticisine ve otel takvimine gönderilmez');
    expect(review.warnings.join(' ')).not.toContain('Gönderim hedefi Exely');
  });
  it('counts only selected weekdays in the inclusive date range', () => {
    expect(countTargetNights({
      dateFrom: '2026-10-05',
      dateTo: '2026-10-11',
      allDays: false,
      selectedDays: new Set([1, 5]),
    })).toBe(2);
  });

  it('calculates the publication impact for selected rate plans', () => {
    const review = buildRateUpdateReview({
      dateFrom: '2026-10-05',
      dateTo: '2026-10-07',
      allDays: true,
      selectedDays: new Set(),
      selections: { STD: new Set(['BAR', 'NRF']), DLX: new Set(['BAR']) },
      enabledFields: new Set(['rate', 'availability']),
      roomValues: {
        STD: { rate: '1500', availability: '4' },
        DLX: { rate: '2400', availability: '2' },
      },
      selectedChannelCodes: new Set(['booking', 'expedia']),
    });

    expect(review).toMatchObject({ dateCount: 3, roomCount: 2, planCount: 3, channelCount: 2, cellCount: 9 });
    expect(review.errors).toEqual([]);
  });

  it('blocks invalid prices and surfaces destructive restrictions', () => {
    const review = buildRateUpdateReview({
      dateFrom: '2026-10-08',
      dateTo: '2026-10-08',
      allDays: true,
      selections: { STD: new Set(['BAR']) },
      enabledFields: new Set(['rate', 'stop_sell']),
      roomValues: { STD: { rate: '0', stop_sell: true } },
      selectedChannelCodes: new Set(),
    });

    expect(review.errors).toContain('STD için fiyat sıfırdan büyük olmalıdır.');
    expect(review.warnings).toContain('STD satışa kapatılacak.');
    expect(review.warnings).toContain('OTA kanalı seçilmedi; değişiklik yalnızca PMS ve seçili acente kapsamına uygulanır.');
  });
});
