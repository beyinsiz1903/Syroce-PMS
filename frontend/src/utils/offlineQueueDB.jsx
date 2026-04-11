/**
 * Offline Queue & Notification Log (IndexedDB)
 * Stores pending media uploads / task updates while the app is offline.
 */

const DB_NAME = 'RoomOpsOffline';
const DB_VERSION = 1;

const STORES = {
  MEDIA_QUEUE: 'mediaQueue',
  TASK_QUEUE: 'taskQueue',
  NOTIFICATION_LOG: 'notificationLog'
};

class OfflineDB {
  constructor() {
    this.db = null;
    this.initPromise = this.init();
  }

  init() {
    return new Promise((resolve, reject) => {
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
  logNotification,
  listNotifications,
  clearNotification
};
