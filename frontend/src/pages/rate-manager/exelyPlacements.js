export const PLACEMENT_LABELS = {
  adult_main: 'Yetişkin · ana yatak (oda toplamı)',
  child_main: 'Çocuk · ana yatak (çocuk başı)',
  adult_extra: 'Yetişkin · ek yatak (kişi başı)',
  child_extra: 'Çocuk · ek yatak (çocuk başı)',
  child_without_bed: 'Çocuk · yataksız (çocuk başı)',
};

const money = value => {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean'
    || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1e12) throw new Error('Yerleşim fiyatı geçersiz.');
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
};
const sortPrices = (a, b) => a.kind.localeCompare(b.kind) || (a.number_of_guests || 0) - (b.number_of_guests || 0) || (a.min_age ?? -1) - (b.min_age ?? -1);

export const compileExelyGuestPrices = (rule, baseRate, currency) => {
  const count = rule?.base_occupancy;
  if (!Number.isInteger(count) || count < 1 || count > 20) throw new Error('Fiyata dahil yetişkin sayısını kaydedin.');
  const base = money(baseRate);
  if (base <= 0) throw new Error('Taban fiyat sıfırdan büyük olmalıdır.');
  const result = [{ kind: 'adult_main', number_of_guests: count, amount: base }];
  if (rule.pricing_type !== 'per_person') return result;
  const rows = rule.exely_price_placements ?? [];
  if (!Array.isArray(rows) || rows.length > 100) throw new Error('En fazla 100 Exely yerleşim tarifesi tanımlanabilir.');
  if (rows.length && rule.exely_placements_reviewed !== true) throw new Error('Exely yerleşim kapasitesi ve çocuk yaş aralıklarını kontrol edip tarifeleri kaydedin.');
  const seen = new Set([`adult_main:${count}`]);
  const bands = {};
  rows.forEach(row => {
    const kind = row.kind;
    if (!PLACEMENT_LABELS[kind] || !['fixed', 'percentage'].includes(row.price_mode)) throw new Error('Yerleşim türü veya fiyat yöntemi geçersiz.');
    const value = money(row.value);
    if (row.price_mode === 'fixed' && rule.currency !== currency) throw new Error('Yerleşim tarife para birimini kontrol edip yeniden kaydedin.');
    const price = { kind, amount: row.price_mode === 'fixed' ? value : money(base * value / 100) };
    let key = kind;
    if (kind === 'adult_main') {
      if (!Number.isInteger(row.number_of_guests) || row.number_of_guests < 1 || row.number_of_guests > 20 || price.amount <= 0) throw new Error('Yetişkin ana yatak sayısı veya fiyatı geçersiz.');
      price.number_of_guests = row.number_of_guests;
      key += `:${row.number_of_guests}`;
    } else if (kind.startsWith('child_')) {
      const low = row.min_age, high = row.max_age;
      if (!Number.isInteger(low) || !Number.isInteger(high) || low < 0 || high < low || high > 17) throw new Error('Çocuk yaş aralığı 0–17 olmalıdır.');
      if ((bands[kind] || []).some(([min, max]) => low <= max && high >= min)) throw new Error('Çocuk yaş aralıkları çakışamaz.');
      (bands[kind] ||= []).push([low, high]);
      price.min_age = low;
      price.max_age = high + 1; // Exely upper bound is exclusive.
      key += `:${low}:${high}`;
    }
    if (seen.has(key)) throw new Error('Aynı yerleşim veya taban yetişkin sayısı tekrar eklenemez.');
    seen.add(key);
    result.push(price);
  });
  return result.sort(sortPrices);
};

export const placementDescription = price => `${PLACEMENT_LABELS[price.kind] || price.kind}${price.kind === 'adult_main' ? ` · ${price.number_of_guests} yetişkin` : price.min_age !== undefined ? ` · ${price.min_age}–${price.max_age - 1} yaş` : ''}: ${price.amount}`;

export const sameExelyGuestPrices = (expected, received) => {
  if (!Array.isArray(expected) || !Array.isArray(received)) return false;
  const canonical = prices => prices.map(price => JSON.stringify([price?.kind, price?.number_of_guests ?? null,
    price?.min_age ?? null, price?.max_age ?? null, price?.amount])).sort();
  return JSON.stringify(canonical(expected)) === JSON.stringify(canonical(received));
};
