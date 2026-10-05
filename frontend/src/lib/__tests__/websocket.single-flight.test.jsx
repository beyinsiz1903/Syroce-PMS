import { describe, expect, it, vi } from 'vitest';

const socket = {
  connected: false,
  on: vi.fn(),
  emit: vi.fn(),
  disconnect: vi.fn(),
};
const io = vi.fn(() => socket);

vi.mock('socket.io-client', () => ({ io }));

describe('WebSocketManager connection bootstrap', () => {
  it('shares one pending socket.io handshake between first-screen consumers', async () => {
    const { WebSocketManager } = await import('../websocket');
    const manager = new WebSocketManager();

    const [first, second, third] = await Promise.all([
      manager.connect(),
      manager.connect(),
      manager.connect(),
    ]);

    expect(io).toHaveBeenCalledTimes(1);
    expect(first).toBe(socket);
    expect(second).toBe(socket);
    expect(third).toBe(socket);
  });
});
