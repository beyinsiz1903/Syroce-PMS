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
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (detail && typeof detail === 'object') {
    const nested = detail.message || detail.error || detail.msg;
    if (typeof nested === 'string' && nested.trim()) return nested.trim();
  }
  if (typeof error?.message === 'string' && error.message.trim()) return error.message.trim();
  return fallback;
}
