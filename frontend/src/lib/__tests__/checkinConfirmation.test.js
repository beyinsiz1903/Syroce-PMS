import { describe, expect, it, vi } from 'vitest';
import { createCheckinConfirmation } from '../checkinConfirmation';

const booking = (status, id = 'stay') => ({ data: { booking: { id, status } } });
const lost = () => Object.assign(new Error('response lost'), { code: 'ECONNABORTED' });

describe('confirmed check-in recovery', () => {
  it('coalesces simultaneous confirmations into one mutation', async () => {
    let done;
    const client = { post: vi.fn(() => new Promise(resolve => { done = resolve; })), get: vi.fn() };
    const confirm = createCheckinConfirmation(client);
    const first = confirm('stay');
    expect(confirm('stay')).toBe(first);
    done({ data: { success: true } });
    await first;
    expect(client.post).toHaveBeenCalledTimes(1);
    expect(client.post.mock.calls[0][2]).toEqual({ timeout: 15000 });
  });
  it('recovers a committed check-in after losing the response without a second POST', async () => {
    const client = { post: vi.fn().mockRejectedValue(lost()), get: vi.fn().mockResolvedValue(booking('checked_in')) };
    await expect(createCheckinConfirmation(client)('stay')).resolves.toEqual({ recovered: true });
    expect(client.post).toHaveBeenCalledTimes(1);
  });
  it('blocks retry while authoritative readback is unavailable, then observes completion', async () => {
    const client = { post: vi.fn().mockRejectedValue(lost()), get: vi.fn().mockRejectedValue(lost()) };
    const confirm = createCheckinConfirmation(client);
    await expect(confirm('stay')).rejects.toThrow('otomatik tekrarlanmadı');
    await expect(confirm('stay')).rejects.toThrow('otomatik tekrarlanmadı');
    expect(client.post).toHaveBeenCalledTimes(1);
    client.get.mockResolvedValue(booking('checked_in'));
    await expect(confirm('stay')).resolves.toEqual({ recovered: true });
    expect(client.post).toHaveBeenCalledTimes(1);
  });
  it('allows an explicit retry only after confirming the same eligible reservation', async () => {
    const client = { post: vi.fn().mockRejectedValueOnce(lost()).mockResolvedValue({ data: { success: true } }),
      get: vi.fn().mockResolvedValue(booking('confirmed')) };
    const confirm = createCheckinConfirmation(client);
    await expect(confirm('stay')).rejects.toThrow('doğrulanamadı');
    expect(client.post).toHaveBeenCalledTimes(1);
    await confirm('stay');
    expect(client.get).toHaveBeenCalledTimes(2);
    expect(client.post).toHaveBeenCalledTimes(2);
    expect(client.get.mock.invocationCallOrder[1]).toBeLessThan(client.post.mock.invocationCallOrder[1]);
  });
  it.each(['cancelled', 'checked_out'])('never retries a now %s stay', async status => {
    const client = { post: vi.fn().mockRejectedValue(lost()), get: vi.fn().mockResolvedValue(booking(status)) };
    const confirm = createCheckinConfirmation(client);
    await expect(confirm('stay')).rejects.toThrow();
    await expect(confirm('stay')).rejects.toThrow();
    expect(client.post).toHaveBeenCalledTimes(1);
  });
  it('rejects mismatched readback and preserves uncertainty', async () => {
    const client = { post: vi.fn().mockRejectedValue(lost()), get: vi.fn().mockResolvedValue(booking('checked_in', 'other')) };
    const confirm = createCheckinConfirmation(client);
    await expect(confirm('stay')).rejects.toThrow('doğrulanamadı');
    await expect(confirm('stay')).rejects.toThrow('doğrulanamadı');
    expect(client.post).toHaveBeenCalledTimes(1);
  });
  it('preserves explicit lock and validation failures without automatic retry', async () => {
    const denied = { response: { status: 409, data: { detail: 'Lease expired' } } };
    const client = { post: vi.fn().mockRejectedValue(denied), get: vi.fn() };
    await expect(createCheckinConfirmation(client)('stay')).rejects.toBe(denied);
    expect(client.get).not.toHaveBeenCalled();
    expect(client.post).toHaveBeenCalledTimes(1);
  });
});
