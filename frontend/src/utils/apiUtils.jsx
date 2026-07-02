/**
 * API Utilities with Caching Support
 * Optimized fetch with built-in caching
 */

import { getCache, setCache } from './cacheUtils';

const API_BASE_URL = '/api';

/**
 * Fetch with cache support
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @param {object} cacheOptions - Cache options { enabled, ttl, key }
 * @returns {Promise<any>} - API response
 */
export const fetchWithCache = async (endpoint, options = {}, cacheOptions = {}) => {
  const {
    enabled = true,
    ttl = 5 * 60 * 1000, // 5 minutes default
    key = null
  } = cacheOptions;
  
  // Generate cache key
  const cacheKey = key || `${endpoint}_${JSON.stringify(options)}`;
  
  // Try to get from cache if enabled and GET request
  if (enabled && (!options.method || options.method === 'GET')) {
    const cached = getCache(cacheKey);
    if (cached) {
      if (import.meta.env.DEV) console.log(`Cache hit: ${endpoint}`);
      return cached;
    }
  }
  
  // Fetch from API
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    const data = await response.json();
    
    // Cache response if enabled and GET request
    if (enabled && (!options.method || options.method === 'GET')) {
      setCache(cacheKey, data, ttl);
      if (import.meta.env.DEV) console.log(`Cached: ${endpoint}`);
    }
    
    return data;
  } catch (error) {
    console.error(`API fetch failed: ${endpoint}`, error);
    throw error;
  }
};

/**
 * Cached Dashboard API calls
 */
export const dashboardAPI = {
  getPMSDashboard: () => fetchWithCache(
    '/pms/dashboard',
    {},
    { enabled: true, ttl: 5 * 60 * 1000, key: 'pms_dashboard' }
  ),

  getRoomStatus: () => fetchWithCache(
    '/housekeeping/room-status',
    {},
    { enabled: true, ttl: 1 * 60 * 1000, key: 'room_status' }
  ),

  getRoleBasedDashboard: () => fetchWithCache(
    '/dashboard/role-based',
    {},
    { enabled: true, ttl: 5 * 60 * 1000, key: 'role_dashboard' }
  ),

  getEmployeePerformance: (params = {}) => fetchWithCache(
    `/dashboard/employee-performance?${new URLSearchParams(params)}`,
    {},
    { enabled: true, ttl: 10 * 60 * 1000, key: `employee_performance_${JSON.stringify(params)}` }
  ),

  getGuestSatisfaction: (days = 30) => fetchWithCache(
    `/dashboard/guest-satisfaction-trends?days=${days}`,
    {},
    { enabled: true, ttl: 10 * 60 * 1000, key: `guest_satisfaction_${days}` }
  ),

  getFinanceDashboard: () => fetchWithCache(
    '/department/finance/dashboard',
    {},
    { enabled: true, ttl: 5 * 60 * 1000, key: 'finance_dashboard' }
  ),

  getFrontOfficeDashboard: () => fetchWithCache(
    '/department/front-office/dashboard',
    {},
    { enabled: true, ttl: 3 * 60 * 1000, key: 'front_office_dashboard' }
  ),

  getHousekeepingDashboard: () => fetchWithCache(
    '/department/housekeeping/dashboard',
    {},
    { enabled: true, ttl: 2 * 60 * 1000, key: 'housekeeping_dashboard' }
  ),

  getAccountingDashboard: () => fetchWithCache(
    '/accounting/dashboard',
    {},
    { enabled: true, ttl: 10 * 60 * 1000, key: 'accounting_dashboard' }
  )
};

/**
 * Request debouncing utility
 */
const debounceTimers = {};

export const debounce = (func, delay, key) => {
  return (...args) => {
    if (debounceTimers[key]) {
      clearTimeout(debounceTimers[key]);
    }
    
    debounceTimers[key] = setTimeout(() => {
      func(...args);
      delete debounceTimers[key];
    }, delay);
  };
};

/**
 * Request throttling utility
 */
const throttleTimers = {};

export const throttle = (func, delay, key) => {
  return (...args) => {
    if (!throttleTimers[key]) {
      func(...args);
      throttleTimers[key] = true;
      
      setTimeout(() => {
        delete throttleTimers[key];
      }, delay);
    }
  };
};
