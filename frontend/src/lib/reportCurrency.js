import { formatCurrency } from '@/lib/currency';

export const roomRevenueSourceLabel = source => source === 'mixed' ? 'İşlenmiş + tahakkuk (eksik gün/döviz)'
  : source === 'accrued' ? 'Tahakkuk eden' : source === 'posted' ? 'Folyoya işlenmiş' : 'Kaynak bilgisi yok';

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
      formatted: formatCurrency(entry.amount, entry.currency, { locale, decimals: 2, compactDecimals: false }),
    }));
}

export function isMixedCurrencyBreakdown(breakdown) {
  return currencyBreakdownEntries(breakdown).length > 1;
}

export function formatCurrencyBreakdown(breakdown, fallbackAmount = 0, fallbackCurrency = 'TRY', locale = 'tr-TR') {
  const entries = currencyBreakdownEntries(breakdown, locale);
  if (entries.length === 0) {
    const zeroCurrencies = Object.entries(breakdown || {})
      .filter(([code, value]) => code && value != null && Number(value) === 0)
      .map(([code]) => code).sort();
    return zeroCurrencies.length
      ? zeroCurrencies.map(code => formatCurrency(0, code, { locale, decimals: 2, compactDecimals: false })).join(' · ')
      : formatCurrency(fallbackAmount || 0, fallbackCurrency || 'TRY', { locale, decimals: 2, compactDecimals: false });
  }
  return entries
    .map(({ currency, formatted }) => entries.length > 1 ? `${currency}: ${formatted}` : formatted)
    .join(' · ');
}
