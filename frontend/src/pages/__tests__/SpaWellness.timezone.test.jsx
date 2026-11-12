import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { MemoryRouter } from 'react-router-dom';
import SpaWellness from '@/pages/SpaWellness';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/idle', () => ({ runIdle: (fn) => { void fn(); } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({
  getLimit: () => 100, hasFeature: () => true, hasModule: () => true,
  loading: false, isSuperAdmin: true,
}) }));

function dataFor(url, timezone = 'Europe/Istanbul') {
  if (url === '/spa/services') return { services: [{ id: 's', name: 'Bakım', duration_minutes: 60, price: 100, currency: 'TRY', tax_rate: .2 }] };
  if (url === '/spa/appointments') return { appointments: [{ id: 'existing', starts_at: '2026-11-08T09:00:00Z', guest_name: 'Selin Kaya', status: 'completed', price: 100, currency: 'TRY' }] };
  if (url === '/spa/daily-summary') return { total: 1, timezone, by_status: { completed: 1 } };
  return {};
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-08T09:23:00Z'));
  axios.get.mockImplementation(async (url) => ({ data: dataFor(url) }));
  axios.post.mockResolvedValue({ data: {} });
});
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

const renderSpa = (props) => render(<MemoryRouter><SpaWellness {...props} /></MemoryRouter>);

async function openBooking() {
  const result = renderSpa({ tenant: { currency: 'TRY' } });
  await waitFor(() => expect(axios.get.mock.calls.some(([url]) => url === '/spa/daily-summary')).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Randevu' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Randevu' }));
  return result;
}

describe('SPA hotel wall clock, independent of browser UTC', () => {
  it('keeps the date input mounted and focused while a filtered list loads', async () => {
    const { container } = renderSpa();
    await screen.findByText('Selin Kaya');
    let resolveAppointments;
    axios.get.mockImplementation((url) => url === '/spa/appointments'
      ? new Promise(resolve => { resolveAppointments = resolve; })
      : Promise.resolve({ data: dataFor(url) }));
    const date = container.querySelector('input[type="date"]');
    date.focus();
    fireEvent.change(date, { target: { value: '2026-11-10' } });
    expect(container.querySelector('input[type="date"]')).toBe(date);
    expect(date).toHaveFocus();
    expect(date).toHaveValue('2026-11-10');
    await act(async () => { resolveAppointments({ data: { appointments: [] } }); });
    expect(container.querySelector('input[type="date"]')).toBe(date);
    expect(date).toHaveFocus();
  });

  it('does not replace a newer date result with an older slow response', async () => {
    const { container } = renderSpa();
    await screen.findByText('Selin Kaya');
    const requests = {};
    axios.get.mockImplementation((url, options) => url === '/spa/appointments'
      ? new Promise(resolve => { requests[options.params.date_from] = resolve; })
      : Promise.resolve({ data: dataFor(url) }));
    const date = container.querySelector('input[type="date"]');
    fireEvent.change(date, { target: { value: '2026-11-10' } });
    fireEvent.change(date, { target: { value: '2026-11-11' } });
    const appointment = dataFor('/spa/appointments').appointments[0];
    await act(async () => { requests['2026-11-11']({ data: { appointments: [{ ...appointment, guest_name: 'Ayla Deniz' }] } }); });
    expect(await screen.findByText('Ayla Deniz')).toBeVisible();
    await act(async () => { requests['2026-11-10']({ data: { appointments: [{ ...appointment, guest_name: 'Esin Arda' }] } }); });
    expect(screen.getByText('Ayla Deniz')).toBeVisible();
    expect(screen.queryByText('Esin Arda')).not.toBeInTheDocument();
    expect(date).toHaveValue('2026-11-11');
  });

  it('opens the availability tab and shows only slots with a therapist and room', async () => {
    axios.get.mockImplementation(async (url) => ({ data: url === '/spa/availability' ? {
      timezone: 'Europe/Istanbul',
      slots: [
        { starts_at: '2026-11-08T07:00:00Z', any_available: false },
        { starts_at: '2026-11-08T07:30:00Z', ends_at: '2026-11-08T08:30:00Z', any_available: true,
          therapists: [{ available: true, therapist_name: 'Ayşe' }], rooms: [{ id: 'room', name: 'Islak Oda' }] },
      ],
    } : dataFor(url) }));
    renderSpa();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Randevu' })).toBeEnabled());
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Gelişmiş Müsaitlik' }), { button: 0 });
    const panel = screen.getByRole('tabpanel', { name: 'Gelişmiş Müsaitlik' });
    fireEvent.change(within(panel).getByLabelText('Hizmet'), { target: { value: 's' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Müsait saatleri göster' }));
    expect(await within(panel).findByText('08.11 10:30 – 08.11 11:30')).toBeVisible();
    expect(within(panel).getByText('Odalar · Islak Oda')).toBeVisible();
    expect(axios.get).toHaveBeenCalledWith('/spa/availability', { params: { date: '2026-11-08', service_id: 's' } });
  });

  it('finds historical appointments without guessing the identity of same-name guests', async () => {
    const first = { id: 'legacy', guest_name: 'Selin Kaya', starts_at: '2026-11-08T09:00:00Z',
      status: 'completed', service_name: 'Masaj', price: 100, currency: 'TRY' };
    const linked = { ...first, id: 'linked', guest_id: 'g', service_name: 'Hamam', currency: 'EUR' };
    axios.get.mockImplementation(async (url) => ({ data: {
      '/spa/guests/history/search': { appointments: [first, linked] },
      '/spa/guests/g/history': { appointments: [linked] },
    }[url] ?? dataFor(url) }));
    renderSpa();
    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Misafir Geçmişi' }), { button: 0 });
    const panel = screen.getByRole('tabpanel', { name: 'Misafir Geçmişi' });
    fireEvent.change(within(panel).getByLabelText('Misafir adı'), { target: { value: 'Selin Kaya' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Geçmişi ara' }));
    expect(await within(panel).findByText(/Masaj ·/)).toBeVisible();
    expect(within(panel).getAllByRole('button', { name: 'Selin Kaya profil geçmişi' })).toHaveLength(1);
    fireEvent.click(within(panel).getByRole('button', { name: 'Selin Kaya profil geçmişi' }));
    expect(await within(panel).findByText('Selin Kaya · Profil geçmişi')).toBeVisible();
    expect(within(panel).queryByText(/Masaj ·/)).not.toBeInTheDocument();
    expect(within(panel).getByText(/Hizmet bedeli.*€/)).toBeVisible();
  });

  it('blocks new unbillable service snapshots until VAT is explicitly configured', async () => {
    axios.get.mockImplementation(async (url) => ({ data: url === '/spa/services'
      ? { services: [{ id: 's', name: 'Bakım', duration_minutes: 60, price: 100, currency: 'TRY' }] }
      : dataFor(url) }));
    const { container } = await openBooking();
    fireEvent.change(container.querySelector('form select'), { target: { value: 's' } });
    expect(screen.getByRole('alert')).toHaveTextContent('KDV oranı tanımlanmamış');
    expect(screen.getByRole('button', { name: 'cm.pages_SpaWellness.randevu_olustur' })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('opens with the current HOTEL time instead of the UTC clock', async () => {
    const { container } = await openBooking();
    expect(container.querySelector('input[type="datetime-local"]')).toHaveValue('2026-11-08T12:23');
    expect(screen.getByText(/Tesis saati.*Europe\/Istanbul/)).toBeInTheDocument();
  });

  it('sends a manually selected hotel wall time as an explicit UTC instant once', async () => {
    const { container } = await openBooking();
    const form = container.querySelector('form');
    fireEvent.change(form.querySelector('select'), { target: { value: 's' } });
    fireEvent.change(form.querySelector('input[type="datetime-local"]'), { target: { value: '2026-11-15T12:30' } });
    fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: 'Selin Kaya' } });
    fireEvent.submit(form);
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/spa/appointments', expect.objectContaining({
      starts_at: '2026-11-15T09:30:00.000Z', guest_name: 'Selin Kaya', folio_id: null,
    })));
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it('renders existing appointment instants in the same verified hotel timezone', async () => {
    renderSpa();
    expect(await screen.findByText('08.11 12:00')).toBeInTheDocument();
  });

  it('does not replace the hotel daily-summary default with a UTC calendar date', async () => {
    vi.setSystemTime(new Date('2026-11-08T22:30:00Z'));
    await openBooking();
    expect(axios.get).toHaveBeenCalledWith('/spa/daily-summary');
    expect(axios.get.mock.calls.filter(([url]) => url === '/spa/daily-summary').every((call) => call.length === 1)).toBe(true);
  });

  it('does not allow booking when the hotel timezone has not been verified', async () => {
    axios.get.mockImplementation(async (url) => {
      if (url === '/spa/daily-summary') throw new Error('summary unavailable');
      return { data: dataFor(url) };
    });
    renderSpa();
    await screen.findByRole('button', { name: 'Randevu' });
    expect(screen.getByRole('button', { name: 'Randevu' })).toBeDisabled();
    expect(await screen.findByRole('status')).toHaveTextContent('Tesis saat dilimi doğrulanamadı');
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('uses the configured hotel zone even when it differs from Istanbul', async () => {
    axios.get.mockImplementation(async (url) => ({ data: dataFor(url, 'America/New_York') }));
    const { container } = await openBooking();
    expect(container.querySelector('input[type="datetime-local"]')).toHaveValue('2026-11-08T04:23');
    expect(screen.getByText(/Tesis saati.*America\/New_York/)).toBeInTheDocument();
  });

  it('refreshes the default clock on reopening instead of keeping page-load time', async () => {
    const { container } = await openBooking();
    fireEvent.click(screen.getByRole('button', { name: 'cm.pages_SpaWellness.iptal_25174' }));
    vi.setSystemTime(new Date('2026-11-08T09:28:00Z'));
    fireEvent.click(screen.getByRole('button', { name: 'Randevu' }));
    expect(container.querySelector('input[type="datetime-local"]')).toHaveValue('2026-11-08T12:28');
    expect(axios.post).not.toHaveBeenCalled();
  });
});
