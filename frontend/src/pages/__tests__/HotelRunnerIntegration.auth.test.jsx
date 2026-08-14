import { describe, expect, it } from 'vitest';

import {
  buildHotelRunnerRequestConfig,
  getHotelRunnerErrorMessage,
  parseHotelRunnerConnectionTestResult,
} from '@/pages/HotelRunnerIntegration';

describe('HotelRunnerIntegration request authentication', () => {
  it('uses the HttpOnly cookie session when the canonical user has no token', () => {
    expect(buildHotelRunnerRequestConfig({ role: 'super_admin' })).toEqual({});
  });

  it('preserves the explicit token fallback when one is available', () => {
    expect(buildHotelRunnerRequestConfig({ access_token: 'test-access-token' })).toEqual({
      headers: { Authorization: 'Bearer test-access-token' },
    });
  });

  it('recognizes the canonical provider result returned by the backend', () => {
    expect(parseHotelRunnerConnectionTestResult({
      success: true,
      data: { connected: true },
      duration_ms: 42,
    })).toEqual({
      connected: true,
      durationMs: 42,
      errorCode: 'CONNECTION_TEST_FAILED',
    });
  });

  it('keeps structured block codes and does not stringify response payloads', () => {
    expect(getHotelRunnerErrorMessage({
      response: { data: { detail: { error_code: 'HOTELRUNNER_RESERVATION_SYNC_DISABLED' } } },
    }, 'fallback')).toBe('HOTELRUNNER_RESERVATION_SYNC_DISABLED');

    expect(getHotelRunnerErrorMessage({
      response: { data: { detail: { payload: 'must-not-be-rendered' } } },
    }, 'fallback')).toBe('fallback');
  });
});
