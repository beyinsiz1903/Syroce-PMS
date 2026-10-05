import { formatCurrency } from '@/lib/currency';

export function currencyBreakdownEntries(breakdown, locale = 'tr-TR') {
  return Object.entries(breakdown || {})
    .map(([currency, amount]) => ({
      currency: String(currency || '').trim().toUpperCase(),
      amount: Number(amount),
    }))
    .filter(({ currency, amount }) => currency && Number.isFinite(amount) && amount !== 0)
    .sort((left, right) => left.currency.localeCompare(right.currency))
    .map((entry) => ({
      ...entry,
      formatted: formatCurrency(entry.amount, entry.currency, { locale }),
    }));
}

export function isMixedCurrencyBreakdown(breakdown) {
  return currencyBreakdownEntries(breakdown).length > 1;
}

export function formatCurrencyBreakdown(breakdown, fallbackAmount = 0, fallbackCurrency = 'TRY', locale = 'tr-TR') {
  const entries = currencyBreakdownEntries(breakdown, locale);
  if (entries.length === 0) {
    return formatCurrency(fallbackAmount || 0, fallbackCurrency || 'TRY', { locale });
  }
  return entries
    .map(({ currency, formatted }) => entries.length > 1 ? `${currency}: ${formatted}` : formatted)
    .join(' · ');
}
