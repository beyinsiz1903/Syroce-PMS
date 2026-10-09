import { beforeEach, describe, expect, it, vi } from 'vitest';
import { enqueueOrder, readQueue, sendQueuedOrder } from './posOfflineQueue';

const scope = { tenant_id: 'hotel1', actor_id: 'waiter1' };
const body = { items: [{ item_id: 'tea', quantity: 2 }], idempotency_key: 'one' };
const path = '/pos/v2/orders';
beforeEach(() => localStorage.clear());
describe('durable tenant-scoped POS queue', () => {
  it('survives reload and retries an identical payload after response loss', async () => {
    enqueueOrder(scope, path, body);
    const api = { get: vi.fn().mockResolvedValue({ data: scope }), post: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: { order_id: 'o1' } }) };
    await expect(sendQueuedOrder(scope, 'one', api)).rejects.toThrow('offline');
    expect(readQueue(scope)[0].state).toBe('pending');
    await sendQueuedOrder({ ...scope }, readQueue(scope)[0].id, api);
    expect(api.post.mock.calls).toEqual([[path, body], [path, body]]);
    expect(readQueue(scope)).toEqual([]);
  });
  it('does not replay another hotel or user queue', async () => {
    enqueueOrder(scope, path, body);
    const api = { get: vi.fn().mockResolvedValue({ data: { ...scope, tenant_id: 'hotel2' } }), post: vi.fn() };
    expect(readQueue({ ...scope, tenant_id: 'hotel2' })).toEqual([]);
    await expect(sendQueuedOrder(scope, 'one', api)).rejects.toThrow('Oturum değişti');
    expect(api.post).not.toHaveBeenCalled();
    expect(readQueue(scope)).toHaveLength(1);
  });
  it('keeps a rejected order for explicit conflict resolution', async () => {
    enqueueOrder(scope, path, body);
    const api = { get: vi.fn().mockResolvedValue({ data: scope }), post: vi.fn().mockRejectedValue({ response: { status: 409, data: { detail: 'Masa dolu' } } }) };
    await expect(sendQueuedOrder(scope, 'one', api)).rejects.toBeDefined();
    expect(readQueue(scope)[0]).toMatchObject({ state: 'conflict', error: 'Masa dolu' });
    expect(() => enqueueOrder(scope, path, { ...body, items: [] })).toThrow('aynı anahtarla');
  });
  it('fails visibly before sending when persistence is unavailable', () => {
    const storage = { getItem: () => null, setItem: () => { throw new Error('quota'); } };
    expect(() => enqueueOrder(scope, path, body, storage)).toThrow('quota');
  });
  it('stores independent operations under separate atomic keys', async () => {
    enqueueOrder(scope, path, body);
    enqueueOrder(scope, path, { ...body, idempotency_key: 'two' });
    const api = { get: vi.fn().mockResolvedValue({ data: scope }), post: vi.fn().mockResolvedValue({ data: { order_id: 'o1' } }) };
    await sendQueuedOrder(scope, 'one', api);
    expect(readQueue(scope).map(row => row.id)).toEqual(['two']);
  });
});
