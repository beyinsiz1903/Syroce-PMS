import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { usePmsBookingHistory } from '../usePmsBookingHistory';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };
const row = id => ({ id, room_id: null, status: 'confirmed' });
beforeEach(() => axios.get.mockReset().mockResolvedValue({ data: [row('initial')] }));

describe('PMS full history ownership', () => {
  it('does not fetch until the permitted history workspace opens', async () => {
    const { result, rerender } = renderHook(props => usePmsBookingHistory(props), { initialProps: { enabled: false, scopeKey: 'a' } });
    act(() => result.current.refreshIfRequested());
    expect(axios.get).not.toHaveBeenCalled();
    rerender({ enabled: true, scopeKey: 'a' });
    await waitFor(() => expect(result.current.rows).toEqual([row('initial')]));
  });

  it('keeps the last complete list during refresh and ignores an older completion', async () => {
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(result.current.rows).toEqual([row('initial')]));
    const old = deferred();
    axios.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ data: [row('newest')] });
    act(() => { void result.current.refresh(); });
    expect(result.current.loading).toBe(true);
    expect(result.current.rows).toEqual([row('initial')]);
    await act(async () => result.current.refresh());
    await act(async () => old.resolve({ data: [row('obsolete')] }));
    expect(result.current.rows).toEqual([row('newest')]);
  });

  it('loads all pages and does not publish an incomplete page set', async () => {
    const second = deferred();
    const firstPage = Array.from({ length: 1000 }, (_, id) => row(String(id)));
    axios.get.mockResolvedValueOnce({ data: firstPage }).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect(result.current.rows).toBeNull();
    expect(axios.get.mock.calls[1][0]).toContain('offset=1000&full_history=true');
    await act(async () => second.resolve({ data: { bookings: [row('last')] } }));
    expect(result.current.rows).toHaveLength(1001);
  });

  it('preserves the complete list when refresh fails or returns a malformed payload', async () => {
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(result.current.rows).not.toBeNull());
    axios.get.mockResolvedValueOnce({ data: { unexpected: [] } });
    await act(async () => result.current.refresh());
    expect(result.current.rows).toEqual([row('initial')]);
    expect(result.current.error).toContain('liste eksik olabilir');
    axios.get.mockResolvedValueOnce({ data: [row('recovered')] });
    await act(async () => result.current.refresh());
    expect(result.current.error).toBeNull();
    expect(result.current.rows).toEqual([row('recovered')]);
  });

  it('does not expose another tenant dataset or accept its delayed response/callback', async () => {
    const old = deferred();
    axios.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ data: [row('tenant-b')] });
    const { result, rerender } = renderHook(props => usePmsBookingHistory(props), { initialProps: { enabled: true, scopeKey: 'a' } });
    const oldRefresh = result.current.refresh;
    rerender({ enabled: true, scopeKey: 'b' });
    expect(result.current.rows).toBeNull();
    await waitFor(() => expect(result.current.rows).toEqual([row('tenant-b')]));
    await act(async () => old.resolve({ data: [row('tenant-a')] }));
    await act(async () => oldRefresh());
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(result.current.rows).toEqual([row('tenant-b')]);
  });

  it('does not publish a partial history when a later page fails', async () => {
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(result.current.rows).not.toBeNull());
    axios.get.mockResolvedValueOnce({ data: Array.from({ length: 1000 }, (_, id) => row(String(id))) })
      .mockRejectedValueOnce(new Error('second-page timeout'));
    await act(async () => result.current.refresh());
    expect(result.current.rows).toEqual([row('initial')]);
    expect(result.current.error).not.toBeNull();
  });

  it('stops repeated full pages rather than looping or doubling totals', async () => {
    const page = Array.from({ length: 1000 }, (_, id) => row(String(id)));
    axios.get.mockResolvedValue({ data: page });
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(result.current.rows).toBeNull();
  });

  it('deduplicates a boundary row without hiding a valid last page', async () => {
    const page = Array.from({ length: 1000 }, (_, id) => row(String(id)));
    axios.get.mockResolvedValueOnce({ data: page }).mockResolvedValueOnce({ data: [row('999'), row('last')] });
    const { result } = renderHook(() => usePmsBookingHistory({ enabled: true, scopeKey: 'a' }));
    await waitFor(() => expect(result.current.rows).toHaveLength(1001));
    expect(result.current.error).toBeNull();
  });
});
