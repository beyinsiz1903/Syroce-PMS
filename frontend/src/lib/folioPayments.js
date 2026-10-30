// Mirror reporting_financials.py: ledger settlement is not always collection.
const invalid = new Set(['void', 'voided', 'failed', 'cancelled', 'canceled', 'rejected', 'pending', 'processing', 'initiated', 'authorized', 'expired', 'declined', 'requires_action']);
const nonCash = new Set(['discount', 'city_ledger', 'direct_bill', 'complimentary', 'correction', 'ar', 'security_deposit_application', 'gift_card_redemption', 'wallet', 'loyalty_redemption', 'barter', 'write_off']);
export const paymentMethod = row => String(row.payment_method || row.method || '').trim().toLowerCase();
export const isEffectivePayment = row => !row.voided && !invalid.has(String(row.status || 'paid').trim().toLowerCase());
export const isNonCashPayment = row => nonCash.has(paymentMethod(row));
export const isRefundPayment = row => String(row.payment_type || '').trim().toLowerCase() === 'refund'
  || String(row.status || '').trim().toLowerCase() === 'refunded' || Number(row.amount || 0) < 0;
export const signedFolioPayment = row => {
  if (!isEffectivePayment(row)) return 0;
  const amount = Number(row.amount || 0);
  if (!Number.isFinite(amount)) return 0;
  return isRefundPayment(row) ? -Math.abs(amount) : amount;
};
export const collectionPayment = row => isNonCashPayment(row) ? 0 : signedFolioPayment(row);
// Display the last actual receipt, not a later concession, AR transfer or refund.
// Sort a copy: payment history order and ledger values must remain untouched.
export const latestCollectionPayment = payments => {
  const receipts = (Array.isArray(payments) ? payments : [])
    .filter(row => row && paymentMethod(row) && collectionPayment(row) > 0)
    .sort((a, b) => (Date.parse(a.processed_at || a.paid_at || a.created_at) || 0)
      - (Date.parse(b.processed_at || b.paid_at || b.created_at) || 0));
  return receipts[receipts.length - 1] || null;
};
export const folioPaymentLabel = row => ({
  cash: 'Nakit', card: 'Kredi kartı', credit_card: 'Kredi kartı', bank_transfer: 'Havale / EFT', online: 'Online ödeme', agency: 'Acente',
  discount: 'İkram / indirim (tahsilat değil)', complimentary: 'İkram (tahsilat değil)', correction: 'Finansal düzeltme (tahsilat değil)',
  city_ledger: 'Cari aktarım (tahsilat değil)', direct_bill: 'Cari aktarım (tahsilat değil)', ar: 'Cari aktarım (tahsilat değil)',
  security_deposit_application: 'Güvence mahsubu (yeni tahsilat değil)',
  gift_card_redemption: 'Hediye kartı mahsubu', wallet: 'Cüzdan mahsubu', loyalty_redemption: 'Sadakat puanı mahsubu',
  barter: 'Barter (tahsilat değil)', write_off: 'Alacaktan silme (tahsilat değil)',
}[paymentMethod(row)] || paymentMethod(row) || '—');

const timelinePayment = event => ({ ...event, method: event.method || event.category,
  payment_type: event.payment_type || (event.type === 'refund' ? 'refund' : 'payment') });
export const folioEventCategoryLabel = event => event.type === 'charge' ? ({
  room: 'Konaklama', food: 'Yiyecek', beverage: 'İçecek', f_and_b: 'Yiyecek ve içecek', spa: 'SPA',
  minibar: 'Minibar', laundry: 'Çamaşırhane', tax: 'Vergi', city_tax: 'Konaklama vergisi', other: 'Diğer',
  room_service: 'Oda servisi', concierge: 'Concierge', transfer: 'Transfer', parking: 'Otopark', mice: 'Toplantı ve etkinlik', activity: 'Aktivite', function_space: 'Salon kiralama', upsell: 'Ek hizmet teklifi',
}[event.category] || event.category || 'Diğer') : folioPaymentLabel(timelinePayment(event));
export const folioEventBalanceEffect = event => {
  if (event.balance_effect != null && Number.isFinite(Number(event.balance_effect))) return Number(event.balance_effect);
  if (event.type === 'charge') return event.voided ? 0 : Number(event.amount || 0);
  return -signedFolioPayment(timelinePayment(event));
};
export const folioEventTitle = event => {
  if (event.type === 'charge') return /^room charge/i.test(event.description || '') ? 'Konaklama ücreti' : event.description || 'Folyo işlemi';
  const payment = timelinePayment(event);
  if (isNonCashPayment(payment)) return `${folioPaymentLabel(payment)}${event.type === 'refund' ? ' · ters kayıt' : ''}`;
  if (event.billing_settlement_id) return event.type === 'refund' ? 'Çek tahsil ters kaydı' : 'Çek tahsilatı (harici banka kaydı)';
  return event.type === 'refund' ? 'Ödeme iadesi' : `${paymentMethod(payment) ? folioPaymentLabel(payment) : 'Ödeme'} tahsilatı`;
};
export const canVoidFolioEvent = event => event.type === 'payment' && event.can_void !== false
  && signedFolioPayment(timelinePayment(event)) > 0 && !isNonCashPayment(timelinePayment(event))
  && !['billing_settlement_id', 'security_fund_id', 'concession_id', 'provider_ref', 'mice_event_id'].some(key => event[key]);
