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

import { performCheckin, checkinKeyForBooking } from '@/utils/offlineCheckin';

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
