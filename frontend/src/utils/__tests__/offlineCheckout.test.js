import { describe, it, expect, vi, beforeEach } from 'vitest';

// offlineQueueDB'yi mock'la (IndexedDB tarayicida olmadigi icin).
const enqueueCheckout = vi.fn();
const listQueuedCheckouts = vi.fn();
const removeQueuedCheckout = vi.fn();
const updateQueuedCheckout = vi.fn();

vi.mock('@/utils/offlineQueueDB', () => ({
  enqueueCheckout: (...a) => enqueueCheckout(...a),
  listQueuedCheckouts: (...a) => listQueuedCheckouts(...a),
  removeQueuedCheckout: (...a) => removeQueuedCheckout(...a),
  updateQueuedCheckout: (...a) => updateQueuedCheckout(...a),
}));

import axios from 'axios';
import {
  performCheckout,
  checkoutKeyForBooking,
  processQueuedCheckouts,
  requeueCheckout,
  cancelQueuedCheckout,
  requeueCheckouts,
  cancelQueuedCheckouts,
  MAX_CHECKOUT_ATTEMPTS,
} from '@/utils/offlineCheckout';

vi.mock('axios', () => ({
  default: { post: vi.fn() },
}));

describe('performCheckout — sifir bakiye yolu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    enqueueCheckout.mockResolvedValue(undefined);
    Object.defineProperty(global.navigator, 'onLine', {
      value: true,
      configurable: true,
    });
  });

  it('deterministik anahtar uretir', () => {
    expect(checkoutKeyForBooking('abc')).toBe('checkout-abc');
  });

  it('cevrimici basarida kuyruga ALMAZ', async () => {
    const onlineRequest = vi.fn().mockResolvedValue({ data: { ok: true } });
    const res = await performCheckout('bk-1', { balance: 0, onlineRequest });
    expect(res.offlineQueued).toBe(false);
    expect(res.synced).toBe(true);
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('AG hatasinda (response yok) kuyruga ALIR', async () => {
    const onlineRequest = vi.fn().mockRejectedValue(new Error('Network Error'));
    const res = await performCheckout('bk-2', { balance: 0, onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(res.key).toBe('checkout-bk-2');
    expect(enqueueCheckout).toHaveBeenCalledTimes(1);
    const entry = enqueueCheckout.mock.calls[0][0];
    expect(entry.id).toBe('checkout-bk-2');
    expect(entry.bookingId).toBe('bk-2');
    expect(entry.status).toBe('pending');
  });

  it('gercek sunucu hatasinda kuyruga ALMAZ, hatayi firlatir', async () => {
    const err = new Error('bad');
    err.response = { status: 400, data: { detail: 'invalid state' } };
    const onlineRequest = vi.fn().mockRejectedValue(err);
    await expect(performCheckout('bk-3', { balance: 0, onlineRequest })).rejects.toThrow();
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('navigator.onLine=false ise dogrudan kuyruga ALIR (online cagri yapilmaz)', async () => {
    Object.defineProperty(global.navigator, 'onLine', {
      value: false,
      configurable: true,
    });
    const onlineRequest = vi.fn();
    const res = await performCheckout('bk-4', { balance: 0, onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(onlineRequest).not.toHaveBeenCalled();
    expect(enqueueCheckout).toHaveBeenCalledTimes(1);
  });
});

describe('performCheckout — acik bakiye ASLA cevrimdisina alinmaz (odeme korumasi)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    enqueueCheckout.mockResolvedValue(undefined);
    Object.defineProperty(global.navigator, 'onLine', {
      value: true,
      configurable: true,
    });
  });

  it('cevrimdisi + acik bakiye: bloklar, kuyruga ALMAZ, online cagri yapmaz', async () => {
    Object.defineProperty(global.navigator, 'onLine', {
      value: false,
      configurable: true,
    });
    const onlineRequest = vi.fn();
    const res = await performCheckout('bk-5', { balance: 250, onlineRequest });
    expect(res.blocked).toBe(true);
    expect(res.reason).toBe('OUTSTANDING_BALANCE');
    expect(onlineRequest).not.toHaveBeenCalled();
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('cevrimici + acik bakiye: normal cikis denenir (basarida sync)', async () => {
    const onlineRequest = vi.fn().mockResolvedValue({ data: { ok: true } });
    const res = await performCheckout('bk-6', { balance: 250, onlineRequest });
    expect(res.synced).toBe(true);
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('cevrimici + acik bakiye + AG hatasi: kuyruga ALMAZ, bloklar', async () => {
    const onlineRequest = vi.fn().mockRejectedValue(new Error('Network Error'));
    const res = await performCheckout('bk-7', { balance: 250, onlineRequest });
    expect(res.blocked).toBe(true);
    expect(res.reason).toBe('OFFLINE_OPEN_BALANCE');
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('cevrimici + acik bakiye + 402: hatayi firlatir, kuyruga ALMAZ', async () => {
    const err = new Error('outstanding');
    err.response = { status: 402, data: { detail: { code: 'OUTSTANDING_BALANCE' } } };
    const onlineRequest = vi.fn().mockRejectedValue(err);
    await expect(performCheckout('bk-8', { balance: 250, onlineRequest })).rejects.toThrow();
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });

  it('bilinmeyen bakiye (undefined) acik kabul edilir → cevrimdisi bloklar', async () => {
    Object.defineProperty(global.navigator, 'onLine', {
      value: false,
      configurable: true,
    });
    const onlineRequest = vi.fn();
    const res = await performCheckout('bk-9', { onlineRequest });
    expect(res.blocked).toBe(true);
    expect(res.reason).toBe('OUTSTANDING_BALANCE');
    expect(enqueueCheckout).not.toHaveBeenCalled();
  });
});

describe('processQueuedCheckouts — replay, idempotent ve kalici hata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    removeQueuedCheckout.mockResolvedValue(undefined);
    updateQueuedCheckout.mockResolvedValue(undefined);
  });

  function mkErr(status, detail) {
    const e = new Error('http');
    e.response = { status, data: { detail } };
    return e;
  }

  it('basarili replay idempotent POST eder ve kuyruktan kaldirir', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([{ id: 'checkout-a', bookingId: 'a', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.post.mockResolvedValueOnce({ data: { ok: true } });

    const res = await processQueuedCheckouts();
    expect(res.synced).toBe(1);
    expect(axios.post).toHaveBeenCalledWith('/frontdesk/checkout/a?auto_close_folios=true');
    expect(removeQueuedCheckout).toHaveBeenCalledWith('checkout-a');
  });

  it('"zaten cikis yapilmis" (400) idempotent BASARI sayilir', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([{ id: 'checkout-b', bookingId: 'b', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(400, 'Guest already checked out'));

    const res = await processQueuedCheckouts();
    expect(res.synced).toBe(1);
    expect(res.conflicts).toBe(0);
    expect(removeQueuedCheckout).toHaveBeenCalledWith('checkout-b');
  });

  it('402 acik bakiye → cakismaya cevrilir (OUTSTANDING_BALANCE)', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([{ id: 'checkout-c', bookingId: 'c', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(402, { code: 'OUTSTANDING_BALANCE' }));

    const res = await processQueuedCheckouts();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedCheckout.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.error.code).toBe('OUTSTANDING_BALANCE');
    expect(patch.httpStatus).toBe(402);
  });

  it('gecici 5xx hatasinda deneme sayacini artirir, kuyrukta birakir', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([{ id: 'checkout-d', bookingId: 'd', status: 'pending', attempts: 1 }])
      .mockResolvedValueOnce([{ id: 'checkout-d', bookingId: 'd', status: 'pending' }]);
    axios.post.mockRejectedValueOnce(mkErr(503, null));

    const res = await processQueuedCheckouts();
    expect(res.conflicts).toBe(0);
    expect(updateQueuedCheckout).toHaveBeenCalledWith('checkout-d', { attempts: 2 });
    expect(removeQueuedCheckout).not.toHaveBeenCalled();
  });

  it('deneme tavanina ulasinca 5xx hatasini cakismaya cevirir', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([
        { id: 'checkout-e', bookingId: 'e', status: 'pending', attempts: MAX_CHECKOUT_ATTEMPTS - 1 },
      ])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(500, null));

    const res = await processQueuedCheckouts();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedCheckout.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.error.code).toBe('MAX_RETRIES_EXCEEDED');
    expect(patch.attempts).toBe(MAX_CHECKOUT_ATTEMPTS);
  });

  it('404 (rezervasyon yok) kalici hatadir, dogrudan cakismaya cevrilir', async () => {
    listQueuedCheckouts
      .mockResolvedValueOnce([{ id: 'checkout-f', bookingId: 'f', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(404, 'not found'));

    const res = await processQueuedCheckouts();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedCheckout.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.httpStatus).toBe(404);
    expect(patch.attempts).toBe(1);
  });
});

describe('requeueCheckout / cancelQueuedCheckout — operatör eylemleri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateQueuedCheckout.mockResolvedValue(undefined);
    removeQueuedCheckout.mockResolvedValue(undefined);
  });

  it('requeue girisi pending yapar ve deneme sayacini sifirlar', async () => {
    await requeueCheckout('checkout-x');
    expect(updateQueuedCheckout).toHaveBeenCalledWith('checkout-x', {
      status: 'pending',
      error: null,
      httpStatus: null,
      attempts: 0,
    });
  });

  it('cancel girisi kuyruktan kaldirir', async () => {
    await cancelQueuedCheckout('checkout-y');
    expect(removeQueuedCheckout).toHaveBeenCalledWith('checkout-y');
  });
});

describe('requeueCheckouts / cancelQueuedCheckouts — toplu operatör eylemleri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateQueuedCheckout.mockResolvedValue(undefined);
    removeQueuedCheckout.mockResolvedValue(undefined);
  });

  it('requeueCheckouts her girisi pending yapar', async () => {
    const count = await requeueCheckouts(['checkout-1', 'checkout-2']);
    expect(count).toBe(2);
    expect(updateQueuedCheckout).toHaveBeenCalledTimes(2);
  });

  it('cancelQueuedCheckouts her girisi kuyruktan kaldirir', async () => {
    const count = await cancelQueuedCheckouts(['checkout-a', 'checkout-b', 'checkout-c']);
    expect(count).toBe(3);
    expect(removeQueuedCheckout).toHaveBeenCalledTimes(3);
  });

  it('bos veya gecersiz liste no-op olur (cokmez)', async () => {
    expect(await requeueCheckouts([])).toBe(0);
    expect(await requeueCheckouts(undefined)).toBe(0);
    expect(await cancelQueuedCheckouts([null, undefined])).toBe(0);
    expect(updateQueuedCheckout).not.toHaveBeenCalled();
    expect(removeQueuedCheckout).not.toHaveBeenCalled();
  });
});
