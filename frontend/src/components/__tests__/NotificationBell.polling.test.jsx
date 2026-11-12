import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import axios from 'axios';
import NotificationBell from '../NotificationBell';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  sessionStorage.clear();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{JSON.stringify({ path: location.pathname, state: location.state })}</output>;
}

it('refreshes a cached list on opening and opens the newly imported booking', async () => {
  sessionStorage.setItem('notif_cache_v1', JSON.stringify({ t: Date.now(), notifications: [], unread_count: 0 }));
  const notification = {
    id: 'exely-source-version', type: 'reservation', title: 'Yeni Exely rezervasyonu',
    message: 'Mert Erdem · 2026-11-23 – 2026-11-25 · 2 oda', read: false,
    related_entity: 'booking', related_id: 'imported-booking',
    metadata: { booking_id: 'imported-booking', booking_ids: ['imported-booking', 'second-room'] },
  };
  axios.get.mockResolvedValue({ data: { notifications: [notification], unread_count: 1 } });
  axios.put.mockResolvedValue({ data: {} });
  render(<MemoryRouter><NotificationBell /><LocationProbe /></MemoryRouter>);
  expect(axios.get).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Bildirimleri aç' }));
  expect(await screen.findByText('Yeni Exely rezervasyonu')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledExactlyOnceWith('/notifications/list?limit=20', { headers: {} });
  fireEvent.click(screen.getByTestId('notification-item-exely-source-version'));
  expect(JSON.parse(screen.getByTestId('location').textContent)).toEqual({
    path: '/app/reservation-calendar', state: { openBookingId: 'imported-booking' },
  });
});

it('polls only visible tabs every minute and refreshes on return', async () => {
  vi.useFakeTimers();
  let visibility = 'visible';
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  axios.get.mockResolvedValue({ data: { notifications: [], unread_count: 0 } });
  await act(async () => { render(<MemoryRouter><NotificationBell /></MemoryRouter>); });

  expect(screen.getByRole('button', { name: 'Bildirimleri aç' })).toBeInTheDocument();
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
