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
  const key = String(status ?? '').trim().toLowerCase();
  return STATUS_LABELS[key] || key || 'Durum belirtilmemiş';
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
  summaryTotal?: unknown;
  summaryBalance?: unknown;
  bookingTotal?: unknown;
  bookingCollected?: unknown;
  bookingBalance?: unknown;
  rateBase?: unknown;
  rateTotal?: unknown;
  folioBalance?: unknown;
  currency?: string;
  charges?: Array<{ amount?: unknown; total?: unknown; voided?: boolean }>;
  payments?: PaymentMovement[];
};

export function finiteMoney(value: unknown): number | undefined {
  if (value === null || value === undefined || typeof value === 'boolean') return undefined;
  if (typeof value !== 'number' && typeof value !== 'string') return undefined;
  if (typeof value === 'string' && !value.trim()) return undefined;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : undefined;
}

export function reservationCurrency(value: unknown): string | undefined {
  const code = typeof value === 'string' ? value.trim().toUpperCase() : '';
  return /^[A-Z]{3}$/.test(code) ? code : undefined;
}

export function reservationAmountLabel(amount: unknown, currency?: string): string {
  const value = finiteMoney(amount);
  if (value === undefined) return 'Bilgi yok';
  const code = reservationCurrency(currency);
  if (!code) return `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(value)} · para birimi belirtilmemiş`;
  try {
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: code }).format(value);
  } catch {
    return `${value.toFixed(2)} ${code}`;
  }
}

type PaymentMovement = {
  amount?: unknown;
  method?: string;
  payment_type?: string;
  status?: string;
  voided?: boolean;
  currency?: string;
};

const INVALID_PAYMENT_STATUSES = new Set(['failed', 'cancelled', 'canceled', 'rejected', 'declined', 'void', 'voided', 'pending', 'processing', 'initiated', 'authorized', 'expired', 'requires_action']);
const NON_COLLECTION_METHODS = new Set(['city_ledger', 'direct_bill', 'ar', 'discount', 'complimentary', 'correction', 'security_deposit_application', 'gift_card_redemption', 'wallet', 'loyalty_redemption', 'barter', 'write_off']);

// Mirrors core/booking_payment_state.py: transfers/discounts are not cash
// collections, and a refund reduces the collected amount. Never add different
// currencies without an API conversion amount.
export function reservationCollectedAmount(payments: PaymentMovement[] | undefined, currency?: string): number | undefined {
  if (!Array.isArray(payments)) return undefined;
  let total = 0;
  for (const payment of payments) {
    if (payment.voided || INVALID_PAYMENT_STATUSES.has(String(payment.status || '').toLowerCase())) continue;
    if (NON_COLLECTION_METHODS.has(String(payment.method || '').trim().toLowerCase()) || payment.payment_type === 'city_ledger_transfer') continue;
    const amount = finiteMoney(payment.amount);
    if (amount === undefined) return undefined;
    const movementCurrency = reservationCurrency(payment.currency);
    if (movementCurrency && (!currency || movementCurrency !== currency)) return undefined;
    total += payment.payment_type === 'refund' || payment.status === 'refunded' ? -Math.abs(amount) : amount;
  }
  return Math.max(0, Math.round(total * 100) / 100);
}

const SOURCE_LABELS: Record<string, string> = {
  direct: 'Doğrudan', direct_booking: 'Doğrudan', website: 'Web sitesi', web: 'Web sitesi',
  phone: 'Telefon', walk_in: 'Walk-in', walkin: 'Walk-in', ota: 'OTA',
  corporate: 'Kurumsal', agency: 'Acente', acente: 'Acente', booking_com: 'Booking.com',
  'booking.com': 'Booking.com', booking: 'Booking.com', expedia: 'Expedia',
};

export function reservationSourceLabel(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return 'Kaynak belirtilmemiş';
  const source = value.trim();
  return SOURCE_LABELS[source.toLowerCase()] || source;
}

export function paymentMethodLabel(method: unknown): string {
  const key = String(method ?? '').toLowerCase();
  return ({ cash: 'Nakit', card: 'Kart', bank_transfer: 'Banka havalesi', transfer: 'Banka havalesi', online: 'Online', city_ledger: 'Cari hesaba aktarım', discount: 'İndirim',
    gift_card_redemption: 'Hediye kartı mahsubu', wallet: 'Cüzdan mahsubu', loyalty_redemption: 'Sadakat puanı mahsubu',
    barter: 'Barter — tahsilat değil', write_off: 'Alacaktan silme — tahsilat değil', security_deposit_application: 'Güvence mahsubu' } as Record<string, string>)[key] || key || 'Yöntem belirtilmemiş';
}

export function paymentStatusLabel(payment: PaymentMovement): string {
  if (payment.voided) return 'İptal edildi';
  const key = String(payment.status ?? '').toLowerCase();
  const statusLabel = ({ paid: 'Kaydedildi', pending: 'Bekliyor', partial: 'Kısmi', failed: 'Başarısız', declined: 'Reddedildi', rejected: 'Reddedildi', voided: 'İptal edildi', void: 'İptal edildi', cancelled: 'İptal edildi', canceled: 'İptal edildi' } as Record<string, string>)[key];
  if (INVALID_PAYMENT_STATUSES.has(key)) return statusLabel || key;
  if (payment.payment_type === 'refund' || key === 'refunded') return 'İade';
  return statusLabel || key || 'Durum belirtilmemiş';
}

// An aggregate reservation balance must never be posted to a guest folio if
// the API shows a separate agency/company payer or ambiguous folio ownership.
export function hasSeparatePayer(input: {
  company_id?: string; agency_id?: string; agency_name?: string; payment_model?: string;
  channel?: string; source_channel?: string; ota_channel?: string;
  folios?: Array<{ folio_type?: string; payor_type?: string; status?: string }>;
}): boolean {
  if (input.company_id || input.agency_id || input.agency_name) return true;
  if (['agency', 'acente', 'corporate', 'marketplace'].includes((input.source_channel || input.channel || '').toLowerCase())) return true;
  if (input.ota_channel && !input.payment_model) return true;
  if (input.payment_model && !['hotel_collect', 'pay_at_hotel'].includes(input.payment_model.toLowerCase())) return true;
  if (!Array.isArray(input.folios)) return true;
  const open = input.folios.filter((folio) => folio.status === 'open');
  if (open.length > 1) return true;
  return input.folios.some((folio) =>
    !folio.folio_type || folio.folio_type !== 'guest' ||
    (!!folio.payor_type && folio.payor_type !== 'guest'),
  );
}

export function reservationMoneySummary(input: MoneyInput): {
  total?: number;
  paid?: number;
  balance?: number;
} {
  const chargeValues = (input.charges ?? [])
    .filter((charge) => !charge.voided)
    .map((charge) => finiteMoney(charge.total ?? charge.amount))
    .filter((value): value is number => value !== undefined);
  const chargeTotal = chargeValues.length ? chargeValues.reduce((sum, value) => sum + value, 0) : undefined;
  const paymentTotal = reservationCollectedAmount(input.payments, input.currency);

  // The API's full-stay summary includes unposted nights. A few posted folio
  // rows must not replace the confirmed stay price; base_rate may be nightly.
  const total =
    finiteMoney(input.summaryTotal) ??
    finiteMoney(input.rateTotal) ??
    finiteMoney(input.bookingTotal) ??
    chargeTotal;
  const paid = input.payments !== undefined ? paymentTotal : finiteMoney(input.bookingCollected);
  const balance =
    finiteMoney(input.summaryBalance) ??
    finiteMoney(input.bookingBalance) ??
    finiteMoney(input.folioBalance);

  return { total, paid, balance };
}
