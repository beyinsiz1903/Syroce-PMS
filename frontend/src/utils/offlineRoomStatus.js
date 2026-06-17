/**
 * Offline Room-Status — çevrimdışı kat hizmetleri oda-durumu güncellemesi +
 * otomatik eşitleme. offlineCheckin.js deseninin birebir kardeşi.
 *
 * Akış:
 *  - performRoomStatusUpdate(): önce çevrimiçi dener. Ağ hatası (sunucuya
 *    ulaşılamadı) → IndexedDB kuyruğuna yazar, Background Sync kaydeder ve
 *    { offlineQueued: true } döner. Gerçek sunucu/iş hatası (oda yok, yetki,
 *    geçersiz durum) ise kuyruğa ALINMAZ — çağırana fırlatılır (çakışma).
 *  - processQueuedRoomStatus(): sayfa bağlamı yedek eşitleyici ('online' olayı /
 *    Background Sync desteklenmeyen tarayıcılar). Idempotent PUT'a replay eder.
 *
 * Anahtar `roomstatus-<roomId>` deterministiktir: aynı oda için arka arkaya
 * yapılan değişiklikler aynı kayda yazılır (coalesce / last-write-wins), böylece
 * yalnızca en son istenen durum eşitlenir. Backend zaten last-write-wins
 * olduğundan tekrar oynatma idempotenttir.
 */
import axios from 'axios';
import {
  enqueueRoomStatus,
  listQueuedRoomStatus,
  removeQueuedRoomStatus,
  updateQueuedRoomStatus,
} from '@/utils/offlineQueueDB';

export const ROOM_STATUS_SYNC_TAG = 'sync-room-status';

// Geçici (401/5xx) hatalar bu sayıya ulaşınca artık sonsuza dek tekrar
// denenmez; operatör müdahalesi için çakışmaya dönüştürülür.
export const MAX_ROOM_STATUS_ATTEMPTS = 8;
// Bu yaştan eski bekleyen güncellemeler "uzun süredir bekliyor" uyarısı tetikler.
export const STALE_ROOM_STATUS_AGE_MS = 5 * 60 * 1000;

// Sayfa içi dinleyicilerin (status bar) anında güncellenmesi için yayın.
export const ROOM_STATUS_QUEUE_EVENT = 'syroce:roomstatus-queue-changed';

function emitQueueChanged(detail = {}) {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(ROOM_STATUS_QUEUE_EVENT, { detail }));
  } catch {
    // CustomEvent yoksa sessizce geç.
  }
}

// Sunucudan HTTP yanıtı YOKSA (ağ/zaman aşımı) çevrimdışı kabul edilir.
function isNetworkError(error) {
  return !error || !error.response;
}

export function roomStatusKeyForRoom(roomId) {
  return `roomstatus-${roomId}`;
}

function endpointForRoom(roomId) {
  return `/pms/housekeeping/rooms/${roomId}/status`;
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
    await registration.sync.register(ROOM_STATUS_SYNC_TAG);
    return true;
  } catch (error) {
    console.warn('[OfflineRoomStatus] Background sync registration failed', error);
    return false;
  }
}

async function queueRoomStatus({ roomId, roomStatus, key }) {
  const authToken = localStorage.getItem('token')?.replace('Bearer ', '') || null;
  // id == key → aynı oda için tekrar kuyruğa alma son durumun üstüne yazar
  // (coalesce / last-write-wins).
  await enqueueRoomStatus({
    id: key,
    roomId,
    roomStatus,
    authToken,
    status: 'pending',
  });
  await registerBackgroundSync();
  emitQueueChanged({ roomId, queued: true });
}

/**
 * @param {string} roomId
 * @param {string} newStatus  hedef oda durumu (clean/dirty/inspected/...)
 * @param {{ onlineRequest?: () => Promise<any> }} options
 *   onlineRequest: bileşenin mevcut çevrimiçi PUT çağrısı (sıcak yol değişmeden
 *   korunur). Verilmezse standart uç kullanılır.
 * @returns {Promise<{offlineQueued: boolean, synced?: boolean, key: string, data?: any}>}
 */
export async function performRoomStatusUpdate(roomId, newStatus, { onlineRequest } = {}) {
  const key = roomStatusKeyForRoom(roomId);

  // Net şekilde çevrimdışıysak timeout beklemeden hemen kuyruğa al.
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    await queueRoomStatus({ roomId, roomStatus: newStatus, key });
    return { offlineQueued: true, key };
  }

  try {
    const response = onlineRequest
      ? await onlineRequest()
      : await axios.put(endpointForRoom(roomId), { status: newStatus });
    return { offlineQueued: false, synced: true, key, data: response?.data };
  } catch (error) {
    if (isNetworkError(error)) {
      await queueRoomStatus({ roomId, roomStatus: newStatus, key });
      return { offlineQueued: true, key };
    }
    // Gerçek sunucu/iş hatası (oda yok, geçersiz durum, yetki) → çağıran
    // operatöre göstersin; kuyruğa alma.
    throw error;
  }
}

/**
 * Operatörün manuel "yeniden dene" eylemi: çakışan/takılan bir güncellemeyi
 * tekrar bekleyene çevirir, deneme sayacını sıfırlar ve hata izini temizler.
 */
export async function requeueRoomStatus(id) {
  const updated = await updateQueuedRoomStatus(id, {
    status: 'pending',
    error: null,
    httpStatus: null,
    attempts: 0,
  });
  emitQueueChanged({ id, requeued: true });
  return updated;
}

/**
 * Operatörün manuel "iptal" eylemi: güncellemeyi kuyruktan kaldırır.
 */
export async function cancelQueuedRoomStatus(id) {
  await removeQueuedRoomStatus(id);
  emitQueueChanged({ id, cancelled: true });
}

/**
 * Toplu "tümünü yeniden dene".
 * @param {string[]} ids
 * @returns {Promise<number>} işlenen giriş sayısı
 */
export async function requeueRoomStatuses(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await updateQueuedRoomStatus(id, {
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
 * @returns {Promise<number>} kaldırılan giriş sayısı
 */
export async function cancelQueuedRoomStatuses(ids) {
  const list = Array.isArray(ids) ? ids.filter(Boolean) : [];
  for (const id of list) {
    await removeQueuedRoomStatus(id);
  }
  if (list.length) emitQueueChanged({ cancelledAll: true, count: list.length });
  return list.length;
}

/**
 * Sayfa bağlamı yedek eşitleyici. Idempotent PUT'a replay eder; axios
 * interceptor'ları token enjekte eder + 401'de sessiz yeniler.
 * @returns {Promise<{synced: number, conflicts: number, remaining: number, stoppedOffline: boolean}>}
 */
export async function processQueuedRoomStatus() {
  let synced = 0;
  let conflicts = 0;
  let stoppedOffline = false;

  const items = await listQueuedRoomStatus();
  const pending = items.filter((it) => it.status !== 'conflict');

  for (const item of pending) {
    if (!item.roomId || !item.roomStatus) {
      await removeQueuedRoomStatus(item.id);
      continue;
    }
    try {
      await axios.put(endpointForRoom(item.roomId), { status: item.roomStatus });
      await removeQueuedRoomStatus(item.id);
      synced += 1;
      emitQueueChanged({ roomId: item.roomId, synced: true });
    } catch (error) {
      if (isNetworkError(error)) {
        stoppedOffline = true;
        break;
      }
      const status = error.response?.status;
      const attempts = (item.attempts || 0) + 1;
      if (status === 401 || (status && status >= 500)) {
        // Geçici (token/sunucu) — normalde kuyrukta bırakılır. Deneme tavanına
        // ulaşıldıysa sonsuz tekrarı durdur, çakışmaya çevir.
        if (attempts >= MAX_ROOM_STATUS_ATTEMPTS) {
          await updateQueuedRoomStatus(item.id, {
            status: 'conflict',
            error: { code: 'MAX_RETRIES_EXCEEDED', httpStatus: status || null },
            httpStatus: status || null,
            attempts,
          });
          conflicts += 1;
          emitQueueChanged({ roomId: item.roomId, conflict: true });
        } else {
          await updateQueuedRoomStatus(item.id, { attempts });
        }
        continue;
      }
      // Kalıcı hata (404 oda yok, 403 yetki, 422 geçersiz durum) → sonsuz
      // tekrar denenmez, operatöre çakışma olarak yüzeye çıkar.
      const detail = error.response?.data?.detail ?? null;
      await updateQueuedRoomStatus(item.id, {
        status: 'conflict',
        error: detail,
        httpStatus: status || null,
        attempts,
      });
      conflicts += 1;
      emitQueueChanged({ roomId: item.roomId, conflict: true });
    }
  }

  const remainingItems = await listQueuedRoomStatus();
  return {
    synced,
    conflicts,
    remaining: remainingItems.length,
    stoppedOffline,
  };
}
