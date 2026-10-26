// Presentation only: amounts come from the server, never from UI arithmetic.
const amount = (value) => {
  if (!['number', 'string'].includes(typeof value) || String(value).trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export function reservationPaymentSummary(summary) {
  const totalDue = amount(summary?.reservation_total_due ?? summary?.balance);
  const folioBalance = amount(summary?.folio_balance ?? summary?.balance);
  const pendingRoomAmount = amount(summary?.unposted_room_amount);
  const needsReconciliation = Boolean(summary?.pricing_reconciliation_required);
  const difference = amount(summary?.pricing_reconciliation_difference);
  const kind = needsReconciliation ? 'reconciliation' : totalDue == null ? 'unknown' : totalDue > 0.01 ? 'due' : totalDue < -0.01 ? 'credit' : 'settled';
  return {
    totalDue,
    folioBalance,
    pendingRoomAmount,
    kind,
    label: kind === 'reconciliation' ? 'Fiyat / tahakkuk farkı' : kind === 'unknown' ? 'Ödeme bilgisi alınamadı' : kind === 'credit' ? 'Misafir alacağı' : 'Toplam kalan ödeme',
    displayAmount: kind === 'reconciliation' ? difference : kind === 'credit' ? Math.abs(totalDue) : totalDue,
    description: kind === 'reconciliation' ? 'Ödeme almadan önce fiyat ve kayıtları kontrol edin.'
      : kind === 'unknown' ? 'Tutarı doğrulamak için rezervasyonu yenileyin.'
      : kind === 'credit' ? 'Konaklamanın tamamı için misafir lehine kalan tutar.'
      : kind === 'due' ? 'Tüm konaklama ve ekstralar dahil kalan tutar.' : 'Konaklamanın tamamı için kalan ödeme yok.',
    hasAllocatedPrepayment: pendingRoomAmount > 0.01 && totalDue != null && totalDue <= 0.01 && folioBalance < -0.01,
  };
}
