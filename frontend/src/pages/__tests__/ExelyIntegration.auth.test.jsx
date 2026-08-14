import { describe, expect, it } from 'vitest';

import {
  buildExelyRequestConfig,
  getExelyErrorMessage,
  parseExelyConnectionTestResult,
} from '@/pages/ExelyIntegration';

describe('ExelyIntegration request authentication', () => {
  it('uses the HttpOnly cookie session when the canonical user has no token', () => {
    expect(buildExelyRequestConfig({ role: 'super_admin' })).toEqual({});
  });

  it('preserves the explicit token fallback when one is available', () => {
    expect(buildExelyRequestConfig({ access_token: 'test-access-token' })).toEqual({
      headers: { Authorization: 'Bearer test-access-token' },
    });
  });

  it('reports the safe error type returned by the canonical test endpoint', () => {
    expect(parseExelyConnectionTestResult({
      success: false,
      connected: false,
      error_type: 'EXELY_PRODUCTION_DISABLED',
    })).toEqual({
      connected: false,
      durationMs: 0,
      errorCode: 'EXELY_PRODUCTION_DISABLED',
    });
  });

  it('keeps structured block codes and does not stringify response payloads', () => {
    expect(getExelyErrorMessage({
      response: { data: { detail: { error_code: 'EXELY_RESERVATION_SYNC_DISABLED' } } },
    }, 'fallback')).toBe('EXELY_RESERVATION_SYNC_DISABLED');

    expect(getExelyErrorMessage({
      response: { data: { detail: { payload: 'must-not-be-rendered' } } },
    }, 'fallback')).toBe('fallback');
  });
});
