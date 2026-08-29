const PAYMENT_TOLERANCE = 0.01;

export function classifyGuestPayment(amount, outstandingBalance) {
  const numericAmount = Number(amount);
  const numericBalance = Number(outstandingBalance);

  if (!Number.isFinite(numericAmount) || numericAmount <= 0) return 'interim';
  if (!Number.isFinite(numericBalance) || numericBalance <= 0) return 'interim';

  return numericAmount >= numericBalance - PAYMENT_TOLERANCE ? 'final' : 'interim';
}

export function guestPaymentClassificationLabel(amount, outstandingBalance) {
  const numericAmount = Number(amount);
  if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
    return 'Tutar girildiğinde ödeme türü otomatik belirlenecek';
  }
  return classifyGuestPayment(amount, outstandingBalance) === 'final'
    ? 'Tam ödeme — bakiye kapanacak'
    : 'Kısmi ödeme — kalan bakiye açık kalacak';
}
