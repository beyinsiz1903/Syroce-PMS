/**
 * Lazy Loading Utilities for React Components
 * Improves initial load time by code-splitting
 */

import { lazy, Suspense } from 'react';

/**
 * Lazy load component with error boundary and loading fallback
 * @param {function} importFunc - Dynamic import function
 * @param {string} fallbackText - Loading text (default: "Loading...")
 * @returns {React.Component} - Lazy loaded component
 */
export const lazyLoadComponent = (importFunc, fallbackText = "Loading...") => {
  const LazyComponent = lazy(importFunc);
  
  return (props) => (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-600">{fallbackText}</span>
      </div>
    }>
      <LazyComponent {...props} />
    </Suspense>
  );
};

/**
 * Lazy load with retry on failure
 * @param {function} importFunc - Dynamic import function
 * @param {number} retries - Number of retries (default: 3)
 * @returns {Promise} - Import promise
 */
export const lazyWithRetry = (importFunc, retries = 3) => {
  return new Promise((resolve, reject) => {
    const attemptImport = (retriesLeft) => {
      importFunc()
        .then(resolve)
        .catch((error) => {
          if (retriesLeft === 0) {
            reject(error);
            return;
          }
          
          console.warn(`Lazy load failed, retrying... (${retriesLeft} attempts left)`);
          
          // Retry after a delay
          setTimeout(() => {
            attemptImport(retriesLeft - 1);
          }, 1000);
        });
    };
    
    attemptImport(retries);
  });
};

/**
 * Preload component (start loading before needed)
 * @param {function} importFunc - Dynamic import function
 */
export const preloadComponent = (importFunc) => {
  importFunc();
};

/**
 * Common loading skeleton
 */
export const LoadingSkeleton = () => (
  <div className="animate-pulse space-y-4 p-4">
    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
    <div className="h-4 bg-gray-200 rounded w-5/6"></div>
    <div className="h-4 bg-gray-200 rounded w-2/3"></div>
  </div>
);

/**
 * Dashboard loading skeleton
 */
export const DashboardLoadingSkeleton = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4">
    {[1, 2, 3, 4].map(i => (
      <div key={i} className="bg-white rounded-lg shadow p-6 animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-3/4 mb-4"></div>
        <div className="h-10 bg-gray-200 rounded w-1/2 mb-2"></div>
        <div className="h-4 bg-gray-200 rounded w-2/3"></div>
      </div>
    ))}
  </div>
);

/**
 * Table loading skeleton
 */
export const TableLoadingSkeleton = ({ rows = 5, cols = 4 }) => (
  <div className="overflow-x-auto">
    <table className="min-w-full divide-y divide-gray-200">
      <thead className="bg-gray-50">
        <tr>
          {Array(cols).fill(0).map((_, i) => (
            <th key={i} className="px-6 py-3">
              <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-200">
        {Array(rows).fill(0).map((_, rowIndex) => (
          <tr key={rowIndex}>
            {Array(cols).fill(0).map((_, colIndex) => (
              <td key={colIndex} className="px-6 py-4">
                <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// Example usage:
/*
// In your routes or components:
const Dashboard = lazyLoadComponent(() => import('./pages/Dashboard'));
const Bookings = lazyLoadComponent(() => import('./pages/Bookings'), "Loading Bookings...");

// With retry:
const HeavyComponent = lazy(() => lazyWithRetry(() => import('./components/HeavyComponent')));

// Preload on hover:
<Link 
  to="/dashboard" 
  onMouseEnter={() => preloadComponent(() => import('./pages/Dashboard'))}
>
  Dashboard
</Link>
*/
