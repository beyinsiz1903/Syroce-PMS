import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const socketState = vi.hoisted(() => ({
  connect: vi.fn(),
  on: vi.fn(),
  listener: null,
  unsubscribe: vi.fn(),
}));

vi.mock('@/lib/websocket', () => ({
  websocket: {
    connect: socketState.connect,
    on: socketState.on,
  },
}));

import { useCalendarRealtime } from '../useCalendarRealtime';

describe('useCalendarRealtime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    socketState.connect.mockReset().mockResolvedValue({});
    socketState.unsubscribe.mockReset();
    socketState.listener = null;
    socketState.on.mockReset().mockImplementation((event, callback) => {
      if (event === 'booking_update') socketState.listener = callback;
      return socketState.unsubscribe;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reloads authoritative calendar data when a booking event arrives', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const { unmount } = renderHook(() => useCalendarRealtime(refresh, {
      debounceMs: 20,
      pollIntervalMs: 60_000,
    }));

    expect(socketState.on).toHaveBeenCalledWith('booking_update', expect.any(Function));
    expect(socketState.connect).toHaveBeenCalledTimes(1);

    act(() => socketState.listener({ event_type: 'cancel' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20);
    });

    expect(refresh).toHaveBeenCalledTimes(1);
    unmount();
    expect(socketState.unsubscribe).toHaveBeenCalledTimes(1);
  });

  it('coalesces bursts and refreshes again when the tab becomes visible', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useCalendarRealtime(refresh, {
      debounceMs: 25,
      pollIntervalMs: 60_000,
    }));

    act(() => {
      socketState.listener({ event_type: 'update' });
      socketState.listener({ event_type: 'update' });
      socketState.listener({ event_type: 'cancel' });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(25);
    });
    expect(refresh).toHaveBeenCalledTimes(1);

    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(25);
    });
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
