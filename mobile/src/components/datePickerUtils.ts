// Pure, timezone-safe date helpers backing <DatePicker>.
//
// These are deliberately kept free of React / React Native imports so the
// picker's date math (the part a future refactor could silently break) can be
// unit-tested in plain Node without a render harness. The component imports
// every helper from here — there is no duplicated logic.

export type DateParts = { y: number; m: number; d: number };

export function pad(n: number): string {
  return String(n).padStart(2, '0');
}

// Build a YYYY-MM-DD string from local Y/M/D parts. `m` is 0-based (0 = Jan),
// matching JS Date semantics. No Date object is constructed, so there is no UTC
// conversion and therefore no off-by-one day across timezones.
export function toISO(y: number, m: number, d: number): string {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

// Parse a YYYY-MM-DD string into local Y/M/D parts (no timezone shift).
// Returns null for empty/undefined/malformed input.
export function parseISO(iso?: string): DateParts | null {
  if (!iso) return null;
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]) - 1;
  const d = Number(match[3]);
  if (m < 0 || m > 11 || d < 1 || d > 31) return null;
  return { y, m, d };
}

export function daysInMonth(y: number, m: number): number {
  return new Date(y, m + 1, 0).getDate();
}

// Monday-based weekday index (0 = Monday … 6 = Sunday) for the 1st of a month.
export function firstWeekdayIndex(y: number, m: number): number {
  return (new Date(y, m, 1).getDay() + 6) % 7;
}

// True when (y, m, d) falls strictly before the inclusive lower bound.
// `minParts == null` means "no lower bound" → nothing is disabled.
// Comparison is on the canonical YYYY-MM-DD string so it stays lexical and
// timezone-free.
export function isBeforeMinParts(
  minParts: DateParts | null,
  y: number,
  m: number,
  d: number,
): boolean {
  if (!minParts) return false;
  return toISO(y, m, d) < toISO(minParts.y, minParts.m, minParts.d);
}

// Convenience overload that parses the ISO bound itself.
export function isBeforeMin(
  minimumDate: string | undefined,
  y: number,
  m: number,
  d: number,
): boolean {
  return isBeforeMinParts(parseISO(minimumDate), y, m, d);
}

// Calendar grid cells for a month: leading blanks (null) to align the 1st to
// its Monday-based weekday, then 1..daysInMonth.
export function buildMonthCells(y: number, m: number): (number | null)[] {
  const lead = firstWeekdayIndex(y, m);
  const total = daysInMonth(y, m);
  const out: (number | null)[] = [];
  for (let i = 0; i < lead; i += 1) out.push(null);
  for (let d = 1; d <= total; d += 1) out.push(d);
  return out;
}

// Local Y/M/D parts for "now" (or an injected Date in tests).
export function todayParts(now: Date = new Date()): DateParts {
  return { y: now.getFullYear(), m: now.getMonth(), d: now.getDate() };
}

// Resolve the "Today" shortcut: the ISO for today, or null when today is before
// the minimum bound (shortcut must not select a disabled day).
export function todayShortcutISO(
  today: DateParts,
  minimumDate?: string,
): string | null {
  if (isBeforeMin(minimumDate, today.y, today.m, today.d)) return null;
  return toISO(today.y, today.m, today.d);
}
