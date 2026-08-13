import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

const axiosGet = vi.fn();

vi.mock('axios', () => ({
  default: { get: (...args) => axiosGet(...args) },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import PushSubscriptionManager from '@/components/PushSubscriptionManager';

describe('PushSubscriptionManager status cache', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockResolvedValue({
      data: { enabled: false, devices: [], subscriptions: ['arrivals'] },
    });
    sessionStorage.clear();
    localStorage.setItem('user', JSON.stringify({ id: 'user-1' }));
    vi.stubGlobal('Notification', { permission: 'default' });
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {},
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('reuses a fresh user-scoped status across layout remounts', async () => {
    const first = render(<PushSubscriptionManager />);
    await waitFor(() => expect(axiosGet).toHaveBeenCalledTimes(1));
    first.unmount();

    render(<PushSubscriptionManager />);
    await waitFor(() => expect(axiosGet).toHaveBeenCalledTimes(1));
  });
});
