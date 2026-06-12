/**
 * Service Worker for Offline Support & Caching
 * Provides offline functionality and aggressive caching
 */

// Bumped when caching topology değişiyor — eski client'lar otomatik yeni
// CACHE_NAME'e geçer (activate handler eskileri siler).
const CACHE_VERSION = 'v1.2.0';
const CACHE_NAME = `hotel-pms-${CACHE_VERSION}`;
// Auth ayrımı: kullanıcı değişimi sonrası tüm cache'i drop edebilmek için
// client'lar `postMessage({ type: 'AUTH_CHANGED' })` gönderir → SW siler.
const OFFLINE_DB_NAME = 'SyroceOffline';
// v2: checkinQueue store eklendi (çevrimdışı ön büro girişleri). Frontend
// tarafı (src/utils/offlineQueueDB.jsx) ile aynı versiyon olmalı.
const OFFLINE_DB_VERSION = 2;
const MEDIA_QUEUE_STORE = 'mediaQueue';
const TASK_QUEUE_STORE = 'taskQueue';
const NOTIFICATION_LOG_STORE = 'notificationLog';
const CHECKIN_QUEUE_STORE = 'checkinQueue';
const MEDIA_SYNC_TAG = 'sync-media-uploads';
const TASK_SYNC_TAG = 'sync-task-updates';
const NOTIFICATION_SYNC_TAG = 'sync-notification-log';
const CHECKIN_SYNC_TAG = 'sync-checkins';
// Çevrimdışı kuyruğun tekrar oynatılacağı tek idempotent uç.
const CHECKIN_SYNC_ENDPOINT = '/api/frontdesk/v2/checkin';
// Geçici (401/5xx) hatalar bu sayıya ulaşınca sonsuza dek tekrar denenmez;
// operatör müdahalesi için çakışmaya dönüştürülür. src/utils/offlineCheckin.js
// içindeki MAX_CHECKIN_ATTEMPTS ile aynı tutulmalı.
const MAX_CHECKIN_ATTEMPTS = 8;

// Assets to cache immediately on install
const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/static/css/main.css',
  '/static/js/main.js',
  '/manifest.json',
];

// Cache strategies
const CACHE_STRATEGIES = {
  // Network first, fallback to cache (for API calls)
  NETWORK_FIRST: 'network-first',
  
  // Cache first, fallback to network (for static assets)
  CACHE_FIRST: 'cache-first',
  
  // Network only (no cache)
  NETWORK_ONLY: 'network-only',
  
  // Cache only
  CACHE_ONLY: 'cache-only',
  
  // Stale while revalidate
  STALE_WHILE_REVALIDATE: 'stale-while-revalidate',
};

// SWR (stale-while-revalidate) tercih edilen rotalar — anlık UI yanıtı +
// arka planda taze veri. UI tarafında React Query refetchOnWindowFocus zaten
// senkronize ediyor; SW sadece "ilk paint hızlı" amacıyla cache servisliyor.
const NO_CACHE_PATTERNS = [
  /\/api\/auth\/(login|logout|refresh|2fa|verify|password)/i,
  /\/api\/payments?\/(charge|refund|capture)/i,
  /\/api\/cashier/i,
  /\/api\/folios?\/(charge|payment|void|adjust)/i,
  /\/api\/bookings?\/(create|cancel|check.?in|check.?out)/i,
  /\/api\/night-audit/i,
  /\/api\/admin/i,
  /\/api\/quick-?id/i,
];

const ROUTE_STRATEGIES = [
  {
    pattern: /\/api\/optimization\/(health|cache\/stats|views\/stats)/,
    strategy: CACHE_STRATEGIES.NETWORK_FIRST,
    cacheDuration: 60 * 1000, // 1 minute
  },
  // Read-heavy listeler: SWR — ilk paint cache'ten, arka planda taze çek
  {
    pattern: /\/api\/(rooms|guests|room-types|rate-plans|amenities)\/?(\?|$)/,
    strategy: CACHE_STRATEGIES.STALE_WHILE_REVALIDATE,
    cacheDuration: 5 * 60 * 1000,
  },
  {
    pattern: /\/api\/(pms|bookings)/,
    strategy: CACHE_STRATEGIES.NETWORK_FIRST,
    cacheDuration: 5 * 60 * 1000,
  },
  // Ön büro okuma listeleri (arrivals/departures/in-house/oda durumu): çevrimdışı
  // okunabilirlik için son taze yanıtı cache'le, internet varken ağ-öncelikli.
  {
    pattern: /\/api\/(unified|housekeeping|frontdesk)\//,
    strategy: CACHE_STRATEGIES.NETWORK_FIRST,
    cacheDuration: 5 * 60 * 1000,
  },
  {
    pattern: /\/api\/(dashboard|kpis|widgets)/,
    strategy: CACHE_STRATEGIES.STALE_WHILE_REVALIDATE,
    cacheDuration: 2 * 60 * 1000,
  },
  {
    pattern: /\/api\/reports/,
    strategy: CACHE_STRATEGIES.STALE_WHILE_REVALIDATE,
    cacheDuration: 60 * 60 * 1000, // 1 hour
  },
  {
    pattern: /\.(js|css|png|jpg|jpeg|svg|woff|woff2)$/,
    strategy: CACHE_STRATEGIES.CACHE_FIRST,
    cacheDuration: 7 * 24 * 60 * 60 * 1000, // 7 days
  },
];

// ─── Cache timestamp yan-channel ────────────────────────────────────────────
// Body-moving + custom header desenini kaldırdık (race → "body already used").
// Onun yerine SW global scope'ta in-memory bir timestamp haritası tutuyoruz.
// SW yeniden başlarsa harita boşalır → ilgili URL için cache "stale" sayılır
// ve networkFirst/SWR network'ten taze veri çeker (güvenli/fail-safe).
const _cacheTimestamps = new Map();
// Maksimum giriş sayısı (LRU yerine basit FIFO eviction — memory leak guard).
const _CACHE_TS_MAX = 500;

function recordCacheTimestamp(url, ts) {
  if (_cacheTimestamps.size >= _CACHE_TS_MAX) {
    const firstKey = _cacheTimestamps.keys().next().value;
    if (firstKey !== undefined) _cacheTimestamps.delete(firstKey);
  }
  _cacheTimestamps.set(url, ts);
}

function getCacheTimestamp(url) {
  return _cacheTimestamps.get(url);
}

// Install event - precache assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Precaching assets');
      return cache.addAll(PRECACHE_ASSETS);
    }).then(() => {
      console.log('[SW] Installation complete');
      return self.skipWaiting();
    })
  );
});

// Activate event - cleanup old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('[SW] Activation complete');
      return self.clients.claim();
    })
  );
});

// Fetch event - handle requests with caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }
  
  // Skip cross-origin requests
  if (url.origin !== self.location.origin) {
    return;
  }

  // Güvenlik: hassas/auth-mutasyon rotalarında kesinlikle cache yok.
  // (Auth-protected GET listesi bile olsa, kullanıcı değişimi sonrası
  // AUTH_CHANGED message handler tüm cache'i drop ediyor.)
  for (const noCache of NO_CACHE_PATTERNS) {
    if (noCache.test(url.pathname)) {
      return; // SW araya girmesin → varsayılan network
    }
  }

  // Find matching strategy
  let strategy = CACHE_STRATEGIES.NETWORK_FIRST; // Default
  let cacheDuration = 5 * 60 * 1000; // 5 minutes default
  
  for (const route of ROUTE_STRATEGIES) {
    if (route.pattern.test(url.pathname)) {
      strategy = route.strategy;
      cacheDuration = route.cacheDuration;
      break;
    }
  }
  
  // Apply strategy
  switch (strategy) {
    case CACHE_STRATEGIES.NETWORK_FIRST:
      event.respondWith(networkFirst(request, cacheDuration));
      break;
      
    case CACHE_STRATEGIES.CACHE_FIRST:
      event.respondWith(cacheFirst(request, cacheDuration));
      break;
      
    case CACHE_STRATEGIES.STALE_WHILE_REVALIDATE:
      event.respondWith(staleWhileRevalidate(request, cacheDuration));
      break;
      
    case CACHE_STRATEGIES.NETWORK_ONLY:
      event.respondWith(fetch(request));
      break;
      
    case CACHE_STRATEGIES.CACHE_ONLY:
      event.respondWith(caches.match(request));
      break;
      
    default:
      event.respondWith(networkFirst(request, cacheDuration));
  }
});

// Strategy implementations

async function networkFirst(request, cacheDuration) {
  const cache = await caches.open(CACHE_NAME);
  
  try {
    const networkResponse = await fetch(request);

    // Cache successful responses.
    // Önemli: body'yi clone'dan yeni Response'a "taşımak" (new Response(clone.body, ...))
    // tarayıcı/Sentry instrumentation ile race'e girip "Failed to execute 'clone' on
    // 'Response': Response body is already used" üretebiliyor. MDN standardı: clone'u
    // doğrudan cache.put'a ver. Timestamp için yan-channel kullanıyoruz (timestampCache).
    if (networkResponse.ok) {
      const clone = networkResponse.clone();
      cache.put(request, clone).then(() => {
        recordCacheTimestamp(request.url, Date.now());
      }).catch(() => {});
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, falling back to cache:', request.url);
    
    const cachedResponse = await cache.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline page or error
    return new Response('Offline - No cached data available', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: new Headers({
        'Content-Type': 'text/plain',
      }),
    });
  }
}

async function cacheFirst(request, cacheDuration) {
  const cache = await caches.open(CACHE_NAME);
  const cachedResponse = await cache.match(request);
  
  if (cachedResponse) {
    // Check if cache is expired (yan-channel timestamp; bkz networkFirst)
    const cachedAt = getCacheTimestamp(request.url);
    if (cachedAt && Date.now() - cachedAt < cacheDuration) {
      console.log('[SW] Serving from cache:', request.url);
      return cachedResponse;
    }
  }

  // Fetch from network — body-moving desenden kaçınıyoruz; clone doğrudan cache'e gider.
  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const clone = networkResponse.clone();
      cache.put(request, clone).then(() => {
        recordCacheTimestamp(request.url, Date.now());
      }).catch(() => {});
    }

    return networkResponse;
  } catch (error) {
    // Return cached response even if expired
    if (cachedResponse) {
      return cachedResponse;
    }
    
    throw error;
  }
}

async function staleWhileRevalidate(request, cacheDuration) {
  const cache = await caches.open(CACHE_NAME);
  const cachedResponse = await cache.match(request);

  // Cache TTL aşıldıysa "stale" sayma — fetch sonucunu bekle.
  let cacheStillFresh = false;
  if (cachedResponse) {
    const cachedAt = getCacheTimestamp(request.url);
    if (cachedAt) {
      cacheStillFresh = Date.now() - cachedAt < cacheDuration;
    }
  }

  // Fetch from network in background — clone doğrudan cache.put'a; body-moving YOK.
  const fetchPromise = fetch(request)
    .then((networkResponse) => {
      // Hatalı yanıtları ASLA cache'leme (401/403/5xx leak'ini engelle).
      if (networkResponse && networkResponse.ok) {
        // Cache-Control: no-store / private respect
        const cc = (networkResponse.headers.get('Cache-Control') || '').toLowerCase();
        if (!cc.includes('no-store') && !cc.includes('private')) {
          const clone = networkResponse.clone();
          cache.put(request, clone).then(() => {
            recordCacheTimestamp(request.url, Date.now());
          }).catch(() => {});
        }
      }
      return networkResponse;
    })
    .catch(() => null);

  // Taze cache varsa hemen dön (background'da revalidate sürer)
  if (cacheStillFresh) {
    return cachedResponse;
  }
  // Stale cache varsa ve network başarısızsa fallback dön
  const fresh = await fetchPromise;
  if (fresh) return fresh;
  if (cachedResponse) return cachedResponse;
  return new Response('Offline - No cached data available', {
    status: 503,
    statusText: 'Service Unavailable',
    headers: new Headers({ 'Content-Type': 'text/plain' }),
  });
}

// Auth değişiminde tüm dynamic cache'i drop et — cross-user data leak guard.
self.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type === 'AUTH_CHANGED' || data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((names) =>
        Promise.all(names.filter((n) => n.startsWith('hotel-pms-')).map((n) => caches.delete(n)))
      )
    );
  }
  if (data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  // Sayfa bağlamından tetiklenen yedek senkronizasyon (Background Sync API
  // desteklenmeyen tarayıcılar / 'online' olayı için).
  if (data.type === 'PROCESS_CHECKIN_QUEUE') {
    event.waitUntil(processCheckinQueue());
  }
});

// Background sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync triggered:', event.tag);
  
  if (event.tag === MEDIA_SYNC_TAG) {
    event.waitUntil(processMediaQueue());
  } else if (event.tag === TASK_SYNC_TAG) {
    event.waitUntil(processTaskQueue());
  } else if (event.tag === CHECKIN_SYNC_TAG) {
    event.waitUntil(processCheckinQueue());
  } else if (event.tag === NOTIFICATION_SYNC_TAG || event.tag === 'sync-offline-actions') {
    event.waitUntil(broadcastClientMessage({ type: 'SYNC_NOTIFICATION_LOG' }));
  }
});

// Push notifications
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(handlePushNotification(data));
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});

async function openOfflineDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      if (!db.objectStoreNames.contains(MEDIA_QUEUE_STORE)) {
        const store = db.createObjectStore(MEDIA_QUEUE_STORE, { keyPath: 'id' });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
      if (!db.objectStoreNames.contains(TASK_QUEUE_STORE)) {
        const store = db.createObjectStore(TASK_QUEUE_STORE, { keyPath: 'id' });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
      if (!db.objectStoreNames.contains(NOTIFICATION_LOG_STORE)) {
        const store = db.createObjectStore(NOTIFICATION_LOG_STORE, { keyPath: 'id' });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
      if (!db.objectStoreNames.contains(CHECKIN_QUEUE_STORE)) {
        const store = db.createObjectStore(CHECKIN_QUEUE_STORE, { keyPath: 'id' });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
    };
  });
}

async function getAllFromStore(storeName) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([storeName], 'readonly');
    const store = tx.objectStore(storeName);
    const index = store.index('createdAt');
    const request = index.openCursor(null, 'next');
    const items = [];

    request.onsuccess = (event) => {
      const cursor = event.target.result;
      if (cursor) {
        items.push(cursor.value);
        cursor.continue();
      } else {
        resolve(items);
      }
    };
    request.onerror = () => reject(request.error);
  });
}

async function removeFromStore(storeName, id) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([storeName], 'readwrite');
    const store = tx.objectStore(storeName);
    const request = store.delete(id);
    request.onsuccess = () => resolve(true);
    request.onerror = () => reject(request.error);
  });
}

async function processMediaQueue() {
  try {
    const items = await getAllFromStore(MEDIA_QUEUE_STORE);
    if (!items.length) {
      return;
    }

    for (const media of items) {
      if (!media.file) {
        await removeFromStore(MEDIA_QUEUE_STORE, media.id);
        continue;
      }

      const descriptor = await ensureUploadDescriptor(media);
      if (!descriptor.uploadUrl) {
        console.warn('[SW] No upload URL yet, will retry later', descriptor.id);
        continue;
      }

      const headers = new Headers(descriptor.headers || {});
      if (!headers.has('Content-Type') && descriptor.contentType) {
        headers.set('Content-Type', descriptor.contentType);
      }

      try {
        const uploadResponse = await fetch(descriptor.uploadUrl, {
          method: descriptor.method || 'PUT',
          headers,
          body: descriptor.file
        });

        if (!uploadResponse.ok) {
          console.warn('[SW] Media upload failed, will retry later', descriptor.id);
          continue;
        }
      } catch (err) {
        console.warn('[SW] Media upload network error', err);
        continue;
      }

      await confirmMediaDescriptor(descriptor);
      await removeFromStore(MEDIA_QUEUE_STORE, descriptor.id);
      await broadcastClientMessage({
        type: 'MEDIA_UPLOAD_COMPLETED',
        payload: { mediaId: descriptor.mediaId }
      });
    }
  } catch (error) {
    console.error('[SW] processMediaQueue error', error);
  }
}

async function ensureUploadDescriptor(media) {
  if (media.uploadUrl && media.mediaId) {
    return media;
  }

  if (!media.requestPayload) {
    return media;
  }

  try {
    const headers = {
      'Content-Type': 'application/json',
      ...buildAuthHeader(media.authToken)
    };

    const response = await fetch('/api/media/request-upload', {
      method: 'POST',
      headers,
      body: JSON.stringify(media.requestPayload)
    });

    if (!response.ok) {
      console.warn('[SW] Failed to refresh upload descriptor', response.status);
      return media;
    }

    const data = await response.json();
    media.uploadUrl = data.upload_url;
    media.headers = data.headers;
    media.mediaId = data.media_id;
    media.confirmPayload = {
      ...(media.confirmPayload || {}),
      media_id: data.media_id,
      storage_url: data.upload_url
    };

    await updateStoreEntry(MEDIA_QUEUE_STORE, media);
    return media;
  } catch (error) {
    console.warn('[SW] ensureUploadDescriptor error', error);
    return media;
  }
}

async function confirmMediaDescriptor(media) {
  const payload = {
    ...(media.confirmPayload || {}),
    media_id: media.mediaId,
    storage_url: media.uploadUrl,
    content_type: media.contentType,
    size_bytes: media.file?.size,
    metadata: media.metadata || {},
    qa_required: media.qaRequired
  };

  const headers = {
    'Content-Type': 'application/json',
    ...buildAuthHeader(media.authToken)
  };

  await fetch('/api/media/confirm', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload)
  });
}

async function processTaskQueue() {
  try {
    const tasks = await getAllFromStore(TASK_QUEUE_STORE);
    if (!tasks.length) {
      return;
    }

    for (const task of tasks) {
      if (!task.request) {
        await removeFromStore(TASK_QUEUE_STORE, task.id);
        continue;
      }

      const { url, method = 'POST', headers = {}, body } = task.request;
      try {
        const response = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined
        });

        if (response.ok) {
          await removeFromStore(TASK_QUEUE_STORE, task.id);
          await broadcastClientMessage({ type: 'TASK_SYNC_COMPLETED', payload: { taskId: task.referenceId } });
        } else {
          console.warn('[SW] Task sync failed', task, response.status);
        }
      } catch (err) {
        console.warn('[SW] Task sync network error', err);
      }
    }
  } catch (error) {
    console.error('[SW] processTaskQueue error', error);
  }
}

async function processCheckinQueue() {
  try {
    const items = await getAllFromStore(CHECKIN_QUEUE_STORE);
    if (!items.length) {
      return;
    }

    for (const item of items) {
      // Operatör müdahalesi bekleyen çakışmaları tekrar denemeyiz.
      if (item.status === 'conflict') {
        continue;
      }
      if (!item.bookingId) {
        await removeFromStore(CHECKIN_QUEUE_STORE, item.id);
        continue;
      }

      const key = item.idempotencyKey || item.id;
      try {
        const response = await fetch(CHECKIN_SYNC_ENDPOINT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': key,
            ...buildAuthHeader(item.authToken)
          },
          body: JSON.stringify({ booking_id: item.bookingId, idempotency_key: key })
        });

        if (response.ok) {
          await removeFromStore(CHECKIN_QUEUE_STORE, item.id);
          await broadcastClientMessage({
            type: 'CHECKIN_SYNCED',
            payload: { id: item.id, bookingId: item.bookingId }
          });
        } else if (response.status === 401 || response.status >= 500) {
          // 401: token tazelenmesi gerek (sayfa bağlamı axios silent-refresh ile
          // halleder); 5xx: geçici. Kuyrukta bırak, sonraki sync denesin.
          // Ancak deneme tavanına ulaşıldıysa sonsuz tekrarı durdur.
          const attempts = (item.attempts || 0) + 1;
          item.attempts = attempts;
          item.updatedAt = Date.now();
          if (attempts >= MAX_CHECKIN_ATTEMPTS) {
            item.status = 'conflict';
            item.error = { code: 'MAX_RETRIES_EXCEEDED', httpStatus: response.status };
            item.httpStatus = response.status;
            await updateStoreEntry(CHECKIN_QUEUE_STORE, item);
            await broadcastClientMessage({
              type: 'CHECKIN_CONFLICT',
              payload: { id: item.id, bookingId: item.bookingId, status: response.status, detail: item.error }
            });
          } else {
            await updateStoreEntry(CHECKIN_QUEUE_STORE, item);
            console.warn('[SW] Check-in sync transient, will retry', response.status, attempts);
          }
        } else {
          // Kalıcı 4xx (404 rezervasyon yok / oda dolu / geçersiz durum / yetki)
          // → sonsuz tekrar denenmez, çakışma olarak yüzeye çıkar.
          let detail = null;
          try {
            const data = await response.json();
            detail = data?.detail ?? data;
          } catch (err) {
            detail = null;
          }
          item.status = 'conflict';
          item.error = detail;
          item.httpStatus = response.status;
          item.attempts = (item.attempts || 0) + 1;
          item.updatedAt = Date.now();
          await updateStoreEntry(CHECKIN_QUEUE_STORE, item);
          await broadcastClientMessage({
            type: 'CHECKIN_CONFLICT',
            payload: { id: item.id, bookingId: item.bookingId, status: response.status, detail }
          });
        }
      } catch (err) {
        // Ağ hatası → hâlâ çevrimdışı; döngüyü durdur, sonraki sync denesin.
        console.warn('[SW] Check-in sync network error, still offline', err);
        break;
      }
    }
  } catch (error) {
    console.error('[SW] processCheckinQueue error', error);
  }
}

async function handlePushNotification(data) {
  const options = {
    body: data.body || 'New notification',
    icon: data.icon || '/icon-192.png',
    badge: data.badge || '/badge-72.png',
    vibrate: data.vibrate || [200, 100, 200],
    data: data,
    actions: data.actions || [],
    tag: data.tag || `notification-${Date.now()}`
  };

  await logNotificationEvent({
    title: data.title || 'Hotel PMS',
    body: data.body,
    data,
    createdAt: Date.now()
  });

  await broadcastClientMessage({ type: 'PUSH_NOTIFICATION', payload: data });

  return self.registration.showNotification(data.title || 'Hotel PMS', options);
}

async function logNotificationEvent(event) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([NOTIFICATION_LOG_STORE], 'readwrite');
    const store = tx.objectStore(NOTIFICATION_LOG_STORE);
    const record = {
      ...event,
      id: event.id || crypto.randomUUID(),
      createdAt: event.createdAt || Date.now()
    };
    const request = store.put(record);
    request.onsuccess = () => resolve(true);
    request.onerror = () => reject(request.error);
  });
}

async function broadcastClientMessage(message) {
  const clientList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  clientList.forEach((client) => {
    client.postMessage(message);
  });
}

async function updateStoreEntry(storeName, entry) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([storeName], 'readwrite');
    const store = tx.objectStore(storeName);
    const request = store.put(entry);
    request.onsuccess = () => resolve(true);
    request.onerror = () => reject(request.error);
  });
}

const buildAuthHeader = (token) =>
  token
    ? {
        Authorization: token.startsWith('Bearer ') ? token : `Bearer ${token}`
      }
    : {};

console.log('[SW] Service Worker loaded');
