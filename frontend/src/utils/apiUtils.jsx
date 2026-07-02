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
  /**
   * Get PMS Dashboard
   */
  getPMSDashboard: (token) => fetchWithCache(
    '/pms/dashboard',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 5 * 60 * 1000, key: 'pms_dashboard' }
  ),
  
  /**
   * Get Housekeeping Room Status
   */
  getRoomStatus: (token) => fetchWithCache(
    '/housekeeping/room-status',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 1 * 60 * 1000, key: 'room_status' } // 1 minute for real-time data
  ),
  
  /**
   * Get Role-based Dashboard
   */
  getRoleBasedDashboard: (token) => fetchWithCache(
    '/dashboard/role-based',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 5 * 60 * 1000, key: 'role_dashboard' }
  ),
  
  /**
   * Get Employee Performance
   */
  getEmployeePerformance: (token, params = {}) => fetchWithCache(
    `/dashboard/employee-performance?${new URLSearchParams(params)}`,
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 10 * 60 * 1000, key: `employee_performance_${JSON.stringify(params)}` }
  ),
  
  /**
   * Get Guest Satisfaction Trends
   */
  getGuestSatisfaction: (token, days = 30) => fetchWithCache(
    `/dashboard/guest-satisfaction-trends?days=${days}`,
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 10 * 60 * 1000, key: `guest_satisfaction_${days}` }
  ),
  
  /**
   * Get Finance Dashboard
   */
  getFinanceDashboard: (token) => fetchWithCache(
    '/department/finance/dashboard',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 5 * 60 * 1000, key: 'finance_dashboard' }
  ),
  
  /**
   * Get Front Office Dashboard
   */
  getFrontOfficeDashboard: (token) => fetchWithCache(
    '/department/front-office/dashboard',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 3 * 60 * 1000, key: 'front_office_dashboard' }
  ),
  
  /**
   * Get Housekeeping Dashboard
   */
  getHousekeepingDashboard: (token) => fetchWithCache(
    '/department/housekeeping/dashboard',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
    { enabled: true, ttl: 2 * 60 * 1000, key: 'housekeeping_dashboard' }
  ),
  
  /**
   * Get Accounting Dashboard
   */
  getAccountingDashboard: (token) => fetchWithCache(
    '/accounting/dashboard',
    {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    },
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
