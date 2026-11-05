import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { render, waitFor, screen } from '@testing-library/react';
import App from '../App';
import { keepActiveSessionAlive, shouldRefreshActiveSession, verifyActiveSession } from '@/config/axiosConfig';
import { rememberTabAuthSubject } from '@/lib/authSessionScope';

// Mock the axios module
vi.mock('axios', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
      defaults: {
        headers: { common: {} },
        baseURL: '',
        withCredentials: true
      },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }
  };
});

// Mock hooks that would crash the test
vi.mock('@/hooks/usePushNotifications', () => ({ default: vi.fn() }));
vi.mock('@/utils/offlineQueueDB', () => ({
  listNotifications: vi.fn().mockResolvedValue([]),
  initQueueDB: vi.fn().mockResolvedValue(),
  OfflineDB: {
    init: vi.fn().mockResolvedValue(),
    list: vi.fn().mockResolvedValue([])
  }
}));

// Exercise the real registered auth interceptor together with App bootstrap,
// rather than supplying a hand-labelled error that bypasses the broken seam.
const rejectAuthResponse = axios.interceptors.response.use.mock.calls.at(-1)[1];

describe('Auth Cookie Flow in App.jsx', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/app/dashboard');
    vi.clearAllMocks();
    axios.get.mockReset();
    axios.post.mockReset();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(), // Deprecated
        removeListener: vi.fn(), // Deprecated
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it.each([503, 429, undefined])('preserves App bootstrap after an initial 401 and transient refresh failure %s', async status => {
    const user = { id: 'u1', name: 'Cached User', tenant_id: 't1', role: 'admin' };
    localStorage.setItem('token_ts', String(Date.now()));
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', property_name: 'Test Hotel' }));
    axios.post.mockRejectedValueOnce(status ? { response: { status } } : new Error('offline'));
    axios.get.mockImplementation((url, config) => url === '/auth/me' && !config?._skipAuthRetry
      ? rejectAuthResponse({ config: { url, method: 'get' }, response: { status: 401 } })
      : Promise.resolve({ data: {} }));

    render(<App />);

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/auth/refresh-token', {}, { _skipAuthRetry: true }));
    await waitFor(() => expect(screen.getByTestId('nav-dashboard-button')).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('user'))).toEqual(user);
    expect(localStorage.getItem('token_ts')).not.toBeNull();
  });

  it.each([false, true])('uses a fresh verified identity response when the startup 401 is stale (already retried: %s)', async retried => {
    const cached = { id: 'u1', name: 'Cached User', tenant_id: 't1', role: 'admin' };
    const fresh = { ...cached, name: 'Verified User' };
    localStorage.setItem('token_ts', String(Date.now()));
    localStorage.setItem('user', JSON.stringify(cached));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', property_name: 'Test Hotel' }));
    axios.post.mockRejectedValueOnce({ response: { status: 400 } });
    axios.get.mockImplementation((url, config) => url === '/auth/me'
      ? config?._skipAuthRetry ? Promise.resolve({ data: fresh, status: 200 })
        : rejectAuthResponse({ config: { url, method: 'get', _retried: retried }, response: { status: 401 } })
      : Promise.resolve({ data: {} }));

    render(<App />);

    await waitFor(() => expect(screen.getByTestId('nav-dashboard-button')).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('user'))).toEqual(fresh);
    expect(axios.get).toHaveBeenCalledWith('/auth/me', { _skipAuthRetry: true, _skipRetry: true, _noCache: true });
  });

  it('still rejects a different identity in the fresh recovery response for an existing tab', async () => {
    const cached = { id: 'u1', tenant_id: 't1', role: 'admin' };
    localStorage.setItem('token_ts', String(Date.now()));
    localStorage.setItem('user', JSON.stringify(cached));
    rememberTabAuthSubject(cached);
    axios.post.mockRejectedValueOnce({ response: { status: 400 } });
    axios.get.mockImplementation((url, config) => url === '/auth/me'
      ? config?._skipAuthRetry ? Promise.resolve({ data: { id: 'u2', tenant_id: 't2', role: 'admin' }, status: 200 })
        : rejectAuthResponse({ config: { url, method: 'get' }, response: { status: 401 } })
      : Promise.resolve({ data: {} }));

    render(<App />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/auth/me', expect.objectContaining({ _skipAuthRetry: true })));
    await waitFor(() => expect(screen.queryByTestId('nav-dashboard-button')).not.toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem('user'))).toEqual(cached);
  });

  it.each([
    [false, '/pms/cashier/verify-pin'], [true, '/pms/cashier/verify-pin'],
    [false, '/pms/payments'], [true, '/pms/payments'],
  ])('never turns an operation 401 into a successful identity response (%s, %s)', async (retried, url) => {
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    axios.post.mockRejectedValueOnce({ response: { status: 400 } });
    axios.get.mockResolvedValueOnce({ data: { id: 'u1' }, status: 200 });
    const error = { config: { url, method: 'post', _retried: retried }, response: { status: 401 } };

    await expect(rejectAuthResponse(error)).rejects.toBe(error);

    expect(localStorage.getItem('user')).not.toBeNull();
    if (retried) expect(axios.post).not.toHaveBeenCalled();
  });

  it('still clears the session when refresh and the uncached identity endpoint definitively reject it', async () => {
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    localStorage.setItem('token_ts', String(Date.now()));
    axios.post.mockRejectedValueOnce({ response: { status: 401 } });
    axios.get.mockRejectedValueOnce({ response: { status: 401 } });
    const error = { config: { url: '/auth/me', method: 'get' }, response: { status: 401 } };

    await expect(rejectAuthResponse(error)).rejects.toBe(error);

    expect(localStorage.getItem('user')).toBeNull();
    expect(localStorage.getItem('token_ts')).toBeNull();
  });

  it('should wait for /auth/me to verify session if token_ts is present', async () => {
    // Set the cookie session flag
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ name: 'Test User' }));
    
    // Mock a successful backend verification
    axios.get.mockResolvedValueOnce({ data: { id: 'u1', name: 'Fresh User' } });
    
    expect(localStorage.getItem('token')).toBeNull(); // No token in localStorage
    
    // Call the effect logic directly via a wrapper or assume render works if we mock enough.
    // For this security test, we want to ensure axios.get is called
    try {
      render(<App />);
    } catch(e) {
      // ignore render crashes due to missing providers, we only care about the useEffect side effect
    }
    
    // App should call /auth/me because token_ts exists
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
    });
  });

  it('opens the verified workspace without waiting for subscription metadata', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'Cached User', tenant_id: 't1' }));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', property_name: 'Test Hotel' }));

    let resolveSubscription;
    axios.get.mockImplementation((url) => {
      if (url === '/auth/me') {
        return Promise.resolve({ data: { id: 'u1', name: 'Fresh User', tenant_id: 't1', role: 'admin' } });
      }
      if (url === '/subscription/current') {
        return new Promise((resolve) => { resolveSubscription = resolve; });
      }
      return Promise.resolve({ data: {} });
    });

    render(<App />);

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/subscription/current');
      expect(screen.getByTestId('nav-dashboard-button')).toBeInTheDocument();
    });

    resolveSubscription({ data: { modules: { pms: true } } });
  });

  it('should recover a missing tenant snapshot and modules from the server', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'Cached User' }));
    localStorage.setItem('tenant', 'null');

    axios.get
      .mockResolvedValueOnce({ data: { id: 'u1', tenant_id: 't1', name: 'Fresh User', role: 'admin' } })
      .mockResolvedValueOnce({
        data: {
          tenant: { id: 't1', property_name: 'The Canyon Kartepe' },
          modules: { pms: true, reports: true },
        },
      });

    render(<App />);

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/subscription/current');
      expect(JSON.parse(localStorage.getItem('tenant'))).toEqual({
        id: 't1',
        property_name: 'The Canyon Kartepe',
        modules: { pms: true, reports: true },
      });
      expect(JSON.parse(localStorage.getItem('modules'))).toEqual({ pms: true, reports: true });
    });
  });

  it('should clear token_ts if /auth/me definitively rejects the session', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ name: 'Test User' }));
    localStorage.setItem('entitlements', JSON.stringify({ tenantId: 'previous-hotel' }));
    sessionStorage.setItem('notif_cache_v1', 'previous-notifications');
    
    // Mock a failed backend verification (e.g. cookie expired)
    axios.get.mockRejectedValueOnce({ response: { status: 401 } });
    
    try {
      render(<App />);
    } catch(e) {
      // ignore
    }
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      // Auth storage should be cleared
      expect(localStorage.getItem('token_ts')).toBeNull();
      expect(localStorage.getItem('user')).toBeNull();
      expect(localStorage.getItem('entitlements')).toBeNull();
      expect(sessionStorage.getItem('notif_cache_v1')).toBeNull();
    });
  });

  it('preserves the restored origin session after an expired super-admin workspace context', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'admin-1', name: 'Platform Admin' }));
    localStorage.setItem('tenant', JSON.stringify({ id: 'origin-tenant', name: 'Platform' }));

    axios.get.mockRejectedValueOnce({
      response: { status: 401 },
      _sessionContextRestored: true,
    });

    try {
      render(<App />);
    } catch (e) {
      // Providers are intentionally minimal in this focused auth test.
    }

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(localStorage.getItem('token_ts')).not.toBeNull();
      expect(JSON.parse(localStorage.getItem('user'))).toMatchObject({ id: 'admin-1' });
    });
  });

  it('should preserve the verified local session during a transient backend outage', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'Test User' }));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', name: 'Test Hotel' }));

    axios.get.mockRejectedValueOnce({ response: { status: 503 } });

    try {
      render(<App />);
    } catch (e) {
      // Providers are intentionally minimal in this focused auth test.
    }

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(localStorage.getItem('token_ts')).not.toBeNull();
      expect(localStorage.getItem('user')).not.toBeNull();
    });
  });

  it('preserves the cached session when a 401 could not be verified because identity is temporarily unavailable', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'Test User' }));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', name: 'Test Hotel' }));

    axios.get.mockRejectedValueOnce({
      response: { status: 401 },
      _sessionVerificationTransient: true,
    });

    try {
      render(<App />);
    } catch (e) {
      // Providers are intentionally minimal in this focused auth test.
    }

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(localStorage.getItem('token_ts')).not.toBeNull();
      expect(localStorage.getItem('user')).not.toBeNull();
    });
  });

  it('should preserve the verified local session when /auth/me denies an operation', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'Test User' }));
    localStorage.setItem('tenant', JSON.stringify({ id: 't1', name: 'Test Hotel' }));

    axios.get.mockRejectedValueOnce({ response: { status: 403 } });

    try {
      render(<App />);
    } catch (e) {
      // Providers are intentionally minimal in this focused auth test.
    }

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(localStorage.getItem('token_ts')).not.toBeNull();
      expect(localStorage.getItem('user')).not.toBeNull();
    });
  });

  it('should verify an old session marker instead of logging out locally', async () => {
    const eightDaysAgo = Date.now() - (8 * 24 * 60 * 60 * 1000);
    localStorage.setItem('token_ts', String(eightDaysAgo));
    localStorage.setItem('user', JSON.stringify({ name: 'Long Session User' }));
    axios.get.mockResolvedValueOnce({ data: { id: 'u1', name: 'Long Session User' } });

    try {
      render(<App />);
    } catch (e) {
      // Providers are intentionally minimal in this focused auth test.
    }

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(localStorage.getItem('token_ts')).toBe(String(eightDaysAgo));
    });
  });

  it('should renew an active session before the access token expires', () => {
    const ninetyOneMinutesAgo = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(ninetyOneMinutesAgo));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));

    expect(shouldRefreshActiveSession()).toBe(true);
  });

  it('should not renew a fresh session unnecessarily', () => {
    localStorage.setItem('token_ts', String(Date.now()));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));

    expect(shouldRefreshActiveSession()).toBe(false);
  });

  it('should rotate an old active session without logging the user out', async () => {
    const oldMarker = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(oldMarker));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    localStorage.setItem('refresh_token', 'test-refresh-token');
    axios.post.mockResolvedValueOnce({
      data: { access_token: 'new-access-token', refresh_token: 'new-refresh-token' },
    });

    await expect(keepActiveSessionAlive()).resolves.toEqual({ refreshed: true });
    expect(axios.post).toHaveBeenCalledWith(
      '/auth/refresh-token',
      { refresh_token: 'test-refresh-token' },
      { _skipAuthRetry: true },
    );
    expect(localStorage.getItem('refresh_token')).toBe('new-refresh-token');
    expect(Number(localStorage.getItem('token_ts'))).toBeGreaterThan(oldMarker);
    expect(localStorage.getItem('user')).not.toBeNull();
  });

  it('should preserve an old active session when renewal is temporarily unavailable', async () => {
    const oldMarker = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(oldMarker));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    axios.post.mockRejectedValueOnce({ response: { status: 503 } });

    await expect(keepActiveSessionAlive()).resolves.toEqual({ transient: true });
    expect(localStorage.getItem('token_ts')).toBe(String(oldMarker));
    expect(localStorage.getItem('user')).not.toBeNull();
  });

  it('should preserve an old active session when renewal is rate limited', async () => {
    const oldMarker = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(oldMarker));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    axios.post.mockRejectedValueOnce({ response: { status: 429 } });

    await expect(keepActiveSessionAlive()).resolves.toEqual({ transient: true });
    expect(localStorage.getItem('token_ts')).toBe(String(oldMarker));
    expect(localStorage.getItem('user')).not.toBeNull();
  });

  it('should preserve the session when refresh races but /auth/me is still valid', async () => {
    const oldMarker = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(oldMarker));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    localStorage.setItem('refresh_token', 'rotated-in-another-tab');
    axios.post.mockRejectedValueOnce({ response: { status: 401 } });
    axios.get.mockResolvedValueOnce({ data: { id: 'u1', tenant_id: 't1' } });

    await expect(keepActiveSessionAlive()).resolves.toEqual({ sessionRecovered: true });
    expect(axios.get).toHaveBeenCalledWith('/auth/me', {
      _skipAuthRetry: true,
      _skipRetry: true,
      _noCache: true,
    });
    expect(localStorage.getItem('token_ts')).toBe(String(oldMarker));
    expect(localStorage.getItem('user')).not.toBeNull();
  });

  it('does not log out when refresh is rejected but the identity check is temporarily unavailable', async () => {
    const oldMarker = Date.now() - (91 * 60 * 1000);
    localStorage.setItem('token_ts', String(oldMarker));
    localStorage.setItem('user', JSON.stringify({ id: 'u1' }));
    localStorage.setItem('refresh_token', 'possibly-stale-refresh-token');
    axios.post.mockRejectedValueOnce({ response: { status: 401 } });
    axios.get.mockRejectedValueOnce({ response: { status: 503 } });

    await expect(keepActiveSessionAlive()).resolves.toEqual({ transient: true });
    expect(localStorage.getItem('token_ts')).toBe(String(oldMarker));
    expect(localStorage.getItem('user')).not.toBeNull();
  });

  it('should trust only a fresh uncached /auth/me response for logout decisions', async () => {
    axios.get.mockResolvedValueOnce({ data: { id: 'u1' } });

    await expect(verifyActiveSession()).resolves.toBe(true);
    expect(axios.get).toHaveBeenCalledWith('/auth/me', {
      _skipAuthRetry: true,
      _skipRetry: true,
      _noCache: true,
    });
  });
});
