import { describe, expect, it } from 'vitest';
import { calculateOccupancyPrice, findOccupancyRule, nightsBetween } from '../occupancyPricing';

const rule = {
  pricing_type: 'per_person',
  base_occupancy: 2,
  extra_adult_rate: 1500,
  extra_child_rate: 750,
  child_free_age_max: 6,
  max_occupancy: 4,
};

describe('occupancy pricing', () => {
  it('adds the third adult supplement for every night', () => {
    const quote = calculateOccupancyPrice({ baseNightlyRate: 5000, nights: 2, adults: 3, rule });
    expect(quote.nightlyTotal).toBe(6500);
    expect(quote.totalAmount).toBe(13000);
  });

  it('charges only children older than the free-age limit', () => {
    const quote = calculateOccupancyPrice({ baseNightlyRate: 5000, nights: 1, adults: 2, childrenAges: [6, 7], rule });
    expect(quote.chargeableChildren).toBe(1);
    expect(quote.totalAmount).toBe(5750);
  });

  it('finds rules using the PMS room type independent of letter case', () => {
    expect(findOccupancyRule({ STANDARD: rule }, { room_type: 'standard' })).toMatchObject(rule);
  });

  it('calculates stay nights using UTC dates', () => {
    expect(nightsBetween('2026-08-26', '2026-08-28')).toBe(2);
  });
});
