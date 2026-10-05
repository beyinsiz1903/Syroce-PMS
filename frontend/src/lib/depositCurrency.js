import { formatCurrency } from '@/lib/currency';

export const normalizeDepositCurrency = value => {
  const code = String(value || 'TRY').toUpperCase();
  return code === 'TL' ? 'TRY' : code;
};

export const depositCurrency = deposit => normalizeDepositCurrency(deposit?.currency);

export const formatDepositAmount = (amount, currency, language) => formatCurrency(
  Number(amount || 0),
  normalizeDepositCurrency(currency),
  { locale: language, decimals: 2 }
);

export const depositTotalsByCurrency = (rows, amountForRow) => Object.entries(
  rows.reduce((totals, row) => {
    const currency = depositCurrency(row);
    totals[currency] = (totals[currency] || 0) + Number(amountForRow(row) || 0);
    return totals;
  }, {})
).sort(([left], [right]) => left.localeCompare(right));

export const formatDepositTotals = (totals, language) => totals.length
  ? totals.map(([currency, amount]) => formatDepositAmount(amount, currency, language)).join(' · ')
  : formatDepositAmount(0, 'TRY', language);
