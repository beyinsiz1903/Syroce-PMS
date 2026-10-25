// Retain the exact submitted body across timeout, retry and page reload.
// A changed form must not silently create a second uncertain receipt/refund.
export async function submitDepositIntent(bookingId, action, payload, send) {
  const key = `pms:deposit-intent:v1:${bookingId}:${action}`;
  const fingerprint = JSON.stringify(payload);
  let intent;
  try {
    intent = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (intent && intent.fingerprint !== fingerprint) {
      throw new Error('Önceki depozito işleminin sonucu belirsiz. Önce aynı bilgilerle tekrar deneyin ve kayıtları yenileyin.');
    }
    if (!intent) {
      intent = { fingerprint, body: { ...payload, request_id: crypto.randomUUID() } };
      sessionStorage.setItem(key, JSON.stringify(intent));
    }
  } catch (error) {
    throw new Error(error.message || 'Güvenli işlem anahtarı saklanamadı; işlem gönderilmedi.');
  }
  let result;
  try {
    result = await send(intent.body);
  } catch (error) {
    // These responses prove validation/authorization failed before a write.
    // 409/5xx/network loss remain uncertain and must retain the original UUID.
    if ([400, 401, 403, 404, 422].includes(error.response?.status)) sessionStorage.removeItem(key);
    throw error;
  }
  // A successful payment must not look failed merely because cleanup failed.
  // Keeping the UUID is safer than minting a new one after such a failure.
  try { sessionStorage.removeItem(key); } catch { /* retained for safe replay */ }
  return result;
}
