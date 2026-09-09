import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { NotificationProvider } from '../NotificationContext';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/utils/offlineQueueDB', () => ({
  listNotifications: vi.fn().mockResolvedValue([]),
  logNotification: vi.fn(), clearNotification: vi.fn(),
}));
vi.mock('@/lib/websocket', () => ({
  websocket: { connect: vi.fn().mockResolvedValue(), on: vi.fn(() => vi.fn()) },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('user', JSON.stringify({ id: 'staff', role: 'finance' }));
  axios.get.mockImplementation(async (path) => ({
    data: path.endsWith('/access') ? { can_view: false } : { unread_count: 0, total_unread: 2 },
  }));
});
afterEach(cleanup);

describe('notification access', () => {
  it('does not request protected guest threads when access is denied', async () => {
    render(<NotificationProvider><div /></NotificationProvider>);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/messaging/guest-requests/access'));
    expect(axios.get.mock.calls.some(([path]) => path.endsWith('/threads'))).toBe(false);
  });

  it('loads guest unread counts after access is granted', async () => {
    axios.get.mockResolvedValue({ data: { can_view: true, total_unread: 2 } });
    render(<NotificationProvider><div /></NotificationProvider>);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith(
      '/messaging/guest-requests/threads', { params: { limit: 1 } },
    ));
  });

  it('does not re-fetch on focus when the auth snapshot is unchanged', async () => {
    render(<NotificationProvider><div /></NotificationProvider>);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    await act(async () => window.dispatchEvent(new Event('focus')));
    expect(axios.get).toHaveBeenCalledTimes(2);
  });

  it('suppresses protected requests until a mandatory password change completes', async () => {
    localStorage.setItem('user', JSON.stringify({ id: 'staff', role: 'admin', requires_password_change: true }));
    render(<NotificationProvider><div /></NotificationProvider>);
    await act(async () => {});
    expect(axios.get).not.toHaveBeenCalled();
  });
});
