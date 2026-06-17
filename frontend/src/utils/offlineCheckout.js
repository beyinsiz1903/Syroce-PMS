/**
 * Offline Check-out — çevrimdışı çıkış + otomatik eşitleme. SADECE sıfır/kapalı
 * bakiyeli folyolar çevrimdışı kuyruğa alınır. ÖDEME ASLA çevrimdışına alınmaz:
 * açık bakiye varsa ne istemci kuyruğa alır ne de backend replay'de kabul eder
 * (402 OUTSTANDING_BALANCE). offlineCheckin.js deseninin kardeşi.
 *
 * Akış:
 *  - performCheckout(): bakiye > 0.01 ise ASLA kuyruğa almaz ({ blocked: true }).
 *    Sıfır bakiyede önce çevrimiçi dener; ağ hatası → kuyruğa yazar; gerçek
 *    sunucu/iş hatası (402 vb.) çağırana fırlatılır.
 *  - processQueuedCheckouts(): sayfa bağlamı yedek eşitleyici. Idempotent POST'a
 *    replay eder.
 *
 * Anahtar `checkout-<bookingId>` deterministiktir → çift çıkış / çift folyo
 * kapanışını önler. Replay'de "zaten çıkış yapılmış" (400) idempotent BAŞARI
 * sayılır (çıkış olmuş, yanıt kaybolmuş); 402 ise (kuyruğa alındıktan sonra
 * eklenen ücret) çakışma olarak operatöre yüzeye çıkar.
 */
import axios from 'axios';
import {
  enqueueCheckout,
  listQueuedCheckouts,
  removeQueuedCheckout,
  updateQueuedCheckout,
} from '@/utils/offlineQueueDB';

export const CHECKOUT_SYNC_TAG = 'sync-checkouts';

// Açık bakiye eşiği — bunun üstü çevrimdışı çıkışa UYGUN DEĞİL.
export const OPEN_BALANCE_THRESHOLD = 0.01;

// Geçici (401/5xx) hatalar bu sayıya ulaşınca artık sonsuza dek tekrar
// denenmez; operatör müdahalesi için çakışmaya dönüştürülür.
export const MAX_CHECKOUT_ATTEMPTS = 8;
// Bu yaştan eski bekleyen çıkışlar "uzun süredir bekliyor" uyarısı tetikler.
export const STALE_CHECKOUT_AGE_MS = 5 * 60 * 1000;

// Sayfa içi dinleyicilerin (status bar) anında güncellenmesi için yayın.
export const CHECKOUT_QUEUE_EVENT = 'syroce:checkout-queue-changed';

function emitQueueChanged(detail = {}) {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(CHECKOUT_QUEUE_EVENT, { detail }));
  } catch {
    // CustomEvent yoksa sessizce geç.
  }
}

// Sunucudan HTTP yanıtı YOKSA (ağ/zaman aşımı) çevrimdışı kabul edilir.
function isNetworkError(error) {
  return !error || !error.response;
}

// Backend "Guest already checked out" (400) → idempotent başarı eşleşmesi.
function isAlreadyCheckedOut(error) {
  if (error?.response?.status !== 400) return false;
  const detail = error.response?.data?.detail;
  const text = typeof detail === 'string' ? detail : detail?.message || '';
  return /already checked out/i.test(text);
}

export function checkoutKeyForBooking(bookingId) {
  return `checkout-${bookingId}`;
}

function checkoutEndpoint(bookingId) {
  return `/frontdesk/checkout/${bookingId}?auto_close_folios=true`;
}

function hasOpenBalance(balance) {
  const num = Number(balance);
  if (!Number.isFinite(num)) return true; // bilinmeyen bakiye → güvenli taraf: açık say
  return num > OPEN_BALANCE_THRESHOLD;
}

async function registerBackgroundSync() {
  if (
    typeof window === 'undefined' ||
    !('serviceWorker' in navigator) ||
    !('SyncManager' in window)
  ) {
    return false;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    await registration.sync.register(CHECKOUT_SYNC_TAG);
    return true;
  } catch (error) {
    console.warn('[OfflineCheckout] Background sync registration failed', error);
    return false;
  }
}

async function queueCheckout({ bookingId, key }) {
  const authToken = localStorage.getItem('token')?.replace('Bearer ', '') || null;
  await enqueueCheckout({
    id: key,
    bookingId,
    idempotencyKey: key,
    authToken,
    status: 'pending',
  });
  await registerBackgroundSync();
  emitQueueChanged({ bookingId, queued: true });
}

/**
 * @param {string} bookingId
 * @param {{ balance?: number, onlineRequest?: () => Promise<any> }} options
 *   balance: tıklama anındaki bilinen bakiye. > 0.01 ise ASLA kuyruğa alınmaz.
 *   onlineRequest: bileşenin mevcut çevrimiçi çıkış çağrısı (sıcak yol korunur).
 * @returns {Promise<
 *   | { offlineQueued: true, key: string }
 *   | { offlineQueued: false, synced: true, key: string, data?: any }
 *   | { blocked: true, reason: 'OUTSTANDING_BALANCE' | 'OFFLINE_OPEN_BALANCE' }
 * >}
 */
export async function performCheckout(bookingId, { balance, onlineRequest } = {}) {
  const key = checkoutKeyForBooking(bookingId);
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false;

  // Açık bakiye → ÖDEME çevrimdışına alınamaz. Asla kuyruğa alma.
  if (hasOpenBalance(balance)) {
    if (offline) {
      // Çevrimdışı + açık bakiye: işlem yapılamaz, operatöre bildir.
      return { blocked: true, reason: 'OUTSTANDING_BALANCE' };
    }
    // Çevrimiçi: normal çıkışı dene (backend 402 verirse çağırana fırlatılır).
    try {
      const response = onlineRequest
        ? await onlineRequest()
        : await axios.post(checkoutEndpoint(bookingId));
      return { offlineQueued: false, synced: true, key, data: response?.data };
    } catch (error) {
      if (isNetworkError(error)) {
        // Açık bakiyeyi kuyruğa ALMA — ödeme çevrimdışı olamaz.
        return { blocked: true, reason: 'OFFLINE_OPEN_BALANCE' };
      }
      throw error;
    }
  }

  // Sıfır / kapalı bakiye → çevrimdışı çıkışa uygun.
  if (offline) {
    await queueCheckout({ bookingId, key });
    return { offlineQueued: true, key };
  }

  try {
    const response = onlineRequest
      ? await onlineRequest()
      : await axios.post(checkoutEndpoint(bookingId));
    return { offlineQueued: false, synced: true, key, data: response?.data };
  } catch (error) {
    if (isNetworkError(error)) {
      await queueCheckout({ bookingId, key });
      return { offlineQueued: true, key };
    }
    // Gerçek sunucu/iş hatası (402 açık bakiye, geçersiz durum, yetki) →
    // çağıran operatöre göstersin; kuyruğa alma.
    throw error;
  }
}

/**
 * Operatörün manuel "yeniden dene" eylemi.
 */
export async function requeueCheckout(id) {
  const updated = await updateQueuedCheckout(id, {
    status: 'pending',
    error: null,
    httpStatus: null,
    attempts: 0,
  });
  emitQueueChanged({ id, requeued: true });
  return updated;
}

/**
 * Operatörün manuel "iptal" eylemi.
 */
export async function cancelQueuedCheckout(id) {
  await removeQueuedCheckout(id);
  emitQueueChanged({ id, cancelled: true });
}

/**
 * Toplu "tümünü yeniden dene".
 * @param {string[]} ids
 * @returns {Promise<number>}
 */
export async function requeueCheckouts(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await updateQueuedCheckout(id, {
      status: 'pending',
      error: null,
      httpStatus: null,
      attempts: 0,
    });
  }
  if (list.length) emitQueueChanged({ requeuedAll: true, count: list.length });
  return list.length;
}

/**
 * Toplu "tümünü iptal".
 * @param {string[]} ids
 * @returns {Promise<number>}
 */
export async function cancelQueuedCheckouts(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await removeQueuedCheckout(id);
  }
  if (list.length) emitQueueChanged({ cancelledAll: true, count: list.length });
  return list.length;
}

/**
 * Sayfa bağlamı yedek eşitleyici. Idempotent POST'a replay eder.
 * @returns {Promise<{synced: number, conflicts: number, remaining: number, stoppedOffline: boolean}>}
 */
export async function processQueuedCheckouts() {
  let synced = 0;
  let conflicts = 0;
  let stoppedOffline = false;

  const items = await listQueuedCheckouts();
  const pending = items.filter((it) => it.status !== 'conflict');

  for (const item of pending) {
    if (!item.bookingId) {
      await removeQueuedCheckout(item.id);
      continue;
    }
    try {
      await axios.post(checkoutEndpoint(item.bookingId));
      await removeQueuedCheckout(item.id);
      synced += 1;
      emitQueueChanged({ bookingId: item.bookingId, synced: true });
    } catch (error) {
      if (isNetworkError(error)) {
        stoppedOffline = true;
        break;
      }
      // "Zaten çıkış yapılmış" → idempotent BAŞARI (çıkış olmuş, yanıt kaybolmuş).
      if (isAlreadyCheckedOut(error)) {
        await removeQueuedCheckout(item.id);
        synced += 1;
        emitQueueChanged({ bookingId: item.bookingId, synced: true });
        continue;
      }
      const status = error.response?.status;
      const attempts = (item.attempts || 0) + 1;
      if (status === 401 || (status && status >= 500)) {
        // Geçici (token/sunucu) — deneme tavanına ulaşıldıysa çakışmaya çevir.
        if (attempts >= MAX_CHECKOUT_ATTEMPTS) {
          await updateQueuedCheckout(item.id, {
            status: 'conflict',
            error: { code: 'MAX_RETRIES_EXCEEDED', httpStatus: status || null },
            httpStatus: status || null,
            attempts,
          });
          conflicts += 1;
          emitQueueChanged({ bookingId: item.bookingId, conflict: true });
        } else {
          await updateQueuedCheckout(item.id, { attempts });
        }
        continue;
      }
      // 402 açık bakiye (kuyruğa alındıktan sonra ücret eklendi) veya diğer
      // kalıcı 4xx → çakışma; sonsuz tekrar denenmez, operatöre yüzeye çıkar.
      const detail = error.response?.data?.detail ?? null;
      const isOutstanding = status === 402;
      await updateQueuedCheckout(item.id, {
        status: 'conflict',
        error: isOutstanding ? { code: 'OUTSTANDING_BALANCE' } : detail,
        httpStatus: status || null,
        attempts,
      });
      conflicts += 1;
      emitQueueChanged({ bookingId: item.bookingId, conflict: true });
    }
  }

  const remainingItems = await listQueuedCheckouts();
  return {
    synced,
    conflicts,
    remaining: remainingItems.length,
    stoppedOffline,
  };
}
