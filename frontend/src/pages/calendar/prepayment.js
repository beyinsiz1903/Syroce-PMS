const normalizeCurrency = (currency) => String(currency || 'TRY').toUpperCase() === 'TL'
  ? 'TRY'
  : String(currency || 'TRY').toUpperCase();

// Reservation creation and the first folio write are two separate requests.
// The payment carries a stable reference, so retrying is safe: the backend
// returns the original payment for a matching retry instead of crediting the
// guest twice. A short 404 can occur while a just-created reservation is
// becoming visible behind a rolling API deployment; it must not leave the
// operator with a confirmed reservation but an unrecorded prepayment.
const isRetryable = (error) => {
  const status = Number(error?.response?.status || 0);
  return !error?.response || status === 404 || status >= 500;
};

const PREPAYMENT_MAX_ATTEMPTS = 3;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const recordInitialPrepayment = async ({
  client,
  bookingId,
  amount,
  method,
  reference,
  currency,
  idempotencyKey,
}) => {
  if (!bookingId) throw new Error('Oluşturulan rezervasyon kimliği alınamadı');

  const normalizedCurrency = normalizeCurrency(currency);
  const paymentReference = String(reference || '').trim()
    || `reservation-prepayment:${bookingId}:${idempotencyKey}`;
  const payload = {
    amount,
    method,
    payment_type: 'prepayment',
    reference: paymentReference,
    notes: 'Rezervasyon oluşturulurken alınan ön ödeme',
    currency: normalizedCurrency,
    received_currency: normalizedCurrency,
    received_amount: amount,
    exchange_rate: 1,
  };

  let response;
  let lastError;
  for (let attempt = 1; attempt <= PREPAYMENT_MAX_ATTEMPTS; attempt += 1) {
    try {
      response = await client.post(`/pms/reservations/${bookingId}/record-payment`, payload);
      break;
    } catch (error) {
      lastError = error;
      if (!isRetryable(error) || attempt === PREPAYMENT_MAX_ATTEMPTS) throw error;
      // A tiny backoff lets a just-created booking become visible to the
      // payment route during a rolling deployment without blocking the UI.
      await wait(200 * attempt);
    }
  }

  if (!response) throw lastError || new Error('Ön ödeme kaydedilemedi');

  const payment = response?.data?.payment;
  if (
    !payment?.id
    || payment.booking_id !== bookingId
    || String(payment.payment_type || '').toLowerCase() !== 'prepayment'
    || Math.round(Number(payment.amount || 0) * 100) !== Math.round(Number(amount) * 100)
  ) {
    throw new Error('Ön ödeme sunucu tarafından doğrulanamadı');
  }
  return payment;
};
