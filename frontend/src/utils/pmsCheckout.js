export function normalizeCheckoutResponse(response) {
  const data = response?.data && typeof response.data === 'object' ? response.data : {};
  const totalBalance = Number(data.total_balance);
  const foliosClosed = Number(data.folios_closed);

  return {
    message: typeof data.message === 'string' && data.message.trim()
      ? data.message.trim()
      : 'Çıkış işlemi tamamlandı',
    totalBalance: Number.isFinite(totalBalance) ? totalBalance : 0,
    foliosClosed: Number.isFinite(foliosClosed) ? foliosClosed : 0,
  };
}

export function getCheckoutErrorMessage(error, fallback = 'Çıkış yapılamadı') {
  const detail = error?.response?.data?.detail;
  const code = detail && typeof detail === 'object'
    ? String(detail.code || detail.error_code || '').trim().toUpperCase()
    : '';
  const rawMessage = typeof detail === 'string'
    ? detail.trim()
    : detail && typeof detail === 'object'
      ? String(detail.message || detail.error || detail.msg || '').trim()
      : '';

  if (
    code === 'RESERVATION_EDIT_LOCK_REQUIRED'
    || /active reservation edit lock required/i.test(rawMessage)
  ) {
    return 'Rezervasyon işlem kilidi alınamadı. Lütfen tekrar deneyin.';
  }
  if (
    code === 'RESERVATION_EDIT_LOCK_LOST'
    || /reservation edit lock (?:expired|lost)|belongs to another view/i.test(rawMessage)
  ) {
    return 'Rezervasyon işlem kilidinin süresi doldu veya kayıt başka bir ekranda kullanılıyor. Lütfen tekrar deneyin.';
  }

  if (rawMessage) return rawMessage;
  if (detail && typeof detail === 'object') {
    const nested = detail.message || detail.error || detail.msg;
    if (typeof nested === 'string' && nested.trim()) return nested.trim();
  }
  if (typeof error?.message === 'string' && error.message.trim()) return error.message.trim();
  return fallback;
}
