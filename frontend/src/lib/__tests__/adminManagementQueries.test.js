import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import { queryClient } from '@/lib/queryClient';
import { prefetchAdminManagementRoute } from '@/lib/adminManagementQueries';

vi.mock('axios');

describe('admin management navigation prefetch', () => {
  beforeEach(() => {
    queryClient.clear();
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { tenants: [], agencies: [] } });
  });

  it('warms each management dataset before navigation and reuses fresh data', async () => {
    await prefetchAdminManagementRoute('/admin/agencies');
    await prefetchAdminManagementRoute('/admin/agencies');
    await prefetchAdminManagementRoute('/admin/tenants');

    expect(axios.get.mock.calls).toEqual([
      ['/marketplace/v1/admin/agencies'],
      ['/admin/tenants'],
    ]);
  });

  it('ignores unrelated routes', () => {
    expect(prefetchAdminManagementRoute('/app/dashboard')).toBeUndefined();
    expect(axios.get).not.toHaveBeenCalled();
  });
});
