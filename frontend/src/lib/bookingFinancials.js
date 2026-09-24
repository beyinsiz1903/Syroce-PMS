import { cachedTenantCurrency } from '@/lib/currency';

const finiteOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const firstFinite = (...values) => {
  for (const value of values) {
    const number = finiteOrNull(value);
    if (number !== null) return number;
  }
  return null;
};

export function normalizeCurrencyCode(value) {
  const code = String(value || cachedTenantCurrency() || 'TRY').toUpperCase();
  return code === 'TL' || code === '₺' ? 'TRY' : code;
}

/**
 * Normalizes the financial aliases returned by booking, front-desk and folio
 * endpoints. Folio totals are authoritative because they include extras such
 * as minibar, food & beverage and laundry charges.
 */
export function bookingFinancials(booking = {}, folios = []) {
  const folioRows = Array.isArray(folios) ? folios : [];
  const folioBalance = folioRows.length
    ? folioRows.reduce((sum, folio) => sum + (finiteOrNull(folio?.balance) || 0), 0)
    : null;
  const paid = firstFinite(
    booking.folio_total_paid,
    booking.payments_total,
    booking.total_paid,
    booking.paid_amount,
  ) || 0;
  const explicitBalance = folioBalance ?? firstFinite(
    booking.folio_balance,
    booking.balance_due,
    booking.outstanding_balance,
    booking.balance,
  );
  const statedTotal = firstFinite(
    booking.folio_total_charges,
    booking.total_charges,
    booking.grand_total,
    booking.total_amount,
    booking.total_price,
  );
  // A fetched folio balance is newer than the booking snapshot. Reconstruct
  // the displayed total from paid + balance so newly posted extras are visible.
  const total = folioBalance !== null
    ? paid + folioBalance
    : (statedTotal ?? (explicitBalance !== null ? paid + explicitBalance : 0));
  const balance = explicitBalance !== null ? explicitBalance : total - paid;

  return {
    total: Math.round(total * 100) / 100,
    paid: Math.round(paid * 100) / 100,
    balance: Math.round(balance * 100) / 100,
    currency: normalizeCurrencyCode(booking.currency || booking.currency_code),
  };
}
