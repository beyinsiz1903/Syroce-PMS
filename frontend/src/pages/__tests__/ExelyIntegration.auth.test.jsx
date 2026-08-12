import { describe, expect, it } from 'vitest';

import { buildExelyRequestConfig } from '@/pages/ExelyIntegration';

describe('ExelyIntegration request authentication', () => {
  it('uses the HttpOnly cookie session when the canonical user has no token', () => {
    expect(buildExelyRequestConfig({ role: 'super_admin' })).toEqual({});
  });

  it('preserves the explicit token fallback when one is available', () => {
    expect(buildExelyRequestConfig({ access_token: 'test-access-token' })).toEqual({
      headers: { Authorization: 'Bearer test-access-token' },
    });
  });
});
