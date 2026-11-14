import { exelyReservationDetails } from '@/utils/exelyReservation';

// Presentation only: amounts come from the server, never from UI arithmetic.
const amount = (value) => {
  if (!['number', 'string'].includes(typeof value) || String(value).trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export function reservationPaymentSummary(summary, booking) {
  const totalDue = amount(summary?.reservation_total_due ?? summary?.balance);
  const folioBalance = amount(summary?.folio_balance ?? summary?.balance);
  const pendingRoomAmount = amount(summary?.unposted_room_amount);
  const needsReconciliation = Boolean(summary?.pricing_reconciliation_required);
  const difference = amount(summary?.pricing_reconciliation_difference);
  const kind = needsReconciliation ? 'reconciliation' : totalDue == null ? 'unknown' : totalDue > 0.01 ? 'due' : totalDue < -0.01 ? 'credit' : 'settled';
  const isExely = Boolean(exelyReservationDetails(booking || {}));
  return {
    totalDue,
    folioBalance,
    pendingRoomAmount,
    pmsOnly: isExely,
    kind,
    label: kind === 'reconciliation' ? 'Fiyat / tahakkuk farkı' : kind === 'unknown' ? 'Ödeme bilgisi alınamadı' : isExely ? (kind === 'credit' ? 'PMS kayıt alacağı' : 'PMS kayıt bakiyesi') : kind === 'credit' ? 'Misafir alacağı' : 'Toplam kalan ödeme',
    displayAmount: kind === 'reconciliation' ? difference : kind === 'credit' ? Math.abs(totalDue) : totalDue,
    description: kind === 'reconciliation' ? 'Ödeme almadan önce fiyat ve kayıtları kontrol edin.'
      : kind === 'unknown' ? 'Tutarı doğrulamak için rezervasyonu yenileyin.'
      : isExely ? 'Exely ödemeleri ve hizmetleri ayrı izlenir. Tahsilat öncesi iki hesabı birlikte kontrol edin.'
      : kind === 'credit' ? 'Konaklamanın tamamı için misafir lehine kalan tutar.'
      : kind === 'due' ? 'Tüm konaklama ve ekstralar dahil kalan tutar.' : 'Konaklamanın tamamı için kalan ödeme yok.',
    hasAllocatedPrepayment: pendingRoomAmount > 0.01 && totalDue != null && totalDue <= 0.01 && folioBalance < -0.01,
  };
}

// The snapshot covers all provider rooms and services; it is not a PMS receipt
// or a per-room payment allocation. Never combine it with local ledger totals.
export function reservationDisplaySummary(summary, booking) {
  const local = reservationPaymentSummary(summary, booking);
  if (!exelyReservationDetails(booking || {}) || local.kind === 'reconciliation') return local;
  const snapshot = booking?.provider_prepayment;
  const currency = typeof snapshot?.booking_currency === 'string' ? snapshot.booking_currency.trim() : '';
  const candidate = snapshot?.schema_version === 1 && currency ? amount(snapshot.remaining_amount) : null;
  const remaining = candidate != null && candidate >= 0 ? candidate : null;
  return {
    kind: remaining == null ? 'unknown' : remaining > 0.01 ? 'due' : 'settled',
    label: remaining == null ? 'Exely bakiyesi doğrulanamadı' : 'Exely’de kalan tutar',
    displayAmount: remaining,
    currency,
    providerScope: true,
    description: remaining == null
      ? 'Exely ön ödeme bilgilerini kontrol edin. PMS kayıt bakiyesi ayrıca gösterilir.'
      : 'Hizmetler dahil Exely rezervasyonunun tamamı içindir. Otelde eklenen harcamalar ayrı izlenir.',
  };
}
