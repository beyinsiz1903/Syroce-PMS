export type ReservationTone = 'success' | 'warning' | 'info' | 'default' | 'danger';

const STATUS_LABELS: Record<string, string> = {
  confirmed: 'Onaylı',
  guaranteed: 'Garantili',
  checked_in: 'Giriş yaptı',
  checked_out: 'Çıkış yaptı',
  cancelled: 'İptal',
  canceled: 'İptal',
  no_show: 'Gelmedi',
};

export function reservationStatusLabel(status: unknown): string {
  const key = String(status ?? '').toLowerCase();
  return STATUS_LABELS[key] || String(status ?? '—');
}

export function reservationStatusTone(status: unknown): ReservationTone {
  switch (String(status ?? '').toLowerCase()) {
    case 'checked_in':
      return 'success';
    case 'confirmed':
    case 'guaranteed':
      return 'info';
    case 'checked_out':
      return 'default';
    case 'cancelled':
    case 'canceled':
    case 'no_show':
      return 'danger';
    default:
      return 'warning';
  }
}

type MoneyInput = {
  bookingTotal?: unknown;
  bookingPaid?: unknown;
  bookingBalance?: unknown;
  rateBase?: unknown;
  rateTotal?: unknown;
  folioBalance?: unknown;
  charges?: Array<{ amount?: unknown; total?: unknown }>;
  payments?: Array<{ amount?: unknown }>;
};

function finite(value: unknown): number | undefined {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function positive(value: unknown): number | undefined {
  const n = finite(value);
  return n !== undefined && n > 0 ? n : undefined;
}

export function reservationMoneySummary(input: MoneyInput): {
  total?: number;
  paid?: number;
  balance?: number;
} {
  const chargeValues = (input.charges ?? [])
    .map((charge) => finite(charge.amount ?? charge.total))
    .filter((value): value is number => value !== undefined);
  const paymentValues = (input.payments ?? [])
    .map((payment) => finite(payment.amount))
    .filter((value): value is number => value !== undefined);
  const chargeTotal = chargeValues.length ? chargeValues.reduce((sum, value) => sum + value, 0) : undefined;
  const paymentTotal = paymentValues.length ? paymentValues.reduce((sum, value) => sum + value, 0) : undefined;

  // Folio movements are authoritative. Some legacy bookings contain total=0
  // while their rate breakdown still carries the actual accommodation price.
  const total =
    positive(chargeTotal) ??
    positive(input.rateTotal) ??
    positive(input.bookingTotal) ??
    positive(input.rateBase) ??
    finite(input.bookingTotal);
  const paid = paymentTotal ?? finite(input.bookingPaid);
  const balance =
    finite(input.folioBalance) ??
    finite(input.bookingBalance) ??
    (total !== undefined && paid !== undefined ? total - paid : undefined);

  return { total, paid, balance };
}
