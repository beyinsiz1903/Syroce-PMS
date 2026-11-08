import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
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

async function openBooking() {
  const result = render(<SpaWellness tenant={{ currency: 'TRY' }} />);
  await waitFor(() => expect(axios.get.mock.calls.some(([url]) => url === '/spa/daily-summary')).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Randevu' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Randevu' }));
  return result;
}

describe('SPA hotel wall clock, independent of browser UTC', () => {
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
    render(<SpaWellness />);
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
    render(<SpaWellness />);
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
