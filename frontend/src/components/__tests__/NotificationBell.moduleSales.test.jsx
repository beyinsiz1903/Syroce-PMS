import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import NotificationBell from '../NotificationBell';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
const Location = () => { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}</output>; };
const user = { id: 'root', role: 'super_admin' };
const quote = { id: 'module-quote:q', request_id: 'q', type: 'module_quote_request', title: 'Modül teklif talebi', message: 'Kartepe · POS', read: false, action_url: '/admin/module-requests?request=q' };

describe('Platform sales notifications', () => {
  beforeEach(() => {
    vi.resetAllMocks(); sessionStorage.clear(); localStorage.clear();
    axios.get.mockImplementation(async url => url.includes('quote-requests/inbox')
      ? { data: { notifications: [quote], unread_count: 1, open_count: 2, new_count: 1 } }
      : { data: { notifications: [], unread_count: 0 } });
    axios.put.mockResolvedValue({ data: {} }); axios.post.mockResolvedValue({ data: {} });
  });
  afterEach(() => { sessionStorage.clear(); localStorage.clear(); });

  it('shows a badge, acknowledges the quote separately, and deep-links to its queue record', async () => {
    render(<MemoryRouter><NotificationBell user={user} /><Location /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Bildirimler: 1 okunmamış' }));
    expect(await screen.findByText('Kartepe · POS')).toBeInTheDocument();
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/module-store/admin/quote-requests/acknowledge', { request_ids: ['q'] }));
    expect(screen.getByRole('button', { name: /Satış ve modül taleplerini aç \(2 açık\)/ })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('notification-item-module-quote:q'));
    expect(screen.getByTestId('location')).toHaveTextContent('/admin/module-requests?request=q');
  });

  it('never requests platform sales data for hotel users', async () => {
    render(<MemoryRouter><NotificationBell user={{ id: 'hotel', role: 'admin' }} /></MemoryRouter>);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/notifications/list?limit=20', expect.anything()));
    expect(axios.get.mock.calls.some(([url]) => url.includes('quote-requests'))).toBe(false);
  });

  it('keeps the queue link and an explicit failure when the sales inbox cannot be read', async () => {
    axios.get.mockImplementation(async url => {
      if (url.includes('quote-requests')) throw new Error('offline');
      return { data: { notifications: [], unread_count: 0 } };
    });
    render(<MemoryRouter><NotificationBell user={user} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Bildirimleri aç' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Satış talepleri alınamadı');
    expect(screen.getByRole('button', { name: 'Satış ve modül taleplerini aç' })).toBeInTheDocument();
  });
});
