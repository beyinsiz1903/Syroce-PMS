// Only order lines are queued. No guest data, tokens, signatures or payments.
export const queueKey = scope => `pos-orders-v1:${encodeURIComponent(scope.tenant_id)}:${encodeURIComponent(scope.actor_id)}`;
export function readQueue(scope, storage = localStorage) {
  const prefix = queueKey(scope) + ':';
  const rows = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (!key?.startsWith(prefix)) continue;
    const row = JSON.parse(storage.getItem(key));
    if (!row?.id || !row.body || !/^\/pos\/v2\/orders(?:\/[^/]+\/items)?$/.test(row.path)) {
      throw new Error('Sipariş kuyruğu okunamadı. Cihaz verilerini silmeden destek alın.');
    }
    rows.push(row);
  }
  return rows.sort((a, b) => a.created_at.localeCompare(b.created_at));
}
function saveRow(scope, row, storage) {
  // One atomic storage key per operation: different tabs cannot overwrite
  // each other's queues with a stale read/modify/write of a shared array.
  storage.setItem(queueKey(scope) + ':' + row.id, JSON.stringify(row));
}
export function removeQueuedOrder(scope, id, storage = localStorage) {
  storage.removeItem(queueKey(scope) + ':' + id);
}
export function enqueueOrder(scope, path, body, storage = localStorage) {
  const rows = readQueue(scope, storage);
  const prior = rows.find(row => row.id === body.idempotency_key);
  if (prior) {
    if (prior.path !== path || JSON.stringify(prior.body) !== JSON.stringify(body)) {
      throw new Error('Önce bekleyen siparişi çözümleyin; aynı anahtarla değişik sipariş gönderilemez.');
    }
    return prior;
  }
  if (rows.length >= 100) throw new Error('Kuyruk dolu. Önce bekleyen siparişleri gönderin.');
  const row = { id: body.idempotency_key, path, body, state: 'pending', created_at: new Date().toISOString() };
  saveRow(scope, row, storage);
  return row;
}
export async function sendQueuedOrder(scope, id, api, storage = localStorage) {
  // Verify the active server identity before EVERY replay, including after login changes.
  const identity = (await api.get('/pos/v2/session')).data;
  if (queueKey(identity) !== queueKey(scope)) throw new Error('Oturum değişti. Bu kuyruk başka kullanıcıya ait.');
  const row = readQueue(scope, storage).find(item => item.id === id);
  if (!row) return null;
  try {
    const response = await api.post(row.path, row.body);
    removeQueuedOrder(scope, id, storage);
    return response;
  } catch (error) {
    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;
    saveRow(scope, {
      ...row, state: status >= 400 && status < 500 ? 'conflict' : 'pending',
      error: typeof detail === 'string' ? detail : detail?.message || 'Sunucu onayı alınamadı. Aynı sipariş güvenli biçimde tekrar gönderilecek.',
    }, storage);
    throw error;
  }
}
