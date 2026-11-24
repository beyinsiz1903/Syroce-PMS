// Mirror server cents allocation for the confirmation preview. Server revalidates
// current balances under the financial transaction before writing anything.
export function previewGroupCollection(total, balances, distribution) {
  const raw = Number(total) * 100;
  const caps = balances.map(value => Math.max(0, Math.round(Number(value) * 100)));
  if (!Number.isFinite(raw) || Math.abs(raw - Math.round(raw)) > 0.00001 || raw <= 0 || raw > caps.reduce((a, b) => a + b, 0)) return null;
  let remaining = Math.round(raw);
  const result = caps.map(() => 0);
  if (distribution === 'balance_only') {
    caps.forEach((cap, index) => { result[index] = Math.min(cap, remaining); remaining -= result[index]; });
  } else {
    while (remaining) {
      const active = caps.map((_, i) => i).filter(i => caps[i] > result[i]);
      const weights = active.map(i => distribution === 'proportional' ? caps[i] : 1);
      const denominator = weights.reduce((a, b) => a + b, 0);
      const budget = remaining;
      const fractions = new Map();
      active.forEach((i, j) => {
        const numerator = BigInt(budget) * BigInt(weights[j]);
        const share = Math.min(caps[i] - result[i], Number(numerator / BigInt(denominator)));
        fractions.set(i, numerator % BigInt(denominator));
        result[i] += share; remaining -= share;
      });
      active.sort((a, b) => (fractions.get(b) > fractions.get(a) ? 1 : fractions.get(b) < fractions.get(a) ? -1 : a - b)).forEach(i => {
        if (remaining && result[i] < caps[i]) { result[i]++; remaining--; }
      });
    }
  }
  return result.map(value => value / 100);
}
