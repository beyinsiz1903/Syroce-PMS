// Keep an uncertain receivable reassignment stable across retry and reload.
export async function submitCariAgencyIntent(tenantId, sourceId, payload, send) {
  if (!tenantId || !sourceId) throw new Error('Cari aktarım için tesis ve kaynak hesap doğrulanamadı.');
  const key = `pms:cari-agency-intent:v1:${tenantId}:${sourceId}`;
  const fingerprint = JSON.stringify(payload);
  let intent;
  try {
    intent = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (intent && intent.fingerprint !== fingerprint) {
      throw new Error('Önceki cari aktarımın sonucu belirsiz. Önce aynı bilgilerle tekrar deneyin ve hesapları yenileyin.');
    }
    if (!intent) {
      intent = { fingerprint, body: { ...payload, request_id: crypto.randomUUID() } };
      sessionStorage.setItem(key, JSON.stringify(intent));
    }
  } catch (error) {
    throw new Error(error.message || 'Güvenli işlem anahtarı saklanamadı; aktarım gönderilmedi.');
  }
  let result;
  try {
    result = await send(intent.body);
  } catch (error) {
    if ([400, 401, 403, 404, 422].includes(error.response?.status)) sessionStorage.removeItem(key);
    throw error;
  }
  try { sessionStorage.removeItem(key); } catch { /* retain UUID for safe replay */ }
  return result;
}
