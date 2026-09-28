import axios from 'axios';

import { queryClient } from '@/lib/queryClient';

const FRESH_FOR_MS = 60_000;
const KEEP_FOR_MS = 10 * 60_000;

export const adminManagementQueryKeys = {
  tenants: ['admin-management', 'tenants'],
  agencies: ['admin-management', 'agencies'],
};

export const adminManagementQueries = {
  tenants: {
    queryKey: adminManagementQueryKeys.tenants,
    queryFn: () => axios.get('/admin/tenants').then((response) => response.data),
    staleTime: FRESH_FOR_MS,
    gcTime: KEEP_FOR_MS,
  },
  agencies: {
    queryKey: adminManagementQueryKeys.agencies,
    queryFn: () => axios.get('/marketplace/v1/admin/agencies').then((response) => response.data),
    staleTime: FRESH_FOR_MS,
    gcTime: KEEP_FOR_MS,
  },
};

export function prefetchAdminManagementRoute(path) {
  const query = path === '/admin/tenants'
    ? adminManagementQueries.tenants
    : path === '/admin/agencies'
      ? adminManagementQueries.agencies
      : null;

  if (!query) return undefined;
  return queryClient.prefetchQuery(query);
}
