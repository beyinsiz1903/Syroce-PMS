/**
 * Service Worker for Offline Support & Caching
 * Provides offline functionality and aggressive caching
 */

const CACHE_VERSION = 'v1.0.0';
const CACHE_NAME = `hotel-pms-${CACHE_VERSION}`;
const OFFLINE_DB_NAME = 'RoomOpsOffline';
const OFFLINE_DB_VERSION = 1;
const MEDIA_QUEUE_STORE = 'mediaQueue';
const TASK_QUEUE_STORE = 'taskQueue';
const NOTIFICATION_LOG_STORE = 'notificationLog';
const MEDIA_SYNC_TAG = 'sync-media-uploads';
const TASK_SYNC_TAG = 'sync-task-updates';
const NOTIFICATION_SYNC_TAG = 'sync-notification-log';

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

// Route patterns and their strategies
const ROUTE_STRATEGIES = [
  {
    pattern: /\/api\/optimization\/(health|cache\/stats|views\/stats)/,
    strategy: CACHE_STRATEGIES.NETWORK_FIRST,
    cacheDuration: 60 * 1000, // 1 minute
  },
  {
    pattern: /\/api\/(pms|bookings|rooms|guests)/,
    strategy: CACHE_STRATEGIES.NETWORK_FIRST,
    cacheDuration: 5 * 60 * 1000, // 5 minutes
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
    
    // Cache successful responses
    if (networkResponse.ok) {
      const responseToCache = networkResponse.clone();
      
      // Add expiry timestamp
      const headers = new Headers(responseToCache.headers);
      headers.append('sw-cached-at', Date.now().toString());
      
      const cachedResponse = new Response(responseToCache.body, {
        status: responseToCache.status,
        statusText: responseToCache.statusText,
        headers: headers,
      });
      
      cache.put(request, cachedResponse);
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
    // Check if cache is expired
    const cachedAt = cachedResponse.headers.get('sw-cached-at');
    
    if (cachedAt) {
      const age = Date.now() - parseInt(cachedAt);
      
      if (age < cacheDuration) {
        console.log('[SW] Serving from cache:', request.url);
        return cachedResponse;
      }
    }
  }
  
  // Fetch from network
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const headers = new Headers(networkResponse.headers);
      headers.append('sw-cached-at', Date.now().toString());
      
      const responseToCache = new Response(networkResponse.body, {
        status: networkResponse.status,
        statusText: networkResponse.statusText,
        headers: headers,
      });
      
      cache.put(request, responseToCache.clone());
      
      return responseToCache;
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
  
  // Fetch from network in background
  const fetchPromise = fetch(request).then((networkResponse) => {
    if (networkResponse.ok) {
      const headers = new Headers(networkResponse.headers);
      headers.append('sw-cached-at', Date.now().toString());
      
      const responseToCache = new Response(networkResponse.body, {
        status: networkResponse.status,
        statusText: networkResponse.statusText,
        headers: headers,
      });
      
      cache.put(request, responseToCache);
    }
    
    return networkResponse;
  }).catch(() => {
    // Ignore network errors
  });
  
  // Return cached response immediately if available
  if (cachedResponse) {
    return cachedResponse;
  }
  
  // Otherwise wait for network
  return fetchPromise;
}

// Background sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync triggered:', event.tag);
  
  if (event.tag === MEDIA_SYNC_TAG) {
    event.waitUntil(processMediaQueue());
  } else if (event.tag === TASK_SYNC_TAG) {
    event.waitUntil(processTaskQueue());
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
