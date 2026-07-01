import { describe, it, expect, vi, beforeEach } from 'vitest';

// offlineQueueDB'yi mock'la (IndexedDB tarayicida olmadigi icin).
const enqueueRoomStatus = vi.fn();
const listQueuedRoomStatus = vi.fn();
const removeQueuedRoomStatus = vi.fn();
const updateQueuedRoomStatus = vi.fn();

vi.mock('@/utils/offlineQueueDB', () => ({
  enqueueRoomStatus: (...a) => enqueueRoomStatus(...a),
  listQueuedRoomStatus: (...a) => listQueuedRoomStatus(...a),
  removeQueuedRoomStatus: (...a) => removeQueuedRoomStatus(...a),
  updateQueuedRoomStatus: (...a) => updateQueuedRoomStatus(...a),
}));

import axios from 'axios';
import {
  performRoomStatusUpdate,
  roomStatusKeyForRoom,
  processQueuedRoomStatus,
  requeueRoomStatus,
  cancelQueuedRoomStatus,
  requeueRoomStatuses,
  cancelQueuedRoomStatuses,
  MAX_ROOM_STATUS_ATTEMPTS,
} from '@/utils/offlineRoomStatus';

vi.mock('axios', () => ({
  default: { put: vi.fn() },
}));

describe('performRoomStatusUpdate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    enqueueRoomStatus.mockResolvedValue(undefined);
    Object.defineProperty(global.navigator, 'onLine', {
      value: true,
      configurable: true,
    });
  });

  it('deterministik anahtar uretir', () => {
    expect(roomStatusKeyForRoom('abc')).toBe('roomstatus-abc');
  });

  it('cevrimici basarida kuyruga ALMAZ', async () => {
    const onlineRequest = vi.fn().mockResolvedValue({ data: { ok: true } });
    const res = await performRoomStatusUpdate('room-1', 'clean', { onlineRequest });
    expect(res.offlineQueued).toBe(false);
    expect(res.synced).toBe(true);
    expect(enqueueRoomStatus).not.toHaveBeenCalled();
  });

  it('AG hatasinda (response yok) kuyruga ALIR (coalesce: id == key)', async () => {
    const onlineRequest = vi.fn().mockRejectedValue(new Error('Network Error'));
    const res = await performRoomStatusUpdate('room-2', 'dirty', { onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(res.key).toBe('roomstatus-room-2');
    expect(enqueueRoomStatus).toHaveBeenCalledTimes(1);
    const entry = enqueueRoomStatus.mock.calls[0][0];
    expect(entry.id).toBe('roomstatus-room-2');
    expect(entry.roomId).toBe('room-2');
    expect(entry.roomStatus).toBe('dirty');
    expect(entry.status).toBe('pending');
  });

  it('gercek sunucu hatasinda (oda yok) kuyruga ALMAZ, hatayi firlatir', async () => {
    const err = new Error('not found');
    err.response = { status: 404, data: { detail: 'room not found' } };
    const onlineRequest = vi.fn().mockRejectedValue(err);
    await expect(performRoomStatusUpdate('room-3', 'clean', { onlineRequest })).rejects.toThrow();
    expect(enqueueRoomStatus).not.toHaveBeenCalled();
  });

  it('navigator.onLine=false ise dogrudan kuyruga ALIR (online cagri yapilmaz)', async () => {
    Object.defineProperty(global.navigator, 'onLine', {
      value: false,
      configurable: true,
    });
    const onlineRequest = vi.fn();
    const res = await performRoomStatusUpdate('room-4', 'inspected', { onlineRequest });
    expect(res.offlineQueued).toBe(true);
    expect(onlineRequest).not.toHaveBeenCalled();
    expect(enqueueRoomStatus).toHaveBeenCalledTimes(1);
  });
});

describe('processQueuedRoomStatus — deneme sayaci + kalici hata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    removeQueuedRoomStatus.mockResolvedValue(undefined);
    updateQueuedRoomStatus.mockResolvedValue(undefined);
  });

  function mkErr(status, detail) {
    const e = new Error('http');
    e.response = { status, data: { detail } };
    return e;
  }

  it('basarili replay idempotent PUT eder ve kuyruktan kaldirir', async () => {
    listQueuedRoomStatus
      .mockResolvedValueOnce([{ id: 'roomstatus-a', roomId: 'a', roomStatus: 'clean', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.put.mockResolvedValueOnce({ data: { ok: true } });

    const res = await processQueuedRoomStatus();
    expect(res.synced).toBe(1);
    expect(axios.put).toHaveBeenCalledWith('/pms/housekeeping/rooms/a/status', { status: 'clean' });
    expect(removeQueuedRoomStatus).toHaveBeenCalledWith('roomstatus-a');
  });

  it('gecici 5xx hatasinda deneme sayacini artirir, kuyrukta birakir', async () => {
    listQueuedRoomStatus
      .mockResolvedValueOnce([{ id: 'roomstatus-a', roomId: 'a', roomStatus: 'clean', status: 'pending', attempts: 1 }])
      .mockResolvedValueOnce([{ id: 'roomstatus-a', roomId: 'a', roomStatus: 'clean', status: 'pending' }]);
    axios.put.mockRejectedValueOnce(mkErr(503, null));

    const res = await processQueuedRoomStatus();
    expect(res.conflicts).toBe(0);
    expect(updateQueuedRoomStatus).toHaveBeenCalledWith('roomstatus-a', { attempts: 2 });
    expect(removeQueuedRoomStatus).not.toHaveBeenCalled();
  });

  it('deneme tavanina ulasinca 5xx hatasini cakismaya cevirir (sonsuz tekrar yok)', async () => {
    listQueuedRoomStatus
      .mockResolvedValueOnce([
        { id: 'roomstatus-b', roomId: 'b', roomStatus: 'dirty', status: 'pending', attempts: MAX_ROOM_STATUS_ATTEMPTS - 1 },
      ])
      .mockResolvedValueOnce([]);
    axios.put.mockRejectedValueOnce(mkErr(500, null));

    const res = await processQueuedRoomStatus();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedRoomStatus.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.error.code).toBe('MAX_RETRIES_EXCEEDED');
    expect(patch.attempts).toBe(MAX_ROOM_STATUS_ATTEMPTS);
  });

  it('404 (oda yok) kalici hatadir, dogrudan cakismaya cevrilir', async () => {
    listQueuedRoomStatus
      .mockResolvedValueOnce([{ id: 'roomstatus-c', roomId: 'c', roomStatus: 'clean', status: 'pending' }])
      .mockResolvedValueOnce([]);
    axios.put.mockRejectedValueOnce(mkErr(404, 'not found'));

    const res = await processQueuedRoomStatus();
    expect(res.conflicts).toBe(1);
    const patch = updateQueuedRoomStatus.mock.calls[0][1];
    expect(patch.status).toBe('conflict');
    expect(patch.httpStatus).toBe(404);
    expect(patch.attempts).toBe(1);
  });
});

describe('requeueRoomStatus / cancelQueuedRoomStatus — operatör eylemleri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateQueuedRoomStatus.mockResolvedValue(undefined);
    removeQueuedRoomStatus.mockResolvedValue(undefined);
  });

  it('requeue girisi pending yapar ve deneme sayacini sifirlar', async () => {
    await requeueRoomStatus('roomstatus-x');
    expect(updateQueuedRoomStatus).toHaveBeenCalledWith('roomstatus-x', {
      status: 'pending',
      error: null,
      httpStatus: null,
      attempts: 0,
    });
  });

  it('cancel girisi kuyruktan kaldirir', async () => {
    await cancelQueuedRoomStatus('roomstatus-y');
    expect(removeQueuedRoomStatus).toHaveBeenCalledWith('roomstatus-y');
  });
});

describe('requeueRoomStatuses / cancelQueuedRoomStatuses — toplu operatör eylemleri', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateQueuedRoomStatus.mockResolvedValue(undefined);
    removeQueuedRoomStatus.mockResolvedValue(undefined);
  });

  it('requeueRoomStatuses her girisi pending yapar ve sayaci sifirlar', async () => {
    const count = await requeueRoomStatuses(['roomstatus-1', 'roomstatus-2']);
    expect(count).toBe(2);
    expect(updateQueuedRoomStatus).toHaveBeenCalledTimes(2);
  });

  it('cancelQueuedRoomStatuses her girisi kuyruktan kaldirir', async () => {
    const count = await cancelQueuedRoomStatuses(['roomstatus-a', 'roomstatus-b', 'roomstatus-c']);
    expect(count).toBe(3);
    expect(removeQueuedRoomStatus).toHaveBeenCalledTimes(3);
  });

  it('bos veya gecersiz liste no-op olur (cokmez)', async () => {
    expect(await requeueRoomStatuses([])).toBe(0);
    expect(await requeueRoomStatuses(undefined)).toBe(0);
    expect(await cancelQueuedRoomStatuses([null, undefined])).toBe(0);
    expect(updateQueuedRoomStatus).not.toHaveBeenCalled();
    expect(removeQueuedRoomStatus).not.toHaveBeenCalled();
  });
});
