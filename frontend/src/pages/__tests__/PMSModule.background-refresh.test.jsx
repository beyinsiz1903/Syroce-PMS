import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { BUSINESS_DATE_CHANGED_EVENT } from '@/lib/businessDateEvents';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const { translate } = vi.hoisted(() => ({ translate: (key, options) => typeof options === 'string' ? options : options?.defaultValue || key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/Layout', () => ({ default: ({ children }) => <main>{children}</main> }));
vi.mock('@/components/GlobalSearch', () => ({ default: () => null }));
vi.mock('@/utils/moduleAccess', () => ({ canAccessPmsTab: (_user, tab) => tab === 'rooms' }));
vi.mock('@/components/pms/RoomsTab', async () => {
  const { useState } = await import('react');
  const RoomWorkspaceMock = ({ rooms, bookings, onDataRefresh }) => {
    const [draft, setDraft] = useState('');
    return <section data-testid="rooms-workspace">
      <input aria-label="Oda işlem taslağı" value={draft} onChange={event => setDraft(event.target.value)} />
      <button onClick={() => onDataRefresh()}>Oda verisini güncelle</button>
      <span data-testid="room-numbers">{rooms.map(room => room.room_number).join(',')}</span>
      <span data-testid="booking-names">{bookings.map(booking => booking.guest_name).join(',')}</span>
    </section>;
  };
  return { default: RoomWorkspaceMock };
});

import PMSModule from '../PMSModule';

const roomRows = number => [{ id: 'r1', room_number: number, status: 'dirty' }];
const bookingRows = name => [{ id: 'b1', guest_name: name, status: 'confirmed', total_amount: 10 }];
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const user = { id: 'u1', role: 'admin', effective_permissions: ['view_bookings'] };
const tenant = { id: 't1', subscription_plan: 'core_small_hotel' };
const mount = () => render(<MemoryRouter><PMSModule user={user} tenant={tenant} /></MemoryRouter>);

beforeEach(() => {
  window.location.hash = 'rooms';
  axios.get.mockReset().mockImplementation(url => {
    if (url === '/night-audit/business-date') return Promise.resolve({ data: { business_date: '2026-10-18' } });
    if (url.startsWith('/pms/rooms?')) return Promise.resolve({ data: roomRows('101') });
    if (url.startsWith('/pms/bookings?')) return Promise.resolve({ data: bookingRows('İlk misafir') });
    return Promise.resolve({ data: [] });
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.location.hash = ''; });

describe('PMS background refresh', () => {
  it('keeps the room workspace and its draft mounted while refreshing', async () => {
    mount();
    await screen.findByTestId('rooms-workspace');
    fireEvent.change(screen.getByLabelText('Oda işlem taslağı'), { target: { value: 'Kaybolmamalı' } });
    const response = deferred();
    const originalGet = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.startsWith('/pms/rooms?') ? response.promise : originalGet(url));

    fireEvent.click(screen.getByRole('button', { name: 'Oda verisini güncelle' }));
    expect(screen.queryByText('PMS verileri yükleniyor…')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Oda işlem taslağı')).toHaveValue('Kaybolmamalı');
    expect(screen.getByTestId('room-numbers')).toHaveTextContent('101');
    await act(async () => response.resolve({ data: roomRows('102') }));
    expect(screen.getByTestId('room-numbers')).toHaveTextContent('102');
    expect(screen.getByLabelText('Oda işlem taslağı')).toHaveValue('Kaybolmamalı');
  });

  it.each(['rooms', 'bookings'])('retains the previous %s on a partial refresh failure', async source => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mount();
    await screen.findByTestId('rooms-workspace');
    const originalGet = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.startsWith(`/pms/${source}?`) ? Promise.reject(new Error('temporary')) : originalGet(url));
    fireEvent.click(screen.getByRole('button', { name: 'Oda verisini güncelle' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('bir bölümü alınamadı'));
    expect(screen.getByTestId('room-numbers')).toHaveTextContent('101');
    expect(screen.getByTestId('booking-names')).toHaveTextContent('İlk misafir');
  });

  it('ignores a delayed response from the previous business day', async () => {
    mount();
    await screen.findByTestId('rooms-workspace');
    const old = deferred();
    let roomReads = 0;
    const originalGet = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => {
      if (url.startsWith('/pms/rooms?')) return ++roomReads === 1 ? old.promise : Promise.resolve({ data: roomRows('Yeni gün') });
      return originalGet(url);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Oda verisini güncelle' }));
    act(() => window.dispatchEvent(new CustomEvent(BUSINESS_DATE_CHANGED_EVENT, { detail: { businessDate: '2026-10-19' } })));
    await waitFor(() => expect(screen.getByTestId('room-numbers')).toHaveTextContent('Yeni gün'));
    await act(async () => old.resolve({ data: roomRows('Eski gün') }));
    expect(screen.getByTestId('room-numbers')).toHaveTextContent('Yeni gün');
  });
});
