/**
 * IndexedDB Cache Manager
 * Persistent client-side caching for faster page loads
 */

const DB_NAME = 'HotelPMSCache';
const DB_VERSION = 1;
const STORE_NAME = 'apiCache';

class CacheDB {
  constructor() {
    this.db = null;
    this.initPromise = this.init();
  }

  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'key' });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
    });
  }

  async get(key) {
    try {
      await this.initPromise;
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.get(key);

        request.onsuccess = () => {
          const result = request.result;
          if (!result) {
            resolve(null);
            return;
          }

          // Check if expired
          const now = Date.now();
          if (result.expiry && result.expiry < now) {
            // Delete expired entry
            this.delete(key);
            resolve(null);
            return;
          }

          resolve(result.data);
        };

        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('IndexedDB get error:', error);
      return null;
    }
  }

  async set(key, data, ttl = 300000) {
    // ttl in milliseconds (default 5 min)
    try {
      await this.initPromise;
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.put({
          key,
          data,
          timestamp: Date.now(),
          expiry: Date.now() + ttl
        });

        request.onsuccess = () => resolve(true);
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('IndexedDB set error:', error);
      return false;
    }
  }

  async delete(key) {
    try {
      await this.initPromise;
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.delete(key);

        request.onsuccess = () => resolve(true);
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('IndexedDB delete error:', error);
      return false;
    }
  }

  async clear() {
    try {
      await this.initPromise;
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.clear();

        request.onsuccess = () => resolve(true);
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('IndexedDB clear error:', error);
      return false;
    }
  }

  async cleanExpired() {
    try {
      await this.initPromise;
      const transaction = this.db.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const index = store.index('timestamp');
      const now = Date.now();

      const request = index.openCursor();
      request.onsuccess = (event) => {
        const cursor = event.target.result;
        if (cursor) {
          if (cursor.value.expiry < now) {
            store.delete(cursor.value.key);
          }
          cursor.continue();
        }
      };
    } catch (error) {
      console.error('IndexedDB clean error:', error);
    }
  }
}

// Create singleton instance
const cacheDB = new CacheDB();

// Clean expired entries every 5 minutes
setInterval(() => {
  cacheDB.cleanExpired();
}, 300000);

export default cacheDB;
