export function depositGuestLabel(deposit = {}) {
  return String(deposit.guest_name || '').trim() || 'Misafir bilgisi eksik';
}

export function formatDepositDate(value, locale = 'tr-TR') {
  if (!value) return 'Tarih bilgisi yok';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return 'Geçersiz tarih';
  return new Intl.DateTimeFormat(locale || 'tr-TR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}
