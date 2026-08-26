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

const tieredRule = {
  ...rule,
  max_occupancy: 5,
  child_age_bands: [
    { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
    { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
    { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
  ],
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

  it('calculates free, half adult and full adult child age tiers', () => {
    const quote = calculateOccupancyPrice({
      baseNightlyRate: 5000,
      nights: 2,
      adults: 2,
      childrenAges: [6, 7, 12],
      rule: tieredRule,
    });
    expect(quote.childBreakdown.map(child => child.rate)).toEqual([0, 750, 1500]);
    expect(quote.freeChildren).toBe(1);
    expect(quote.childSupplement).toBe(2250);
    expect(quote.totalAmount).toBe(14500);
  });

  it('counts a 12+ child as an adult before adding an extra-person charge', () => {
    const quote = calculateOccupancyPrice({
      baseNightlyRate: 5000,
      nights: 1,
      adults: 1,
      childrenAges: [12],
      rule: tieredRule,
    });
    expect(quote.childBreakdown[0]).toMatchObject({ rate: 0, countsAsAdult: true });
    expect(quote.nightlyTotal).toBe(5000);
  });

  it('rounds percentage supplements to currency precision like the backend', () => {
    const quote = calculateOccupancyPrice({
      baseNightlyRate: 5000,
      nights: 1,
      adults: 2,
      childrenAges: [8],
      rule: {
        ...tieredRule,
        extra_adult_rate: 999.99,
        child_age_bands: tieredRule.child_age_bands.map(band => band.pricing_mode === 'adult_percentage'
          ? { ...band, value: 33.33 }
          : band),
      },
    });
    expect(quote.childSupplement).toBe(333.3);
    expect(quote.nightlyTotal).toBe(5333.3);
  });

  it('finds rules using the PMS room type independent of letter case', () => {
    expect(findOccupancyRule({ STANDARD: rule }, { room_type: 'standard' })).toMatchObject(rule);
  });

  it('calculates stay nights using UTC dates', () => {
    expect(nightsBetween('2026-08-26', '2026-08-28')).toBe(2);
  });
});
