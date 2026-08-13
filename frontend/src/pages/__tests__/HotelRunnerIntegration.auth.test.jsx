import { describe, expect, it } from 'vitest';

import { buildHotelRunnerRequestConfig } from '@/pages/HotelRunnerIntegration';

describe('HotelRunnerIntegration request authentication', () => {
  it('uses the HttpOnly cookie session when the canonical user has no token', () => {
    expect(buildHotelRunnerRequestConfig({ role: 'super_admin' })).toEqual({});
  });

  it('preserves the explicit token fallback when one is available', () => {
    expect(buildHotelRunnerRequestConfig({ access_token: 'test-access-token' })).toEqual({
      headers: { Authorization: 'Bearer test-access-token' },
    });
  });
});
