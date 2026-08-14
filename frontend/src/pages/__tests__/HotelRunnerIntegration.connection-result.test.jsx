import { describe, expect, it } from 'vitest';

import { normalizeHotelRunnerConnectionTest } from '@/pages/HotelRunnerIntegration';

describe('HotelRunner connection result contract', () => {
  it('accepts the normalized endpoint response', () => {
    expect(normalizeHotelRunnerConnectionTest({
      success: true,
      connected: true,
      duration_ms: 17
    })).toEqual({
      connected: true,
      durationMs: 17,
      error: 'Bağlantı doğrulanamadı'
    });
  });

  it('accepts the legacy ProviderResult response', () => {
    expect(normalizeHotelRunnerConnectionTest({
      success: true,
      data: { connected: true },
      duration_ms: 21
    }).connected).toBe(true);
  });

  it('never renders an empty or undefined failure reason', () => {
    expect(normalizeHotelRunnerConnectionTest({ success: false })).toEqual({
      connected: false,
      durationMs: 0,
      error: 'Bağlantı doğrulanamadı'
    });
  });
});
