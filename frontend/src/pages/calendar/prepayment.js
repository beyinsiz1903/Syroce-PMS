const normalizeCurrency = (currency) => String(currency || 'TRY').toUpperCase() === 'TL'
  ? 'TRY'
  : String(currency || 'TRY').toUpperCase();

const isRetryable = (error) => !error?.response || Number(error.response?.status || 0) >= 500;

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
  try {
    response = await client.post(`/pms/reservations/${bookingId}/record-payment`, payload);
  } catch (error) {
    if (!isRetryable(error)) throw error;
    // Aynı referans backend'de idempotenttir. Geçici ağ/5xx hatasında bir kez
    // tekrar deneyerek ödeme yazıldığı halde istemcinin cevabı kaçırdığı
    // belirsiz durumu güvenle kapatırız.
    response = await client.post(`/pms/reservations/${bookingId}/record-payment`, payload);
  }

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

