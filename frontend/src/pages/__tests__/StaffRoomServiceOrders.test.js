import { describe, it, expect, vi } from 'vitest';

// Stub import.meta.env so the page module can read VITE_BACKEND_URL.
vi.stubEnv('VITE_BACKEND_URL', '');

const { buildStaffWsUrl } = await import('../StaffRoomServiceOrders.jsx');

describe('buildStaffWsUrl', () => {
  it('returns null when there is no auth token', () => {
    expect(buildStaffWsUrl({ token: null, origin: 'http://app.test', backendUrl: '/api' })).toBeNull();
  });

  it('uses the dev proxy default `/api` and the page origin when no backend URL is set', () => {
    const url = buildStaffWsUrl({
      token: 'tok',
      origin: 'http://app.test',
      backendUrl: undefined,
    });
    expect(url).toBe('ws://app.test/api/guest/staff/ws/room-service-orders?token=tok');
  });

  it('does NOT double `/api` when VITE_BACKEND_URL already ends in /api', () => {
    const url = buildStaffWsUrl({
      token: 'tok',
      origin: 'http://app.test',
      backendUrl: 'https://api.example.com/api',
    });
    expect(url).toBe('wss://api.example.com/api/guest/staff/ws/room-service-orders?token=tok');
    // Critical regression guard from code review: must not contain `/api/api/`.
    expect(url).not.toMatch(/\/api\/api\//);
  });

  it('appends `/api` when VITE_BACKEND_URL is just an origin', () => {
    const url = buildStaffWsUrl({
      token: 'tok',
      origin: 'http://app.test',
      backendUrl: 'https://api.example.com',
    });
    expect(url).toBe('wss://api.example.com/api/guest/staff/ws/room-service-orders?token=tok');
  });

  it('upgrades https → wss and http → ws', () => {
    expect(
      buildStaffWsUrl({ token: 't', origin: '', backendUrl: 'https://x.test/api' }),
    ).toMatch(/^wss:\/\//);
    expect(
      buildStaffWsUrl({ token: 't', origin: '', backendUrl: 'http://x.test/api' }),
    ).toMatch(/^ws:\/\//);
  });

  it('URL-encodes the token so a `+` or `&` cannot break the query string', () => {
    const url = buildStaffWsUrl({
      token: 'a+b&c=d',
      origin: 'http://app.test',
      backendUrl: '/api',
    });
    expect(url).toContain('token=a%2Bb%26c%3Dd');
  });
});
