import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, put, post, toast } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('axios', () => ({ default: { get, put, post } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').pop() }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', currencySymbol: () => '₺', formatCurrency: value => String(value) }));
import UpsellTab from '../UpsellTab';
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const bookings = ['Ada', 'Deniz'].map((name, index) => ({ id: `b${index}`, guest_name: name, status: 'checked_in', room_number: `${index + 101}` }));
const offers = bookings.map((booking, index) => ({ id: `o${index}`, booking_id: booking.id, target_item: `Teklif ${booking.guest_name}`, type: 'late_checkout', status: 'pending', price: 35, currency: 'TRY' }));
beforeEach(() => {
  get.mockReset(); put.mockReset(); post.mockReset(); toast.error.mockReset(); toast.success.mockReset();
  get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/offers') ? { offers } : url.endsWith('/settings') ? { prices: { late_checkout: 35, early_checkin: 25, airport_transfer: 50 }, defaults: {} } : {} }));
  put.mockResolvedValue({ data: {} });
});
afterEach(cleanup);

it('does not overwrite the new reservation with a late regenerate response', async () => {
  render(<UpsellTab bookings={bookings} />);
  await waitFor(() => expect(get).toHaveBeenCalledWith('/ai/upsell/offers'));
  fireEvent.click(screen.getByText('Ada', { exact: true }));
  await screen.findByText('Teklif Ada');
  const pending = deferred(); post.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByRole('button', { name: /yeniden/i }));
  fireEvent.click(screen.getByText('Deniz', { exact: true }));
  await act(async () => pending.resolve({ data: { offers: [{ ...offers[0], target_item: 'Yanlış eski yanıt' }], total_offers: 1 } }));
  expect(screen.queryByText('Yanlış eski yanıt')).not.toBeInTheDocument();
  expect(screen.getAllByText('Teklif Deniz').length).toBeGreaterThan(0);
});

it('does not permit saving settings after their authoritative read failed', async () => {
  render(<UpsellTab />);
  get.mockImplementation(url => url.endsWith('/settings') ? Promise.reject(new Error('offline')) : Promise.resolve({ data: {} }));
  fireEvent.click(screen.getByTestId('btn-upsell-settings'));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Fiyat ayarları yüklenemedi'));
  expect(screen.getByTestId('btn-save-upsell-prices')).toBeDisabled();
});

it('rejects excess decimals and out-of-range prices instead of silently rounding them', async () => {
  render(<UpsellTab />);
  fireEvent.click(screen.getByTestId('btn-upsell-settings'));
  const input = await screen.findByDisplayValue('35');
  fireEvent.change(input, { target: { value: '35.001' } });
  fireEvent.click(screen.getByTestId('btn-save-upsell-prices'));
  expect(put).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '1000001' } });
  fireEvent.click(screen.getByTestId('btn-save-upsell-prices'));
  expect(put).not.toHaveBeenCalled();
});

it('ignores a late settings read from a closed dialog', async () => {
  render(<UpsellTab />);
  const old = deferred(); const current = deferred(); let reads = 0;
  get.mockImplementation(url => url.endsWith('/settings') ? (++reads === 1 ? old.promise : current.promise) : Promise.resolve({ data: {} }));
  fireEvent.click(screen.getByTestId('btn-upsell-settings'));
  fireEvent.click(screen.getByRole('button', { name: 'vazgec', exact: true }));
  fireEvent.click(screen.getByTestId('btn-upsell-settings'));
  await act(async () => current.resolve({ data: { prices: { late_checkout: 40 }, defaults: {} } }));
  await act(async () => old.resolve({ data: { prices: { late_checkout: 999 }, defaults: {} } }));
  expect(screen.getByDisplayValue('40')).toBeInTheDocument();
  expect(screen.queryByDisplayValue('999')).not.toBeInTheDocument();
});

it('keeps explicit zero prices and does not send a duplicate save', async () => {
  render(<UpsellTab />);
  fireEvent.click(screen.getByTestId('btn-upsell-settings'));
  const input = await screen.findByDisplayValue('35');
  fireEvent.change(input, { target: { value: '0' } });
  const pending = deferred(); put.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByTestId('btn-save-upsell-prices'));
  fireEvent.click(screen.getByTestId('btn-save-upsell-prices'));
  expect(put).toHaveBeenCalledTimes(1);
  expect(put.mock.calls[0][1].prices.late_checkout).toBe(0);
  expect(input).toBeDisabled();
  await act(async () => pending.resolve({ data: {} }));
});
