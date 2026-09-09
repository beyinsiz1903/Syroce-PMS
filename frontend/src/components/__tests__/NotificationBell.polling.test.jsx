import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import NotificationBell from '../NotificationBell';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

it('polls only visible tabs every minute and refreshes on return', async () => {
  vi.useFakeTimers();
  let visibility = 'visible';
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  axios.get.mockResolvedValue({ data: { notifications: [], unread_count: 0 } });
  await act(async () => { render(<MemoryRouter><NotificationBell /></MemoryRouter>); });
  expect(axios.get).toHaveBeenCalledTimes(1);
  await act(async () => { vi.advanceTimersByTime(15000); });
  expect(axios.get).toHaveBeenCalledTimes(1);
  await act(async () => { vi.advanceTimersByTime(45000); });
  expect(axios.get).toHaveBeenCalledTimes(2);
  visibility = 'hidden';
  await act(async () => { vi.advanceTimersByTime(180000); });
  expect(axios.get).toHaveBeenCalledTimes(2);
  visibility = 'visible';
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
  expect(axios.get).toHaveBeenCalledTimes(3);
  cleanup();
  await act(async () => { vi.advanceTimersByTime(60000); });
  expect(axios.get).toHaveBeenCalledTimes(3);
});
