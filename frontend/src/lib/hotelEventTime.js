// API event timestamps are UTC, including legacy datetime.utcnow() values
// without a suffix. Calendar/business/service days are NOT event instants.
export const HOTEL_EVENT_TIME_ZONE = 'Europe/Istanbul';
export const HOTEL_EVENT_TIME_ZONE_LABEL = 'Türkiye saati · Europe/Istanbul';
const formatter = new Intl.DateTimeFormat('tr-TR', {
  timeZone: HOTEL_EVENT_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

function eventInstant(value) {
  let instant;
  if (value instanceof Date) instant = value;
  else {
    const raw = String(value || '').trim().replace(' ', 'T');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})?$/i.test(raw)) return null;
    instant = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`);
  }
  return Number.isFinite(instant.getTime()) ? instant : null;
}

export function hotelEventEpoch(value) {
  return eventInstant(value)?.getTime() ?? null;
}

function parts(value) {
  const instant = eventInstant(value);
  if (!instant) return null;
  return Object.fromEntries(formatter.formatToParts(instant).map(part => [part.type, part.value]));
}

export function formatHotelEventTimestamp(value, { seconds = true } = {}) {
  const p = parts(value);
  return p ? `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}${seconds ? `:${p.second}` : ''}` : '—';
}

export function formatHotelEventTime(value, { seconds = true } = {}) {
  const p = parts(value);
  return p ? `${p.hour}:${p.minute}${seconds ? `:${p.second}` : ''}` : '—';
}

export function hotelEventDay(value = new Date()) {
  const p = parts(value);
  return p ? `${p.year}-${p.month}-${p.day}` : '';
}
