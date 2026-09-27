import { formatCurrency } from '@/lib/currency';

export function formatCurrencyBreakdown(breakdown, fallbackAmount = 0, fallbackCurrency = 'TRY', locale = 'tr-TR') {
  const entries = Object.entries(breakdown || {}).filter(([, amount]) => Number(amount) !== 0);
  if (entries.length === 0) {
    return formatCurrency(fallbackAmount || 0, fallbackCurrency || 'TRY', { locale });
  }
  return entries
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amount]) => formatCurrency(amount, currency, { locale }))
    .join(' · ');
}
