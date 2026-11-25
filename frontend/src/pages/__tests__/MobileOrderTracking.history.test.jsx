import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import MobileOrderTracking from '../MobileOrderTracking';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/components/PropertySwitcher', () => ({ default: () => null }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/night-audit/business-date'
    ? { business_date: '2026-11-12' } : url === '/pos/mobile/order-history'
      ? { orders: [{ id: 'refund', order_number: 'ORD-REFUND', status: 'refunded', total_amount: 44, currency: 'TRY' },
        { id: 'cancel', order_number: 'ORD-CANCEL', status: 'cancelled', total_amount: 0, currency: 'TRY' }] }
      : { orders: [] } }));
});
const open = async () => {
  render(<MemoryRouter><MobileOrderTracking user={{ role: 'admin' }} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: 'Sipariş geçmişi' }));
};
it('uses seven inclusive PMS business dates instead of the computer calendar date', async () => {
  await open();
  await screen.findByText('#ORD-REFUND');
  expect(axios.get).toHaveBeenCalledWith('/pos/mobile/order-history', { params: {
    start_date: '2026-11-06', end_date: '2026-11-12', limit: 50,
  } });
  expect(screen.getByText('İade Edildi')).toBeVisible();
  expect(screen.getByText('İptal Edildi')).toBeVisible();
});
it('allows an explicit historical range and rejects an inverted range without another query', async () => {
  await open(); await screen.findByText('#ORD-REFUND');
  fireEvent.change(screen.getByLabelText('Sipariş geçmişi başlangıç'), { target: { value: '2026-11-10' } });
  fireEvent.click(screen.getByRole('button', { name: 'Dönemi göster' }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/pos/mobile/order-history', { params: {
    start_date: '2026-11-10', end_date: '2026-11-12', limit: 50,
  } }));
  await screen.findByText('#ORD-REFUND');
  const before = axios.get.mock.calls.filter(([url]) => url === '/pos/mobile/order-history').length;
  fireEvent.change(screen.getByLabelText('Sipariş geçmişi başlangıç'), { target: { value: '2026-11-13' } });
  fireEvent.click(screen.getByRole('button', { name: 'Dönemi göster' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli tarih aralığı');
  expect(axios.get.mock.calls.filter(([url]) => url === '/pos/mobile/order-history')).toHaveLength(before);
});
it('does not silently substitute the computer date when PMS business day cannot be read', async () => {
  const original = axios.get.getMockImplementation();
  axios.get.mockImplementation(url => url === '/night-audit/business-date' ? Promise.reject(new Error('unavailable')) : original(url));
  await open();
  expect(await screen.findByRole('alert')).toHaveTextContent('PMS iş günü alınamadı');
  expect(axios.get.mock.calls.some(([url]) => url === '/pos/mobile/order-history')).toBe(false);
});

it('distinguishes a failed history request from a successful empty period', async () => {
  const original = axios.get.getMockImplementation();
  axios.get.mockImplementation(url => url === '/pos/mobile/order-history' ? Promise.reject(new Error('unavailable')) : original(url));
  await open();
  expect(await screen.findByRole('alert')).toHaveTextContent('boş liste sonucu');
  expect(screen.queryByText('Seçilen dönemde sipariş bulunamadı.')).not.toBeInTheDocument();
  axios.get.mockImplementation(url => url === '/pos/mobile/order-history' ? Promise.resolve({ data: { orders: [] } }) : original(url));
  fireEvent.click(screen.getByRole('button', { name: 'Dönemi göster' }));
  expect(await screen.findByText('Seçilen dönemde sipariş bulunamadı.')).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
