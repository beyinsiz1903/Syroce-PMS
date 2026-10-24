// Mirror reporting_financials.py: ledger settlement is not always collection.
const invalid = new Set(['void', 'voided', 'failed', 'cancelled', 'canceled', 'rejected', 'pending', 'processing', 'initiated', 'authorized', 'expired', 'declined', 'requires_action']);
const nonCash = new Set(['discount', 'city_ledger', 'direct_bill', 'complimentary', 'correction', 'ar', 'security_deposit_application']);
export const paymentMethod = row => String(row.payment_method || row.method || '').trim().toLowerCase();
export const isEffectivePayment = row => !row.voided && !invalid.has(String(row.status || 'paid').trim().toLowerCase());
export const isNonCashPayment = row => nonCash.has(paymentMethod(row));
export const signedFolioPayment = row => {
  if (!isEffectivePayment(row)) return 0;
  const amount = Number(row.amount || 0);
  if (!Number.isFinite(amount)) return 0;
  return String(row.payment_type || '').trim().toLowerCase() === 'refund' && amount > 0 ? -amount : amount;
};
export const collectionPayment = row => isNonCashPayment(row) ? 0 : signedFolioPayment(row);
export const folioPaymentLabel = row => ({
  cash: 'Nakit', card: 'Kredi kartı', bank_transfer: 'Havale / EFT', online: 'Online ödeme', agency: 'Acente',
  discount: 'İkram / indirim (tahsilat değil)', complimentary: 'İkram (tahsilat değil)', correction: 'Finansal düzeltme (tahsilat değil)',
  city_ledger: 'Cari aktarım (tahsilat değil)', direct_bill: 'Cari aktarım (tahsilat değil)', ar: 'Cari aktarım (tahsilat değil)',
  security_deposit_application: 'Güvence mahsubu (yeni tahsilat değil)',
}[paymentMethod(row)] || paymentMethod(row) || '—');
