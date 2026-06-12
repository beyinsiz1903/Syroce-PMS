import { describe, it, expect, vi, beforeEach } from 'vitest';

// offlineQueueDB'yi mock'la (IndexedDB tarayicida olmadigi icin).
const enqueueCheckin = vi.fn();
const listQueuedCheckins = vi.fn();
const removeQueuedCheckin = vi.fn();
const updateQueuedCheckin = vi.fn();

vi.mock('@/utils/offlineQueueDB', () => ({
  enqueueCheckin: (...a) => enqueueCheckin(...a),
  listQueuedCheckins: (...a) => listQueuedCheckins(...a),
  removeQueuedCheckin: (...a) => removeQueuedCheckin(...a),
  updateQueuedCheckin: (...a) => updateQueuedCheckin(...a),
}));

import axios from 'axios';
import {
  performCheckin,
  checkinKeyForBooking,
  processQueuedCheckins,
  requeueCheckin,
  cancelQueuedCheckin,
  MAX_CHECKIN_ATTEMPTS,
} from '@/utils/offlineCheckin';

vi.mock('axios', () => ({
  default: { post: vi.fn() },
}));

describe('performCheckin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    enqueueCheckin.mockResolvedValue(undefined);
    // navigator.onLine -> true varsay
    Object.defineProperty(global.navigator, 'onLine', {
      value: true,
      configurable: true,
    });
  });

  it('deterministik anahtar uretir', () => {
    expect(checkinKeyForBooking('abc')).toBe('checkin-abc');
  });

  it('cevrimici basarida kuyruga ALMAZ', async () => {
    const onlineRequest = vi.fn().mockResolvedValue({ data: { ok: true } });
    const res = await performCheckin('bk-1', { onlineRequest });
    expect(res.offlineQueued).toBe(false);
    expect(res.synced).toBe(true);
    expect(enqueueCheckin).not.toHaveBeenCalled();
  });

  it('AG hatasinda (response yok) kuyruga ALIR', async () => {
    const onlineRequest = vi.fn().mockRejectedValue(new Error('Network Error'));
    const res = await performCheckin('bk-2', { onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(res.idempotencyKey).toBe('checkin-bk-2');
    expect(enqueueCheckin).toHaveBeenCalledTimes(1);
    const entry = enqueueCheckin.mock.calls[0][0];
    expect(entry.id).toBe('checkin-bk-2');
    expect(entry.bookingId).toBe('bk-2');
    expect(entry.status).toBe('pending');
  });

  it('gercek sunucu hatasinda (oda dolu) kuyruga ALMAZ, hatayi firlatir', async () => {
    const err = new Error('conflict');
    err.response = { status: 409, data: { detail: { code: 'ROOM_OCCUPIED' } } };
    const onlineRequest = vi.fn().mockRejectedValue(err);
    await expect(performCheckin('bk-3', { onlineRequest })).rejects.toThrow();
    expect(enqueueCheckin).not.toHaveBeenCalled();
  });

  it('navigator.onLine=false ise dogrudan kuyruga ALIR (online cagri yapilmaz)', async () => {
    Object.defineProperty(global.navigator, 'onLine', {
      value: false,
      configurable: true,
    });
    const onlineRequest = vi.fn();
    const res = await performCheckin('bk-4', { onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(onlineRequest).not.toHaveBeenCalled();
    expect(enqueueCheckin).toHaveBeenCalledTimes(1);
  });
});

describe('processQueuedCheckins — deneme sayaci + kalici hata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    removeQueuedCheckin.mockResolvedValue(undefined);
    updateQueuedCheckin.mockResolvedValue(undefined);
  });

  function mkErr(status, detail) {
    const e = new Error('http');
    e.response = { status, data: { detail } };
    return e;
  }

  it('gecici 5xx hatasinda deneme sayacini artirir, kuyrukta birakir', async () => {
    listQueuedCheckins
      .mockResolvedValueOnce([{ id: 'checkin-a', bookingId: 'a', status: 'pending', attempts: 1 }])
      .mockResolvedValueOnce([{ id: 'checkin-a', bookingId: 'a', status: 'pending' }]);
    axios.post.mockRejectedValueOnce(mkErr(503, null));

    const res = await processQueuedCheckins();
    expect(res.conflicts).toBe(0);
    expect(updateQueuedCheckin).toHaveBeenCalledWith('checkin-a', { attempts: 2 });
    expect(removeQueuedCheckin).not.toHaveBeenCalled();
  });

  it('deneme tavanina ulasinca 5xx hatasini cakismaya cevirir (sonsuz tekrar yok)', async () => {
    listQueuedCheckins
      .mockResolvedValueOnce([
        { id: 'checkin-b', bookingId: 'b', status: 'pending', attempts: MAX_CHECKIN_ATTEMPTS - 1 },
      ])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(500, null));

    const res = await processQueuedCheckins();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedCheckin.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.error.code).toBe('MAX_RETRIES_EXCEEDED');
    expect(patch.attempts).toBe(MAX_CHECKIN_ATTEMPTS);
  });

  it('404 (rezervasyon yok) kalici hatadir, dogrudan cakismaya cevrilir', async () => {
    listQueuedCheckins
      .mockResolvedValueOnce([{ id: 'checkin-c', bookingId: 'c', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.post.mockRejectedValueOnce(mkErr(404, 'not found'));

    const res = await processQueuedCheckins();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedCheckin.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.httpStatus).toBe(404);
    expect(patch.attempts).toBe(1);
  });
});

describe('requeueCheckin / cancelQueuedCheckin — operatör eylemleri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateQueuedCheckin.mockResolvedValue(undefined);
    removeQueuedCheckin.mockResolvedValue(undefined);
  });

  it('requeue girisi pending yapar ve deneme sayacini sifirlar', async () => {
    await requeueCheckin('checkin-x');
    expect(updateQueuedCheckin).toHaveBeenCalledWith('checkin-x', {
      status: 'pending',
      error: null,
      httpStatus: null,
      attempts: 0,
    });
  });

  it('cancel girisi kuyruktan kaldirir', async () => {
    await cancelQueuedCheckin('checkin-y');
    expect(removeQueuedCheckin).toHaveBeenCalledWith('checkin-y');
  });
});
