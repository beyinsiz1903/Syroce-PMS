import { folioPaymentLabel } from './folioPayments';

// Use the same settlement vocabulary as the guest account, without changing
// the source method codes or treating non-cash settlement as new collection.
export const reportPaymentMethodLabel = method => {
  const code = String(method || '').trim().toLowerCase();
  if (code === 'debit_card') return 'Banka kartı';
  if (code === 'cheque' || code === 'check') return 'Çek';
  return folioPaymentLabel({ method: code });
};
