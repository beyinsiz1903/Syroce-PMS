export function formatAgencyMoney(value, currency) {
  if (!currency || currency === 'UNKNOWN') return `${Number(value || 0).toLocaleString('tr-TR')} (para birimi eksik)`;
  try { return new Intl.NumberFormat('tr-TR', { style: 'currency', currency }).format(Number(value || 0)); }
  catch { return `${Number(value || 0).toLocaleString('tr-TR')} (${currency})`; }
}
export function currencyTotalsText(rows = [], field) {
  const totals = new Map();
  for (const row of rows) {
    const currency = row.currency || 'UNKNOWN';
    totals.set(currency, (totals.get(currency) || 0) + Number(row[field] || 0));
  }
  return [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([currency, value]) => formatAgencyMoney(value, currency)).join(' · ') || '—';
}
