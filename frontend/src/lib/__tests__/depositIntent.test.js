import { beforeEach, describe, expect, it, vi } from 'vitest';
import { submitDepositIntent } from '../depositIntent';

describe('durable deposit intent', () => {
  beforeEach(() => { sessionStorage.clear(); });
  it.each([undefined, 409, 500, 503])('retains exact body after uncertain %s and across a retry', async status => {
    const sent = [];
    const fail = vi.fn(async body => { sent.push(body); throw { response: status ? { status } : undefined }; });
    const payload = { amount: 100, method: 'cash' };
    await expect(submitDepositIntent('booking', 'receive', payload, fail)).rejects.toBeDefined();
    const retry = vi.fn(async body => { sent.push(body); return { success: true }; });
    await submitDepositIntent('booking', 'receive', payload, retry);
    expect(sent[0]).toEqual(sent[1]);
    expect(sent[0].request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(sessionStorage.length).toBe(0);
  });
  it('does not mint another UUID when uncertain form contents change', async () => {
    await expect(submitDepositIntent('b', 'refund', { refund_amount: 50 }, async () => { throw Error('timeout'); })).rejects.toThrow();
    const send = vi.fn();
    await expect(submitDepositIntent('b', 'refund', { refund_amount: 60 }, send)).rejects.toThrow('sonucu belirsiz');
    expect(send).not.toHaveBeenCalled();
  });
  it.each([400, 401, 403, 404, 422])('clears a definite pre-write %s rejection', async status => {
    await expect(submitDepositIntent('b', 'receive', { amount: 0 }, async () => { throw { response: { status } }; })).rejects.toBeDefined();
    expect(sessionStorage.length).toBe(0);
  });
  it('fails before send if durable storage is unavailable', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: () => { throw Error('Storage unavailable'); } });
    const send = vi.fn();
    await expect(submitDepositIntent('b', 'receive', { amount: 1 }, send)).rejects.toThrow();
    expect(send).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it('does not report a committed payment as failed if storage cleanup fails', async () => {
    const stored = new Map();
    vi.stubGlobal('sessionStorage', {
      getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value),
      removeItem: () => { throw Error('Storage unavailable'); },
    });
    const send = vi.fn(async () => ({ success: true }));
    await expect(submitDepositIntent('b', 'receive', { amount: 1 }, send)).resolves.toEqual({ success: true });
    expect(stored.size).toBe(1);
    vi.unstubAllGlobals();
  });
});
