/**
 * Performance Utilities
 * Debouncing, throttling, and other optimization helpers
 */

/**
 * Debounce function execution
 * Use for: Search inputs, form validation, resize/scroll handlers
 * 
 * @param {Function} func - Function to debounce
 * @param {number} wait - Delay in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait = 300) {
  let timeout;
  
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Throttle function execution
 * Use for: Scroll handlers, mouse move, window resize
 * 
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time limit in milliseconds
 * @returns {Function} Throttled function
 */
export function throttle(func, limit = 300) {
  let inThrottle;
  
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

/**
 * Request Animation Frame throttle
 * Use for: Smooth animations and scroll effects
 * 
 * @param {Function} func - Function to throttle
 * @returns {Function} RAF throttled function
 */
export function rafThrottle(func) {
  let rafId = null;
  
  return function executedFunction(...args) {
    if (rafId) return;
    
    rafId = requestAnimationFrame(() => {
      func(...args);
      rafId = null;
    });
  };
}

/**
 * Lazy load images with Intersection Observer
 * 
 * @param {HTMLElement} element - Image element to lazy load
 * @param {Object} options - Intersection Observer options
 */
export function lazyLoadImage(element, options = {}) {
  const defaultOptions = {
    root: null,
    rootMargin: '50px',
    threshold: 0.01,
  };

  const observer = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        const src = img.dataset.src;
        
        if (src) {
          img.src = src;
          img.removeAttribute('data-src');
          obs.unobserve(img);
        }
      }
    });
  }, { ...defaultOptions, ...options });

  observer.observe(element);
  return observer;
}

/**
 * Batch multiple state updates
 * React 18 automatic batching helper for older patterns
 * 
 * @param {Function} callback - Function containing state updates
 */
export function batchUpdates(callback) {
  // In React 18, batching is automatic
  // This is kept for compatibility
  callback();
}

/**
 * Measure component render time
 * Use for development/debugging
 * 
 * @param {string} componentName - Name of component
 * @returns {Object} Performance helpers
 */
export function measurePerformance(componentName) {
  const startTime = performance.now();
  
  return {
    end: () => {
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      if (duration > 16) { // More than one frame (60fps)
        console.warn(`⚠️ ${componentName} render took ${duration.toFixed(2)}ms`);
      } else {
        console.log(`✅ ${componentName} render took ${duration.toFixed(2)}ms`);
      }
      
      return duration;
    },
  };
}

/**
 * Virtual scroll helper
 * Calculate visible items in a scrollable container
 * 
 * @param {Object} params - Scroll parameters
 * @returns {Object} Visible range
 */
export function calculateVisibleRange({
  scrollTop,
  containerHeight,
  itemHeight,
  totalItems,
  overscan = 3,
}) {
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(
    totalItems - 1,
    Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan
  );

  return { startIndex, endIndex };
}

/**
 * Memoization helper for expensive computations
 * 
 * @param {Function} fn - Function to memoize
 * @returns {Function} Memoized function
 */
export function memoize(fn) {
  const cache = new Map();
  
  return function memoized(...args) {
    const key = JSON.stringify(args);
    
    if (cache.has(key)) {
      return cache.get(key);
    }
    
    const result = fn(...args);
    cache.set(key, result);
    
    // Clear cache if it gets too large
    if (cache.size > 100) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }
    
    return result;
  };
}

/**
 * Detect slow network connection
 * 
 * @returns {boolean} True if connection is slow
 */
export function isSlowConnection() {
  if (!navigator.connection) return false;
  
  const connection = navigator.connection;
  const slowTypes = ['slow-2g', '2g'];
  
  return (
    slowTypes.includes(connection.effectiveType) ||
    connection.saveData === true ||
    connection.downlink < 1
  );
}

/**
 * Prefetch data on hover
 * Use for: Links, buttons that load data
 * 
 * @param {Function} prefetchFn - Function to call on hover
 * @param {number} delay - Delay before prefetch (ms)
 * @returns {Object} Event handlers
 */
export function createPrefetchHandlers(prefetchFn, delay = 100) {
  let timeoutId = null;
  let prefetched = false;
  
  return {
    onMouseEnter: () => {
      if (prefetched) return;
      
      timeoutId = setTimeout(() => {
        prefetchFn();
        prefetched = true;
      }, delay);
    },
    onMouseLeave: () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    },
    onFocus: () => {
      if (!prefetched) {
        prefetchFn();
        prefetched = true;
      }
    },
  };
}

/**
 * Check if element is in viewport
 * 
 * @param {HTMLElement} element - Element to check
 * @returns {boolean} True if in viewport
 */
export function isInViewport(element) {
  const rect = element.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
  );
}

/**
 * Format large numbers for display
 * Use for: Revenue, counts, statistics
 * 
 * @param {number} num - Number to format
 * @returns {string} Formatted number
 */
export function formatLargeNumber(num) {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`;
  }
  return num.toString();
}

/**
 * Cache API responses in memory
 */
class MemoryCache {
  constructor(maxSize = 50) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  set(key, value, ttl = 300000) { // 5 minutes default
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }

    this.cache.set(key, {
      value,
      expires: Date.now() + ttl,
    });
  }

  get(key) {
    const item = this.cache.get(key);
    
    if (!item) return null;
    
    if (Date.now() > item.expires) {
      this.cache.delete(key);
      return null;
    }
    
    return item.value;
  }

  clear() {
    this.cache.clear();
  }

  has(key) {
    return this.cache.has(key);
  }
}

export const memoryCache = new MemoryCache();
