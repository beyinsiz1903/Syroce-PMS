import { describe, expect, it } from 'vitest';

import { buildRateUpdateReview, countTargetNights } from '@/pages/rate-manager/updateReview';

describe('rate update review', () => {
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
