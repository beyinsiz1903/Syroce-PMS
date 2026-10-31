// Cashier API timestamps are UTC, including legacy datetime.utcnow() strings
// without a suffix. Calendar/business days are NOT timestamps and stay unchanged.
export const CASHIER_TIME_ZONE_LABEL = 'Türkiye saati · Europe/Istanbul';
const options = { timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' };
const formatter = new Intl.DateTimeFormat('tr-TR', options);

function parts(value) {
  let instant;
  if (value instanceof Date) instant = value;
  else {
    const raw = String(value || '').trim().replace(' ', 'T');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})?$/i.test(raw)) return null;
    instant = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`);
  }
  if (!Number.isFinite(instant.getTime())) return null;
  return Object.fromEntries(formatter.formatToParts(instant).map(part => [part.type, part.value]));
}

export function formatCashierTimestamp(value, { seconds = false } = {}) {
  const p = parts(value);
  return p ? `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}${seconds ? `:${p.second}` : ''}` : '—';
}

export function formatCashierTime(value) {
  const p = parts(value);
  return p ? `${p.hour}:${p.minute}` : '—';
}

export function cashierCalendarDay(value = new Date()) {
  const p = parts(value);
  return p ? `${p.year}-${p.month}-${p.day}` : '';
}
