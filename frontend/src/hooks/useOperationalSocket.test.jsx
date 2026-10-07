import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { ioMock, socket } = vi.hoisted(() => {
  const mockedSocket = {
    connected: false,
    on: vi.fn(),
    emit: vi.fn(),
    removeAllListeners: vi.fn(),
    disconnect: vi.fn(),
  };
  return { ioMock: vi.fn(() => mockedSocket), socket: mockedSocket };
});

vi.mock('socket.io-client', () => ({ io: ioMock }));

import { useOperationalSocket } from './useOperationalSocket';

describe('useOperationalSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses the canonical Socket.IO endpoint instead of the legacy proxy path', () => {
    const { unmount } = renderHook(() => useOperationalSocket('/', {}));

    expect(ioMock).toHaveBeenCalledTimes(1);
    expect(ioMock.mock.calls[0][1]).toMatchObject({
      path: '/ws/socket.io',
      withCredentials: true,
    });

    unmount();
    expect(socket.disconnect).toHaveBeenCalledTimes(1);
  });
});
