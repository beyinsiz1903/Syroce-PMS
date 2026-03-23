/**
 * React Query Configuration
 * Enterprise-level data fetching and caching
 */
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Stale time: How long data is considered fresh
      staleTime: 5 * 60 * 1000, // 5 minutes (L2 cache equivalent)
      
      // Cache time: How long unused data stays in cache
      cacheTime: 10 * 60 * 1000, // 10 minutes
      
      // Retry failed queries
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      
      // Refetch on window focus for critical data
      refetchOnWindowFocus: false, // Disable for now
      
      // Refetch on mount only if data is stale
      refetchOnMount: 'stale',
      
      // Keep previous data while fetching new data
      keepPreviousData: true,
      
      // Don't refetch on reconnect by default
      refetchOnReconnect: false,
    },
    mutations: {
      // Retry failed mutations once
      retry: 1,
    },
  },
});

/**
 * Query key factory for consistent cache keys
 */
export const queryKeys = {
  // Dashboard
  dashboard: {
    all: ['dashboard'],
    metrics: () => [...queryKeys.dashboard.all, 'metrics'],
    trends: () => [...queryKeys.dashboard.all, 'trends'],
    flash: () => [...queryKeys.dashboard.all, 'flash'],
  },
  
  // PMS
  pms: {
    all: ['pms'],
    rooms: (filters) => [...queryKeys.pms.all, 'rooms', filters],
    guests: (filters) => [...queryKeys.pms.all, 'guests', filters],
    bookings: (filters) => [...queryKeys.pms.all, 'bookings', filters],
    arrivals: () => [...queryKeys.pms.all, 'arrivals'],
    departures: () => [...queryKeys.pms.all, 'departures'],
    inhouse: () => [...queryKeys.pms.all, 'inhouse'],
  },
  
  // Housekeeping
  housekeeping: {
    all: ['housekeeping'],
    tasks: (filters) => [...queryKeys.housekeeping.all, 'tasks', filters],
    roomStatus: () => [...queryKeys.housekeeping.all, 'status'],
  },
  
  // Finance
  finance: {
    all: ['finance'],
    snapshot: () => [...queryKeys.finance.all, 'snapshot'],
    folios: (bookingId) => [...queryKeys.finance.all, 'folios', bookingId],
    expenses: (period) => [...queryKeys.finance.all, 'expenses', period],
  },
  
  // Reports
  reports: {
    all: ['reports'],
    occupancy: (period) => [...queryKeys.reports.all, 'occupancy', period],
    revenue: (period) => [...queryKeys.reports.all, 'revenue', period],
    dailyFlash: (date) => [...queryKeys.reports.all, 'daily-flash', date],
  },
};

/**
 * Cache invalidation helpers
 */
export const invalidateQueries = {
  dashboard: () => queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
  pms: () => queryClient.invalidateQueries({ queryKey: queryKeys.pms.all }),
  housekeeping: () => queryClient.invalidateQueries({ queryKey: queryKeys.housekeeping.all }),
  finance: () => queryClient.invalidateQueries({ queryKey: queryKeys.finance.all }),
  reports: () => queryClient.invalidateQueries({ queryKey: queryKeys.reports.all }),
  all: () => queryClient.invalidateQueries(),
};

/**
 * Prefetch helpers for faster navigation
 */
export const prefetchQueries = {
  dashboard: async (axios) => {
    await queryClient.prefetchQuery({
      queryKey: queryKeys.dashboard.metrics(),
      queryFn: () => axios.get('/pms/dashboard').then(res => res.data),
      staleTime: 5 * 60 * 1000,
    });
  },
  
  pms: async (axios) => {
    await Promise.all([
      queryClient.prefetchQuery({
        queryKey: queryKeys.pms.rooms({}),
        queryFn: () => axios.get('/pms/rooms').then(res => res.data),
      }),
      queryClient.prefetchQuery({
        queryKey: queryKeys.pms.arrivals(),
        queryFn: () => axios.get('/frontdesk/arrivals').then(res => res.data),
      }),
    ]);
  },
};
