const normalizeCurrency = value => String(value || 'TRY').trim().toUpperCase() === 'TL'
  ? 'TRY'
  : String(value || 'TRY').trim().toUpperCase();

export function calculateBookingStats(bookings = []) {
  const revenueByCurrency = {};
  const countByCurrency = {};

  bookings.forEach((booking) => {
    const currency = normalizeCurrency(booking.currency || booking.currency_code);
    const amount = Number(booking.total_amount) || 0;
    revenueByCurrency[currency] = (revenueByCurrency[currency] || 0) + amount;
    countByCurrency[currency] = (countByCurrency[currency] || 0) + 1;
  });

  const adrByCurrency = Object.fromEntries(
    Object.entries(revenueByCurrency).map(([currency, amount]) => [
      currency,
      amount / countByCurrency[currency],
    ]),
  );

  return {
    total: bookings.length,
    confirmed: bookings.filter(booking => booking.status === 'confirmed').length,
    checkedIn: bookings.filter(booking => booking.status === 'checked_in').length,
    revenueByCurrency,
    adrByCurrency,
  };
}
