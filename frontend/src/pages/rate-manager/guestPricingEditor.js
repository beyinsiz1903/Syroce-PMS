import { compileExelyGuestPrices } from './exelyPlacements';

const numberPresent = value => value !== '' && value !== null && value !== undefined
  && typeof value !== 'boolean' && (typeof value !== 'string' || value.trim() !== '') && Number.isFinite(Number(value));
const amountValid = value => numberPresent(value) && Number(value) >= 0 && Number(value) <= 1e12;
const ageValid = value => numberPresent(value) && Number.isInteger(Number(value)) && Number(value) >= 0 && Number(value) <= 17;

export const formatGuestAmount = (value, currency) => `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(value)}${currency ? ` ${currency}` : ''}`;

// Shared by the editor's disabled state and save handler. Blank is never zero.
export const validateGuestPricingDraft = draft => {
  const errors = [];
  if (!numberPresent(draft.base_occupancy) || !Number.isInteger(Number(draft.base_occupancy))
    || Number(draft.base_occupancy) < 1 || Number(draft.base_occupancy) > 20) errors.push('Fiyata dahil yetişkin sayısı 1–20 arasında olmalıdır.');
  if (draft.max_occupancy !== '' && draft.max_occupancy != null
    && (!numberPresent(draft.max_occupancy) || !Number.isInteger(Number(draft.max_occupancy))
      || Number(draft.max_occupancy) < Number(draft.base_occupancy) || Number(draft.max_occupancy) > 50)) errors.push('Maksimum kişi sayısı, dahil yetişkin sayısından az olamaz; en fazla 50 olabilir.');
  if (!amountValid(draft.extra_adult_rate) || !['fixed', 'percentage'].includes(draft.extra_adult_rate_type)) errors.push('Ek yetişkin ücretini sıfır veya pozitif bir tutar olarak girin.');
  const bands = [...draft.child_age_bands].sort((a, b) => Number(a.min_age) - Number(b.min_age));
  let expected = 0;
  const valid = bands.length > 0 && bands.every(band => {
    const matches = ageValid(band.min_age) && ageValid(band.max_age)
      && Number(band.min_age) === expected && Number(band.max_age) >= Number(band.min_age)
      && ['free', 'fixed', 'adult_percentage', 'adult_rate'].includes(band.pricing_mode)
      && (!['fixed', 'adult_percentage'].includes(band.pricing_mode) || amountValid(band.value))
      && (band.pricing_mode !== 'adult_percentage' || Number(band.value) <= 100);
    expected = Number(band.max_age) + 1;
    return matches;
  }) && expected === 18;
  if (!valid) errors.push('Çocuk yaş kademeleri 0–17 aralığını boşluk ve çakışma olmadan kapsamalı; ücretler geçerli olmalıdır.');
  return errors;
};

// Validate the saved tariff independently of the example room price. A room
// price may not have been entered yet; percentage previews must not invent one.
export const exelyDraftError = (draft, currency) => {
  try {
    compileExelyGuestPrices({ ...draft, pricing_type: 'per_person', exely_placements_reviewed: true, currency }, 100, currency);
    return '';
  } catch (error) { return error.message; }
};

export const nextAdultPlacement = (rows, baseGuests) => {
  const used = new Set([Number(baseGuests), ...rows.filter(row => row.kind === 'adult_main').map(row => row.number_of_guests)]);
  return Array.from({ length: 20 }, (_, index) => index + 1).find(count => !used.has(count));
};

export const nextChildAgeBand = (bands, kind) => {
  const relevant = kind ? bands.filter(row => row.kind === kind) : bands;
  const covered = age => relevant.some(row => ageValid(row.min_age) && ageValid(row.max_age)
    && Number(row.min_age) <= age && age <= Number(row.max_age));
  const start = Array.from({ length: 18 }, (_, age) => age).find(age => !covered(age));
  if (start === undefined) return null;
  let end = start;
  while (end < 17 && !covered(end + 1)) end += 1;
  return { min_age: start, max_age: end };
};
