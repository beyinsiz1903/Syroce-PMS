export const DEFAULT_OCCUPANCY_RULE = Object.freeze({
  pricing_type: 'per_room',
  base_occupancy: 2,
  extra_adult_rate: 0,
  extra_child_rate: 0,
  child_free_age_max: 0,
  max_occupancy: null,
  pricing_version: 'occupancy-v1',
});

export const normalizeOccupancyRule = (rule = {}) => ({
  ...DEFAULT_OCCUPANCY_RULE,
  ...rule,
  base_occupancy: Number(rule.base_occupancy ?? 2),
  extra_adult_rate: Number(rule.extra_adult_rate ?? 0),
  extra_child_rate: Number(rule.extra_child_rate ?? 0),
  child_free_age_max: Number(rule.child_free_age_max ?? 0),
  max_occupancy: rule.max_occupancy === null || rule.max_occupancy === '' || rule.max_occupancy === undefined
    ? null
    : Number(rule.max_occupancy),
});

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

export const calculateOccupancyPrice = ({ baseNightlyRate, nights, adults, childrenAges = [], rule }) => {
  const normalized = normalizeOccupancyRule(rule);
  const base = Number(baseNightlyRate);
  if (!Number.isFinite(base) || base < 0 || nights < 1 || adults < 1) return null;
  const extraAdults = normalized.pricing_type === 'per_person'
    ? Math.max(0, Number(adults) - normalized.base_occupancy)
    : 0;
  const chargeableChildren = normalized.pricing_type === 'per_person'
    ? childrenAges.filter(age => Number(age) > normalized.child_free_age_max).length
    : 0;
  const adultSupplement = extraAdults * normalized.extra_adult_rate;
  const childSupplement = chargeableChildren * normalized.extra_child_rate;
  const nightlyTotal = base + adultSupplement + childSupplement;
  return {
    baseNightlyRate: base,
    nights,
    extraAdults,
    chargeableChildren,
    adultSupplement,
    childSupplement,
    nightlyTotal,
    totalAmount: nightlyTotal * nights,
    rule: normalized,
  };
};
