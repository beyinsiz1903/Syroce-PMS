/**
 * Offline Check-in — çevrimdışı ön büro girişi + otomatik eşitleme.
 *
 * Akış:
 *  - performCheckin(): önce çevrimiçi dener (bileşenin kendi uç noktası).
 *    Ağ hatası (sunucuya ulaşılamadı) → IndexedDB kuyruğuna yazar, Background
 *    Sync kaydeder ve { offlineQueued: true } döner. Gerçek sunucu/iş hatası
 *    (oda dolu vb.) ise kuyruğa ALINMAZ — çağırana fırlatılır (çakışma).
 *  - processQueuedCheckins(): sayfa bağlamı yedek eşitleyici ('online' olayı /
 *    Background Sync desteklenmeyen tarayıcılar). Idempotent v2 ucuna replay eder.
 *
 * Tekrar oynatma her zaman idempotent `POST /frontdesk/v2/checkin` ucuna gider;
 * deterministik anahtar `checkin-<bookingId>` çift kayıt/çift folyoyu önler ve
 * aynı rezervasyonun yeniden kuyruğa alınmasını birleştirir (dedupe).
 */
import axios from 'axios';
import {
  enqueueCheckin,
  listQueuedCheckins,
  removeQueuedCheckin,
  updateQueuedCheckin,
} from '@/utils/offlineQueueDB';

export const CHECKIN_SYNC_TAG = 'sync-checkins';
const CHECKIN_SYNC_ENDPOINT = '/frontdesk/v2/checkin';

// Geçici (401/5xx) hatalar bu sayıya ulaşınca artık sonsuza dek tekrar
// denenmez; operatör müdahalesi için çakışmaya dönüştürülür.
export const MAX_CHECKIN_ATTEMPTS = 8;
// Bu yaştan eski bekleyen girişler "uzun süredir bekliyor" uyarısı tetikler.
export const STALE_CHECKIN_AGE_MS = 5 * 60 * 1000;

// Sayfa içi dinleyicilerin (status bar) anında güncellenmesi için yayın.
export const CHECKIN_QUEUE_EVENT = 'syroce:checkin-queue-changed';

function emitQueueChanged(detail = {}) {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(CHECKIN_QUEUE_EVENT, { detail }));
  } catch {
    // CustomEvent yoksa sessizce geç.
  }
}

// Sunucudan HTTP yanıtı YOKSA (ağ/zaman aşımı) çevrimdışı kabul edilir.
function isNetworkError(error) {
  return !error || !error.response;
}

export function checkinKeyForBooking(bookingId) {
  return `checkin-${bookingId}`;
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
    await registration.sync.register(CHECKIN_SYNC_TAG);
    return true;
  } catch (error) {
    console.warn('[OfflineCheckin] Background sync registration failed', error);
    return false;
  }
}

async function queueCheckin({ bookingId, idempotencyKey }) {
  const authToken = localStorage.getItem('token')?.replace('Bearer ', '') || null;
  await enqueueCheckin({
    id: idempotencyKey,
    bookingId,
    idempotencyKey,
    authToken,
    status: 'pending',
  });
  await registerBackgroundSync();
  emitQueueChanged({ bookingId, queued: true });
}

/**
 * @param {string} bookingId
 * @param {{ onlineRequest?: () => Promise<any> }} options
 *   onlineRequest: bileşenin mevcut çevrimiçi check-in çağrısı (regresyonu
 *   önlemek için sıcak yol değişmeden korunur). Verilmezse v2 ucu kullanılır.
 * @returns {Promise<{offlineQueued: boolean, synced?: boolean, idempotencyKey: string, data?: any}>}
 */
export async function performCheckin(bookingId, { onlineRequest } = {}) {
  const idempotencyKey = checkinKeyForBooking(bookingId);

  // Net şekilde çevrimdışıysak 30sn timeout beklemeden hemen kuyruğa al.
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    await queueCheckin({ bookingId, idempotencyKey });
    return { offlineQueued: true, idempotencyKey };
  }

  try {
    const response = onlineRequest
      ? await onlineRequest()
      : await axios.post(CHECKIN_SYNC_ENDPOINT, {
          booking_id: bookingId,
          idempotency_key: idempotencyKey,
        });
    return { offlineQueued: false, synced: true, idempotencyKey, data: response?.data };
  } catch (error) {
    if (isNetworkError(error)) {
      await queueCheckin({ bookingId, idempotencyKey });
      return { offlineQueued: true, idempotencyKey };
    }
    // Gerçek sunucu/iş hatası (oda dolu, geçersiz durum, yetki) → çağıran
    // operatöre göstersin; kuyruğa alma.
    throw error;
  }
}

/**
 * Operatörün manuel "yeniden dene" eylemi: çakışan/takılan bir girişi tekrar
 * bekleyene çevirir, deneme sayacını sıfırlar ve hata izini temizler. Çağıran
 * (hook) ardından processQueuedCheckins'i tetikler.
 */
export async function requeueCheckin(id) {
  const updated = await updateQueuedCheckin(id, {
    status: 'pending',
    error: null,
    httpStatus: null,
    attempts: 0,
  });
  emitQueueChanged({ id, requeued: true });
  return updated;
}

/**
 * Operatörün manuel "iptal" eylemi: girişi kuyruktan kaldırır.
 */
export async function cancelQueuedCheckin(id) {
  await removeQueuedCheckin(id);
  emitQueueChanged({ id, cancelled: true });
}

/**
 * Toplu "tümünü yeniden dene": verilen kimliklerdeki girişleri pending'e çevirir,
 * deneme sayacını sıfırlar ve hata izini temizler. Tek bir kuyruk-değişti olayı
 * yayar (N ayrı tazeleme yerine). Çağıran (hook) ardından eşitlemeyi tetikler.
 * @param {string[]} ids
 * @returns {Promise<number>} işlenen giriş sayısı
 */
export async function requeueCheckins(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await updateQueuedCheckin(id, {
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
 * Toplu "tümünü iptal": verilen kimliklerdeki girişleri kuyruktan kaldırır.
 * Tek bir kuyruk-değişti olayı yayar.
 * @param {string[]} ids
 * @returns {Promise<number>} kaldırılan giriş sayısı
 */
export async function cancelQueuedCheckins(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await removeQueuedCheckin(id);
  }
  if (list.length) emitQueueChanged({ cancelledAll: true, count: list.length });
  return list.length;
}

/**
 * Sayfa bağlamı yedek eşitleyici. Idempotent v2 ucuna replay eder; axios
 * interceptor'ları token enjekte eder + 401'de sessiz yeniler.
 * @returns {Promise<{synced: number, conflicts: number, remaining: number}>}
 */
export async function processQueuedCheckins() {
  let synced = 0;
  let conflicts = 0;
  let stoppedOffline = false;

  const items = await listQueuedCheckins();
  const pending = items.filter((it) => it.status !== 'conflict');

  for (const item of pending) {
    if (!item.bookingId) {
      await removeQueuedCheckin(item.id);
      continue;
    }
    const key = item.idempotencyKey || item.id;
    try {
      await axios.post(CHECKIN_SYNC_ENDPOINT, {
        booking_id: item.bookingId,
        idempotency_key: key,
      });
      await removeQueuedCheckin(item.id);
      synced += 1;
      emitQueueChanged({ bookingId: item.bookingId, synced: true });
    } catch (error) {
      if (isNetworkError(error)) {
        stoppedOffline = true;
        break;
      }
      const status = error.response?.status;
      const attempts = (item.attempts || 0) + 1;
      if (status === 401 || (status && status >= 500)) {
        // Geçici (token/sunucu) — normalde kuyrukta bırakılır. Ancak deneme
        // tavanına ulaşıldıysa sonsuz tekrarı durdur, çakışmaya çevir.
        if (attempts >= MAX_CHECKIN_ATTEMPTS) {
          await updateQueuedCheckin(item.id, {
            status: 'conflict',
            error: { code: 'MAX_RETRIES_EXCEEDED', httpStatus: status || null },
            httpStatus: status || null,
            attempts,
          });
          conflicts += 1;
          emitQueueChanged({ bookingId: item.bookingId, conflict: true });
        } else {
          await updateQueuedCheckin(item.id, { attempts });
        }
        continue;
      }
      // Kalıcı hata (404 rezervasyon yok, 403 yetki, 409 oda dolu vb.) →
      // sonsuz tekrar denenmez, operatöre çakışma olarak yüzeye çıkar.
      const detail = error.response?.data?.detail ?? null;
      await updateQueuedCheckin(item.id, {
        status: 'conflict',
        error: detail,
        httpStatus: status || null,
        attempts,
      });
      conflicts += 1;
      emitQueueChanged({ bookingId: item.bookingId, conflict: true });
    }
  }

  const remainingItems = await listQueuedCheckins();
  return {
    synced,
    conflicts,
    remaining: remainingItems.length,
    stoppedOffline,
  };
}
