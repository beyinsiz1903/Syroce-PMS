export function reservationDateInput(input: string): string | undefined {
  const raw = input.trim();
  const display = raw.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  const iso = display ? `${display[3]}-${display[2].padStart(2, '0')}-${display[1].padStart(2, '0')}` : raw;
  const parts = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!parts) return undefined;
  const [y, m, d] = parts.slice(1).map(Number);
  if (y < 1900 || m < 1 || m > 12 || d < 1 || d > new Date(y, m, 0).getDate()) return undefined;
  return iso;
}

export function reservationGuestCount(input: string, minimum: number): number | null {
  const raw = input.trim();
  if (!/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= minimum && value <= 50 ? value : null;
}

export function reservationRateInput(input: string): number | null {
  const raw = input.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value <= 1e9 ? value : null;
}
