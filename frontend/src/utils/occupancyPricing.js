export const DEFAULT_OCCUPANCY_RULE = Object.freeze({
  pricing_type: 'per_room',
  base_occupancy: 2,
  extra_adult_rate: 0,
  extra_child_rate: 0,
  child_free_age_max: 0,
  child_age_bands: null,
  max_occupancy: null,
  pricing_version: 'occupancy-v2',
});

const legacyChildAgeBands = rule => {
  const freeAgeMax = Number(rule.child_free_age_max ?? 0);
  const bands = [{ min_age: 0, max_age: freeAgeMax, pricing_mode: 'free', value: 0 }];
  if (freeAgeMax < 17) {
    bands.push({
      min_age: freeAgeMax + 1,
      max_age: 17,
      pricing_mode: 'fixed',
      value: Number(rule.extra_child_rate ?? 0),
    });
  }
  return bands;
};

export const normalizeOccupancyRule = (rule = {}) => {
  const suppliedBands = Array.isArray(rule.child_age_bands) && rule.child_age_bands.length > 0
    ? rule.child_age_bands
    : legacyChildAgeBands(rule);
  return {
    ...DEFAULT_OCCUPANCY_RULE,
    ...rule,
    base_occupancy: Number(rule.base_occupancy ?? 2),
    extra_adult_rate_type: ["fixed", "percentage"].includes(rule.extra_adult_rate_type) ? rule.extra_adult_rate_type : "fixed",
    extra_adult_rate: Number(rule.extra_adult_rate ?? 0),
    extra_child_rate: Number(rule.extra_child_rate ?? 0),
    child_free_age_max: Number(rule.child_free_age_max ?? 0),
    child_age_bands: suppliedBands.map(band => ({
      min_age: Number(band.min_age),
      max_age: Number(band.max_age),
      pricing_mode: band.pricing_mode,
      value: Number(band.value ?? 0),
    })),
    max_occupancy: rule.max_occupancy === null || rule.max_occupancy === '' || rule.max_occupancy === undefined
      ? null
      : Number(rule.max_occupancy),
  };
};

const roomKeys = room => [room?.room_type_code, room?.room_type, room?.type, room?.room_type_name]
  .filter(Boolean)
  .map(value => String(value).trim().toLocaleLowerCase('tr-TR'));

export const findOccupancyRule = (rules = {}, room = {}) => {
  const keys = roomKeys(room);
  const entry = Object.entries(rules).find(([code]) => keys.includes(String(code).trim().toLocaleLowerCase('tr-TR')));
  return entry ? normalizeOccupancyRule(entry[1]) : null;
};

export const nightsBetween = (checkIn, checkOut) => {
  const start = new Date(`${checkIn}T00:00:00Z`);
  const end = new Date(`${checkOut}T00:00:00Z`);
  const nights = Math.round((end - start) / 86400000);
  return Number.isFinite(nights) ? Math.max(0, nights) : 0;
};

const roundMoney = value => Math.round((Number(value) + Number.EPSILON) * 100) / 100;

export const calculateOccupancyPrice = ({ baseNightlyRate, nights, adults, childrenAges = [], rule }) => {
  const normalized = normalizeOccupancyRule(rule);
  const base = Number(baseNightlyRate);
  const numericAges = childrenAges.map(Number);
  const guestCount = Number(adults) + numericAges.length;
  if (!Number.isFinite(base) || base < 0 || nights < 1 || adults < 1
    || numericAges.some(age => !Number.isInteger(age) || age < 0 || age > 17)
    || (normalized.max_occupancy !== null && guestCount > normalized.max_occupancy)) return null;
    
  let adultRate = 0;
  if (normalized.pricing_type === 'per_person') {
    adultRate = normalized.extra_adult_rate_type === 'percentage'
      ? roundMoney(base * normalized.extra_adult_rate / 100)
      : normalized.extra_adult_rate;
  }

  const extraAdults = normalized.pricing_type === 'per_person'
    ? Math.max(0, Number(adults) - normalized.base_occupancy)
    : 0;
  const childBreakdown = normalized.pricing_type === 'per_person'
    ? (() => {
      let includedAdultSlots = Math.max(0, normalized.base_occupancy - Number(adults));
      return numericAges.map(age => {
        const band = normalized.child_age_bands.find(candidate => candidate.min_age <= age && age <= candidate.max_age);
        if (!band) return { age, pricingMode: 'invalid', rate: Number.NaN };
        let rate = 0;
        if (band.pricing_mode === 'fixed') rate = band.value;
        if (band.pricing_mode === 'adult_percentage') rate = roundMoney(adultRate * band.value / 100);
        if (band.pricing_mode === 'adult_rate') {
          if (includedAdultSlots > 0) includedAdultSlots -= 1;
          else rate = adultRate;
        }
        return { age, pricingMode: band.pricing_mode, rate, countsAsAdult: band.pricing_mode === 'adult_rate' };
      });
    })()
    : [];
  if (childBreakdown.some(item => !Number.isFinite(item.rate))) return null;
  const chargeableChildren = childBreakdown.filter(item => item.rate > 0).length;
  const freeChildren = childBreakdown.filter(item => item.rate === 0).length;
  const adultSupplement = roundMoney(extraAdults * adultRate);
  const childSupplement = roundMoney(childBreakdown.reduce((sum, item) => sum + item.rate, 0));
  const nightlyTotal = roundMoney(base + adultSupplement + childSupplement);
  return {
    baseNightlyRate: base,
    nights,
    extraAdults,
    chargeableChildren,
    freeChildren,
    childBreakdown,
    adultSupplement,
    childSupplement,
    nightlyTotal,
    totalAmount: roundMoney(nightlyTotal * nights),
    rule: normalized,
  };
};
