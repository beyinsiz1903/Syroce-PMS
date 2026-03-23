/**
 * Custom Hook for PMS Data with React Query
 * Optimized data fetching for PMS module
 */
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { queryKeys } from '@/lib/queryClient';
import { toast } from 'sonner';

/**
 * Hook for fetching rooms
 */
export const useRooms = (filters = {}) => {
  return useQuery({
    queryKey: queryKeys.pms.rooms(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const response = await axios.get(`/pms/rooms?${params}`);
      return response.data;
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });
};

/**
 * Hook for fetching guests
 */
export const useGuests = (filters = { limit: 100 }) => {
  return useQuery({
    queryKey: queryKeys.pms.guests(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const response = await axios.get(`/pms/guests?${params}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 15 * 60 * 1000, // 15 minutes
  });
};

/**
 * Hook for fetching bookings with pagination
 */
export const useBookings = (filters = { limit: 100 }) => {
  return useQuery({
    queryKey: queryKeys.pms.bookings(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const response = await axios.get(`/pms/bookings?${params}`);
      return response.data;
    },
    staleTime: 1 * 60 * 1000, // 1 minute (more dynamic)
    cacheTime: 5 * 60 * 1000, // 5 minutes
    keepPreviousData: true, // For pagination
  });
};

/**
 * Hook for fetching arrivals, departures, in-house
 */
export const useFrontDeskData = () => {
  const queries = useQueries({
    queries: [
      {
        queryKey: queryKeys.pms.arrivals(),
        queryFn: () => axios.get('/frontdesk/arrivals').then(res => res.data),
        staleTime: 2 * 60 * 1000,
      },
      {
        queryKey: queryKeys.pms.departures(),
        queryFn: () => axios.get('/frontdesk/departures').then(res => res.data),
        staleTime: 2 * 60 * 1000,
      },
      {
        queryKey: queryKeys.pms.inhouse(),
        queryFn: () => axios.get('/frontdesk/inhouse').then(res => res.data),
        staleTime: 2 * 60 * 1000,
      },
    ],
  });

  return {
    arrivals: queries[0],
    departures: queries[1],
    inhouse: queries[2],
    isLoading: queries.some(q => q.isLoading),
    isError: queries.some(q => q.isError),
  };
};

/**
 * Hook for creating a booking
 */
export const useCreateBooking = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (bookingData) => {
      const response = await axios.post('/pms/bookings', bookingData);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate and refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.bookings({}) });
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.arrivals() });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
      toast.success('Booking created successfully');
    },
    onError: (error) => {
      toast.error(`Failed to create booking: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for updating a booking
 */
export const useUpdateBooking = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }) => {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `booking-update-${Date.now()}-${Math.random()}`;
      const response = await axios.put(`/pms/bookings/${id}`, data, {
        headers: {
          'Idempotency-Key': idempotencyKey,
        },
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.bookings({}) });
      toast.success('Booking updated successfully');
    },
    onError: (error) => {
      toast.error(`Failed to update booking: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for check-in
 */
export const useCheckIn = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (bookingId) => {
      const response = await axios.post(`/frontdesk/checkin/${bookingId}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
      toast.success('Check-in completed successfully');
    },
    onError: (error) => {
      toast.error(`Check-in failed: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for check-out
 */
export const useCheckOut = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (bookingId) => {
      const response = await axios.post(`/frontdesk/checkout/${bookingId}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.finance.all });
      toast.success('Check-out completed successfully');
    },
    onError: (error) => {
      toast.error(`Check-out failed: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for creating a guest
 */
export const useCreateGuest = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (guestData) => {
      const response = await axios.post('/pms/guests', guestData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.guests({}) });
      toast.success('Guest created successfully');
    },
    onError: (error) => {
      toast.error(`Failed to create guest: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for creating a room
 */
export const useCreateRoom = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (roomData) => {
      const response = await axios.post('/pms/rooms', roomData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pms.rooms({}) });
      toast.success('Room created successfully');
    },
    onError: (error) => {
      toast.error(`Failed to create room: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for housekeeping tasks
 */
export const useHousekeepingTasks = (filters = {}) => {
  return useQuery({
    queryKey: queryKeys.housekeeping.tasks(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const response = await axios.get(`/housekeeping/tasks?${params}`);
      return response.data;
    },
    staleTime: 1 * 60 * 1000, // 1 minute
    cacheTime: 5 * 60 * 1000,
  });
};

/**
 * Hook for creating housekeeping task
 */
export const useCreateHousekeepingTask = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (taskData) => {
      const response = await axios.post('/housekeeping/tasks', taskData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.housekeeping.all });
      toast.success('Housekeeping task created');
    },
    onError: (error) => {
      toast.error(`Failed to create task: ${error.response?.data?.detail || error.message}`);
    },
  });
};

/**
 * Hook for prefetching PMS data
 */
export const usePrefetchPMS = () => {
  const queryClient = useQueryClient();

  const prefetchAll = async () => {
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
  };

  return { prefetchAll };
};
