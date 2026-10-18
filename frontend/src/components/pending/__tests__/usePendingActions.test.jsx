import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import usePendingActions from '../usePendingActions';

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

describe('pending list request ownership', () => {
  it('loads again after a mutation and never lets an older refresh win', async () => {
    const first = deferred(), stale = deferred(), latest = deferred();
    const api = { get: vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(stale.promise).mockReturnValueOnce(latest.promise) };
    const { result } = renderHook(() => usePendingActions({ api, path: '/pending' }));
    await act(async () => first.resolve({ data: { yours: ['old'] } }));
    expect(result.current.data.yours).toEqual(['old']);
    act(() => { result.current.reload(); result.current.reload(); });
    await act(async () => latest.resolve({ data: { yours: [] } }));
    await act(async () => stale.resolve({ data: { yours: ['already-completed'] } }));
    expect(result.current.data.yours).toEqual([]);
  });

  it('clears previous-account data immediately and ignores its delayed response', async () => {
    const old = deferred(), current = deferred();
    const api = { get: vi.fn().mockResolvedValueOnce({ data: { yours: ['agency-a'] } }).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise) };
    const { result, rerender } = renderHook(({ sessionKey }) => usePendingActions({ api, path: '/pending', sessionKey }), { initialProps: { sessionKey: 'a' } });
    await waitFor(() => expect(result.current.data?.yours).toEqual(['agency-a']));
    act(() => { result.current.reload(); });
    rerender({ sessionKey: 'b' });
    expect(result.current.data).toBeNull();
    await act(async () => current.resolve({ data: { yours: ['agency-b'] } }));
    await act(async () => old.resolve({ data: { yours: ['agency-a-private'] } }));
    expect(result.current.data.yours).toEqual(['agency-b']);
  });

  it('does not call the marketplace endpoint in the legacy hotel portal or after logout', async () => {
    const response = deferred();
    const api = { get: vi.fn().mockReturnValue(response.promise) };
    const { result, rerender } = renderHook(({ enabled }) => usePendingActions({ api, path: '/pending', enabled }), { initialProps: { enabled: false } });
    await act(async () => result.current.reload());
    expect(api.get).not.toHaveBeenCalled();
    rerender({ enabled: true });
    expect(api.get).toHaveBeenCalledTimes(1);
    rerender({ enabled: false });
    await act(async () => response.resolve({ data: { yours: ['private'] } }));
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('keeps failures distinct from a successful empty response and permits retry', async () => {
    const failure = { response: { status: 503 } };
    const api = { get: vi.fn().mockRejectedValueOnce(failure).mockResolvedValueOnce({ data: { yours: [], theirs: [] } }) };
    const { result } = renderHook(() => usePendingActions({ api, path: '/pending' }));
    await waitFor(() => expect(result.current.error).toBe(failure));
    expect(result.current.data).toBeNull();
    await act(async () => result.current.reload());
    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual({ yours: [], theirs: [] });
  });
});
