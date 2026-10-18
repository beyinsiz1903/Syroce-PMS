import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { useModuleSalesInbox } from '../useModuleSalesInbox';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const superAdmin = { id: 'root-a', role: 'super_admin' };
const inbox = { open_count: 2, new_count: 1, unread_count: 1, notifications: [{ request_id: 'q', read: false, id: 'module-quote:q' }] };

describe('Module sales inbox access and races', () => {
  beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); axios.get.mockResolvedValue({ data: inbox }); axios.post.mockResolvedValue({ data: { ok: true } }); });
  afterEach(() => { vi.restoreAllMocks(); });

  it('does not query platform data for a hotel administrator', async () => {
    const { result } = renderHook(() => useModuleSalesInbox({ id: 'hotel', role: 'admin' }));
    expect(result.current.enabled).toBe(false);
    expect(result.current.data).toBeUndefined();
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('never reuses a previous administrator response after account switching', async () => {
    let finish;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { result, rerender } = renderHook(({ user }) => useModuleSalesInbox(user), { initialProps: { user: superAdmin } });
    rerender({ user: { id: 'root-b', role: 'super_admin' } });
    await waitFor(() => expect(result.current.data?.open_count).toBe(2));
    await act(async () => finish({ data: { ...inbox, open_count: 999 } }));
    expect(result.current.data.open_count).toBe(2);
    rerender({ user: { id: 'hotel', role: 'admin' } });
    expect(result.current.data).toBeUndefined();
  });

  it('acknowledges only the displayed ids and does not restore stale unread responses', async () => {
    const { result } = renderHook(() => useModuleSalesInbox(superAdmin));
    await waitFor(() => expect(result.current.data?.unread_count).toBe(1));
    let finish;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    act(() => { void result.current.refresh(); });
    await act(async () => result.current.acknowledge(['q']));
    expect(axios.post).toHaveBeenCalledWith('/module-store/admin/quote-requests/acknowledge', { request_ids: ['q'] });
    await act(async () => finish({ data: inbox }));
    expect(result.current.data.unread_count).toBe(0);
    expect(result.current.data.open_count).toBe(2);
    expect(result.current.data.notifications[0].read).toBe(true);
  });
});
