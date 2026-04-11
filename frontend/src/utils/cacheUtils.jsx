/**
 * Frontend Cache Utilities
 * LocalStorage-based caching for API responses
 */

const CACHE_PREFIX = 'hotel_pms_cache_';
const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes in milliseconds

/**
 * Set item in cache with TTL
 * @param {string} key - Cache key
 * @param {any} data - Data to cache
 * @param {number} ttl - Time to live in milliseconds
 */
export const setCache = (key, data, ttl = DEFAULT_TTL) => {
  try {
    const cacheKey = CACHE_PREFIX + key;
    const cacheData = {
      data,
      timestamp: Date.now(),
      ttl
    };
    localStorage.setItem(cacheKey, JSON.stringify(cacheData));
  } catch (error) {
    console.warn('Cache set failed:', error);
  }
};

/**
 * Get item from cache
 * @param {string} key - Cache key
 * @returns {any|null} - Cached data or null if expired/not found
 */
export const getCache = (key) => {
  try {
    const cacheKey = CACHE_PREFIX + key;
    const cached = localStorage.getItem(cacheKey);
    
    if (!cached) return null;
    
    const { data, timestamp, ttl } = JSON.parse(cached);
    const now = Date.now();
    
    // Check if expired
    if (now - timestamp > ttl) {
      localStorage.removeItem(cacheKey);
      return null;
    }
    
    return data;
  } catch (error) {
    console.warn('Cache get failed:', error);
    return null;
  }
};

/**
 * Clear specific cache key
 * @param {string} key - Cache key
 */
export const clearCache = (key) => {
  try {
    const cacheKey = CACHE_PREFIX + key;
    localStorage.removeItem(cacheKey);
  } catch (error) {
    console.warn('Cache clear failed:', error);
  }
};

/**
 * Clear all cache
 */
export const clearAllCache = () => {
  try {
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith(CACHE_PREFIX)) {
        localStorage.removeItem(key);
      }
    });
  } catch (error) {
    console.warn('Clear all cache failed:', error);
  }
};

/**
 * Clear expired cache entries
 */
export const clearExpiredCache = () => {
  try {
    const keys = Object.keys(localStorage);
    const now = Date.now();
    
    keys.forEach(key => {
      if (key.startsWith(CACHE_PREFIX)) {
        try {
          const cached = localStorage.getItem(key);
          const { timestamp, ttl } = JSON.parse(cached);
          
          if (now - timestamp > ttl) {
            localStorage.removeItem(key);
          }
        } catch (e) {
          // Invalid cache entry, remove it
          localStorage.removeItem(key);
        }
      }
    });
  } catch (error) {
    console.warn('Clear expired cache failed:', error);
  }
};

/**
 * Get cache statistics
 * @returns {object} - Cache stats
 */
export const getCacheStats = () => {
  try {
    const keys = Object.keys(localStorage);
    const cacheKeys = keys.filter(k => k.startsWith(CACHE_PREFIX));
    
    let totalSize = 0;
    let expiredCount = 0;
    const now = Date.now();
    
    cacheKeys.forEach(key => {
      try {
        const cached = localStorage.getItem(key);
        totalSize += cached.length;
        
        const { timestamp, ttl } = JSON.parse(cached);
        if (now - timestamp > ttl) {
          expiredCount++;
        }
      } catch (e) {
        // Ignore invalid entries
      }
    });
    
    return {
      total_keys: cacheKeys.length,
      expired_keys: expiredCount,
      total_size_kb: (totalSize / 1024).toFixed(2),
      storage_used_pct: ((totalSize / (5 * 1024 * 1024)) * 100).toFixed(2) // Assuming 5MB limit
    };
  } catch (error) {
    console.warn('Get cache stats failed:', error);
    return { error: error.message };
  }
};

// Clear expired cache on module load
clearExpiredCache();
