import { describe, expect, it } from 'vitest';

import {
  buildChannelConnectionsRequestConfig,
  getChannelConnectionsErrorMessage,
} from '@/pages/ChannelConnections';

describe('ChannelConnections request authentication', () => {
  it('uses the HttpOnly cookie session when the canonical user has no token', () => {
    expect(buildChannelConnectionsRequestConfig({ role: 'super_admin' })).toEqual({});
  });

  it('preserves the explicit token fallback when one is available', () => {
    expect(buildChannelConnectionsRequestConfig({ access_token: 'test-access-token' })).toEqual({
      headers: { Authorization: 'Bearer test-access-token' },
    });
  });

  it('returns only a safe structured code instead of the provider payload', () => {
    expect(getChannelConnectionsErrorMessage({
      response: { data: { detail: { error_code: 'CHANNEL_CONNECTION_FORBIDDEN', payload: 'sensitive' } } },
    })).toBe('CHANNEL_CONNECTION_FORBIDDEN');

    expect(getChannelConnectionsErrorMessage({
      response: { data: { detail: { payload: 'sensitive' } } },
    })).toBe('Bağlantı durumu alınamadı');
  });
});
