// SPA inputs are hotel wall clocks; the API receives explicit UTC instants.
// Never interpret a datetime-local value in the travelling operator's browser TZ.
export function spaTimeZone(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    new Intl.DateTimeFormat('en-GB', { timeZone: value }).format(0);
    return value;
  } catch { return null; }
}

function instant(value) {
  if (value instanceof Date) return Number.isFinite(value.getTime()) ? value : null;
  const raw = String(value || '').trim().replace(' ', 'T');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})?$/i.test(raw)) return null;
  // Legacy SPA naive timestamps were persisted by the API as UTC.
  const result = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`);
  return Number.isFinite(result.getTime()) ? result : null;
}

export function spaDateTimeInput(value, timeZone) {
  const date = instant(value);
  if (!date || !spaTimeZone(timeZone)) return '';
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function formatSpaTime(value, timeZone) {
  const wall = spaDateTimeInput(value, timeZone);
  return wall ? `${wall.slice(8, 10)}.${wall.slice(5, 7)} ${wall.slice(11)}` : '—';
}

export function spaWallTimeToUtc(value, timeZone) {
  if (!spaTimeZone(timeZone)) throw new Error('Tesis saat dilimi doğrulanamadı. Yenileyip tekrar deneyin.');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value || '')) throw new Error('Geçerli bir başlangıç tarihi ve saati girin.');
  const naive = new Date(`${value}:00Z`);
  if (!Number.isFinite(naive.getTime()) || naive.toISOString().slice(0, 16) !== value) {
    throw new Error('Geçerli bir başlangıç tarihi ve saati girin.');
  }
  // Sample both sides of a possible offset transition, then round-trip every
  // candidate. Nonexistent and repeated DST wall times must not silently shift.
  const matches = new Set();
  for (const hours of [-36, -12, 0, 12, 36]) {
    const probe = naive.getTime() + hours * 60 * 60 * 1000;
    const wallAtProbe = spaDateTimeInput(new Date(probe), timeZone);
    const offset = Date.parse(`${wallAtProbe}:00Z`) - probe;
    const candidate = naive.getTime() - offset;
    if (spaDateTimeInput(new Date(candidate), timeZone) === value) matches.add(candidate);
  }
  if (!matches.size) throw new Error('Bu saat tesisin saat diliminde mevcut değil. Başka bir saat seçin.');
  if (matches.size > 1) throw new Error('Bu saat tesisin saat diliminde iki kez oluşuyor. Başka bir saat seçin.');
  return new Date([...matches][0]).toISOString();
}
