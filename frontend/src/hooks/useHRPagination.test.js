import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import { useHRPagination } from './useHRPagination';

vi.mock('axios', () => ({ default: { get: vi.fn(), isCancel: () => false } }));
afterEach(cleanup);

it.each(['staff', 'items'])('reads the %s response envelope without losing pagination metadata', async (key) => {
  const items = [{ id: 'qa' }];
  axios.get.mockResolvedValue({ data: { [key]: items, total: 30, total_pages: 2, counts: { pending: 3 } } });
  const { result } = renderHook(() => useHRPagination('/hr/staff'));
  await waitFor(() => expect(result.current.items).toEqual(items));
  expect(result.current.total).toBe(30);
  expect(result.current.totalPages).toBe(2);
  expect(result.current.meta.counts.pending).toBe(3);
});
