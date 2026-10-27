// Stay dates are hotel calendar days, not instants in the browser's timezone.
const calendarDay = value => {
  const match = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2})(?:$|T| )/.exec(value);
  if (!match) return null;
  const [, year, month, day] = match.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
    ? date.getTime() : null;
};

export function sortBookingsByStay(bookings = [], businessDate, order = 'nearest') {
  const reference = calendarDay(businessDate);
  // Without a verified business day, chronological order is the safest fallback.
  // Never replace a hotel's business date with the operator's device clock.
  const distance = booking => {
    const start = calendarDay(booking.check_in);
    if (start === null) return null;
    const end = calendarDay(booking.check_out);
    if (reference === null) return start;
    if (end !== null && end >= start && start <= reference && reference <= end) return 0;
    return Math.min(Math.abs(start - reference), end !== null && end >= start ? Math.abs(end - reference) : Infinity);
  };

  return [...bookings].sort((left, right) => {
    const a = distance(left), b = distance(right);
    if (a === null || b === null) return a === b ? String(left.id).localeCompare(String(right.id)) : a === null ? 1 : -1;
    return (order === 'farthest' ? b - a : a - b)
      || calendarDay(left.check_in) - calendarDay(right.check_in)
      || String(left.id).localeCompare(String(right.id));
  });
}
