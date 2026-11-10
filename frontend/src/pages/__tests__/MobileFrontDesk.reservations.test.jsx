import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import MobileFrontDesk from '@/pages/MobileFrontDesk';
import { performCheckout } from '@/utils/offlineCheckout';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key === 'pms.bookings' ? 'Rezervasyonlar' : key }) }));
vi.mock('@/hooks/useMediaCapture', () => ({ default: () => ({ uploading: false }) }));
vi.mock('@/utils/offlineCheckout', () => ({ performCheckout: vi.fn() }));

const reservation = {
  id: 'reservation-127', guest_name: 'Hakan Arslan', room_number: '127', status: 'checked_in',
  check_in: '2026-10-22', check_out: '2026-10-26', total_amount: 3000, currency: 'TRY',
};

const arrival = { id: 'arrival-1', guest_name: 'Selin Kaya', status: 'guaranteed', check_in: '2026-10-26' };
const businessDay = {
  business_date: '2026-10-26', today_checkins: 6, today_checkouts: 6, in_house_stays: 25,
  available_rooms: 3, arrivals: [arrival],
  departures: [reservation, { ...reservation, id: 'reservation-203', guest_name: 'Mert Akın', room_number: '203' }],
};

function renderFrontDesk() {
  return render(<MemoryRouter initialEntries={['/mobile/frontdesk']}>
    <Routes>
      <Route path="/mobile/frontdesk" element={<MobileFrontDesk />} />
      <Route path="/walkin" element={<h1>Walk-in rezervasyon formu</h1>} />
    </Routes>
  </MemoryRouter>);
}

describe('mobile front desk reservations', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    axios.get.mockImplementation(async (path) => ({
      data: {
        '/pms/bookings': [reservation],
        '/frontdesk/business-day': businessDay,
        '/unified/in-house': { in_house: [reservation], count: 28 },
        '/bookings/arrival-1/available-rooms': {
          available_rooms: [
            { id: 'r1', room_number: '101', room_type: 'Standard', is_same_type: true, floor: 1 },
            { id: 'r2', room_number: '202', room_type: 'Deluxe', is_same_type: false, floor: 2 },
          ],
        },
      }[path] ?? {},
    }));
    performCheckout.mockResolvedValue({ blocked: false });
  });

  it('displays a PMS reservation when the endpoint returns a bare list', async () => {
    renderFrontDesk();
    fireEvent.click(await screen.findByRole('button', { name: 'Rezervasyonlar' }));
    const dialog = screen.getByRole('dialog', { name: 'Rezervasyonlar (1)' });
    expect(within(dialog).getByText('Hakan Arslan')).toBeVisible();
    expect(within(dialog).getByText('Oda: 127')).toBeVisible();
  });

  it('does not claim there are zero reservations when the request fails', async () => {
    axios.get.mockImplementation(async (path) => {
      if (path === '/pms/bookings') throw new Error('Unavailable');
      return { data: {} };
    });
    renderFrontDesk();
    fireEvent.click(await screen.findByRole('button', { name: 'Rezervasyonlar' }));
    expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent('Rezervasyonlar yüklenemedi');
    expect(screen.queryByText('Rezervasyonlar (0)')).not.toBeInTheDocument();
  });

  it('opens the existing walk-in workflow from the quick action', async () => {
    renderFrontDesk();
    fireEvent.click(await screen.findByRole('button', { name: 'Walk-In' }));
    expect(screen.getByRole('heading', { name: 'Walk-in rezervasyon formu' })).toBeVisible();
  });

  it('shows the PMS workday totals and checks out only the reservation selected', async () => {
    renderFrontDesk();
    expect(await screen.findByText('PMS iş günü · 26.10.2026')).toBeVisible();
    expect(screen.getByText('İŞ GÜNÜ ÇIKIŞ').nextElementSibling).toHaveTextContent('6');
    expect(screen.getByText('KONAKLAYANLAR').nextElementSibling).toHaveTextContent(/^28$/);
    expect(screen.getByText('BOŞ ODALAR').nextElementSibling).toHaveTextContent('3');

    fireEvent.click(screen.getByRole('button', { name: 'Check-Out' }));
    expect(performCheckout).not.toHaveBeenCalled();
    const picker = screen.getByRole('dialog', { name: 'Çıkış yapılacak rezervasyonu seçin' });
    fireEvent.click(within(picker).getByRole('button', { name: /Mert Akın/ }));
    await waitFor(() => expect(performCheckout).toHaveBeenCalledExactlyOnceWith(
      'reservation-203', { onlineRequest: expect.any(Function) },
    ));
  });

  it('keeps workday actions disabled when the workday is unavailable', async () => {
    axios.get.mockRejectedValue(new Error('Unavailable'));
    renderFrontDesk();
    expect(await screen.findByRole('alert')).toHaveTextContent('İş günü bilgileri yüklenemedi');
    expect(screen.getByText('İŞ GÜNÜ GELİŞ').nextElementSibling).toHaveTextContent('—');
    expect(screen.getByRole('button', { name: 'Check-In' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Walk-In' })).toBeEnabled();
  });

  it('does not substitute the worknight count when the current guest count fails', async () => {
    axios.get.mockImplementation(async (path) => {
      if (path === '/unified/in-house') throw new Error('Unavailable');
      return { data: path === '/frontdesk/business-day' ? businessDay : {} };
    });
    renderFrontDesk();
    expect(await screen.findByText('PMS iş günü · 26.10.2026')).toBeVisible();
    expect(screen.getByText('KONAKLAYANLAR').nextElementSibling).toHaveTextContent('—');
  });

  it('assigns a same-type room through the regular reservation update without changing the price', async () => {
    renderFrontDesk();
    fireEvent.click(await screen.findByRole('button', { name: 'Oda Ata' }));
    fireEvent.click(screen.getByRole('button', { name: /Selin Kaya/ }));
    const rooms = await screen.findByRole('dialog', { name: 'Oda Atama' });
    expect(within(rooms).queryByRole('button', { name: /Oda 202/ })).not.toBeInTheDocument();
    fireEvent.click(within(rooms).getByRole('button', { name: /Oda 101/ }));
    await waitFor(() => expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      '/pms/bookings/arrival-1',
      { room_id: 'r1' },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    ));
  });
});
