/**
 * Offline Queue & Notification Log (IndexedDB)
 * Stores pending media uploads / task updates while the app is offline.
 */

const DB_NAME = 'SyroceOffline';
// v2: çevrimdışı check-in kuyruğu (checkinQueue) eklendi. SW ile ortak DB
// olduğundan iki taraf da aynı versiyonu açmalı (frontend/public/service-worker.js).
const DB_VERSION = 2;

const STORES = {
  MEDIA_QUEUE: 'mediaQueue',
  TASK_QUEUE: 'taskQueue',
  NOTIFICATION_LOG: 'notificationLog',
  CHECKIN_QUEUE: 'checkinQueue'
};

class OfflineDB {
  constructor() {
    this.db = null;
    // IndexedDB yoksa (SSR / test ortami) cokmeyi onle: initPromise reject
    // olursa bile islenmemis-rejection uretmemesi icin sessiz catch ekle.
    this.initPromise = this.init();
    this.initPromise.catch(() => {});
  }

  init() {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB unavailable'));
        return;
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        if (!db.objectStoreNames.contains(STORES.MEDIA_QUEUE)) {
          const mediaStore = db.createObjectStore(STORES.MEDIA_QUEUE, { keyPath: 'id' });
          mediaStore.createIndex('createdAt', 'createdAt', { unique: false });
        }

        if (!db.objectStoreNames.contains(STORES.TASK_QUEUE)) {
          const taskStore = db.createObjectStore(STORES.TASK_QUEUE, { keyPath: 'id' });
          taskStore.createIndex('createdAt', 'createdAt', { unique: false });
        }

        if (!db.objectStoreNames.contains(STORES.NOTIFICATION_LOG)) {
          const notifStore = db.createObjectStore(STORES.NOTIFICATION_LOG, { keyPath: 'id' });
          notifStore.createIndex('createdAt', 'createdAt', { unique: false });
        }

        if (!db.objectStoreNames.contains(STORES.CHECKIN_QUEUE)) {
          const checkinStore = db.createObjectStore(STORES.CHECKIN_QUEUE, { keyPath: 'id' });
          checkinStore.createIndex('createdAt', 'createdAt', { unique: false });
        }
      };
    });
  }

  async withStore(storeName, mode, callback) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([storeName], mode);
      const store = tx.objectStore(storeName);
      const result = callback(store);

      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
    });
  }

  async add(storeName, entry) {
    const record = {
      ...entry,
      id: entry.id || crypto.randomUUID(),
      createdAt: entry.createdAt || Date.now(),
      updatedAt: Date.now()
    };

    return this.withStore(storeName, 'readwrite', (store) => store.put(record));
  }

  async remove(storeName, id) {
    return this.withStore(storeName, 'readwrite', (store) => store.delete(id));
  }

  async get(storeName, id) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([storeName], 'readonly');
      const store = tx.objectStore(storeName);
      const request = store.get(id);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async update(storeName, id, patch) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([storeName], 'readwrite');
      const store = tx.objectStore(storeName);
      const getReq = store.get(id);
      getReq.onsuccess = () => {
        const existing = getReq.result;
        if (!existing) {
          resolve(null);
          return;
        }
        const merged = { ...existing, ...patch, updatedAt: Date.now() };
        store.put(merged);
        resolve(merged);
      };
      getReq.onerror = () => reject(getReq.error);
    });
  }

  async count(storeName) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([storeName], 'readonly');
      const store = tx.objectStore(storeName);
      const request = store.count();
      request.onsuccess = () => resolve(request.result || 0);
      request.onerror = () => reject(request.error);
    });
  }

  async list(storeName, limit = 100) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([storeName], 'readonly');
      const store = tx.objectStore(storeName);
      const index = store.index('createdAt');
      const request = index.openCursor(null, 'next');
      const items = [];

      request.onsuccess = (event) => {
        const cursor = event.target.result;
        if (cursor && items.length < limit) {
          items.push(cursor.value);
          cursor.continue();
        } else {
          resolve(items);
        }
      };

      request.onerror = () => reject(request.error);
    });
  }
}

const offlineDB = new OfflineDB();

// Media Queue helpers
export async function enqueueMediaUpload(entry) {
  return offlineDB.add(STORES.MEDIA_QUEUE, entry);
}

export async function listQueuedMedia(limit = 50) {
  return offlineDB.list(STORES.MEDIA_QUEUE, limit);
}

export async function removeQueuedMedia(id) {
  return offlineDB.remove(STORES.MEDIA_QUEUE, id);
}

// Task queue helpers (general purpose)
export async function enqueueTaskUpdate(entry) {
  return offlineDB.add(STORES.TASK_QUEUE, entry);
}

export async function listQueuedTasks(limit = 100) {
  return offlineDB.list(STORES.TASK_QUEUE, limit);
}

export async function removeQueuedTask(id) {
  return offlineDB.remove(STORES.TASK_QUEUE, id);
}

// Check-in queue helpers (çevrimdışı ön büro girişleri)
export async function enqueueCheckin(entry) {
  return offlineDB.add(STORES.CHECKIN_QUEUE, entry);
}

export async function listQueuedCheckins(limit = 200) {
  return offlineDB.list(STORES.CHECKIN_QUEUE, limit);
}

export async function getQueuedCheckin(id) {
  return offlineDB.get(STORES.CHECKIN_QUEUE, id);
}

export async function updateQueuedCheckin(id, patch) {
  return offlineDB.update(STORES.CHECKIN_QUEUE, id, patch);
}

export async function removeQueuedCheckin(id) {
  return offlineDB.remove(STORES.CHECKIN_QUEUE, id);
}

export async function countQueuedCheckins() {
  return offlineDB.count(STORES.CHECKIN_QUEUE);
}

// Notification log
export async function logNotification(event) {
  return offlineDB.add(STORES.NOTIFICATION_LOG, event);
}

export async function listNotifications(limit = 100) {
  return offlineDB.list(STORES.NOTIFICATION_LOG, limit);
}

export async function clearNotification(id) {
  return offlineDB.remove(STORES.NOTIFICATION_LOG, id);
}

export default {
  enqueueMediaUpload,
  listQueuedMedia,
  removeQueuedMedia,
  enqueueTaskUpdate,
  listQueuedTasks,
  removeQueuedTask,
  enqueueCheckin,
  listQueuedCheckins,
  getQueuedCheckin,
  updateQueuedCheckin,
  removeQueuedCheckin,
  countQueuedCheckins,
  logNotification,
  listNotifications,
  clearNotification
};
