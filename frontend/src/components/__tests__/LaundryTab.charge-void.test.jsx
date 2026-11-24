import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { get, post, patch, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('axios', () => ({ default: { get, post, patch } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').pop() }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: value => String(value) }));
import LaundryTab from '@/components/pms/LaundryTab';
const source = { id: 'delivered-25', room_number: '117', guest_name: 'Deniz', status: 'delivered', folio_charged: true,
  total: 25, folio_financial_total: 25, currency: 'TRY', folio_currency: 'TRY', items: [{ name: 'Atkı', quantity: 1 }] };
let orders;
beforeEach(() => {
  orders = [{ ...source }]; get.mockReset(); post.mockReset(); patch.mockReset(); toast.success.mockReset();
  get.mockImplementation(async url => ({ data: url === '/laundry/items' ? { items: [] } : { orders } }));
  post.mockImplementation(async () => { orders = [{ ...source, financial_voided: true, folio_financial_total: 0 }]; return { data: { success: true } }; });
});
async function open() { render(<LaundryTab />); fireEvent.click(await screen.findByRole('button', { name: 'Ücreti iptal et' })); }
it('requires a reason, preserves physical delivery and never requests a cash refund', async () => {
  await open();
  expect(screen.getByRole('button', { name: 'Ücret iptalini onayla' })).toBeDisabled();
  expect(screen.getByText(/Misafire para iadesi yapılmaz/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Ücret iptal gerekçesi'), { target: { value: 'Hatalı hizmet bedeli, teslim kaydı korunacak' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ücret iptalini onayla' }));
  await screen.findByText('Ücreti iptal edildi');
  expect(post).toHaveBeenCalledExactlyOnceWith('/laundry/orders/delivered-25/void-charge', {
    expected_amount: 25, currency: 'TRY', reason: 'Hatalı hizmet bedeli, teslim kaydı korunacak', request_id: expect.any(String),
  });
  expect(screen.getByText(/Liste bedeli: 25/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Ücreti iptal et' })).not.toBeInTheDocument();
  expect(patch).not.toHaveBeenCalled();
});
it('keeps one request key on a response-unknown retry and leaves rejection visible', async () => {
  post.mockRejectedValueOnce(new Error('network'));
  await open(); fireEvent.change(screen.getByLabelText('Ücret iptal gerekçesi'), { target: { value: 'Kaynak hizmet tutarını geri al' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ücret iptalini onayla' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('sonucu doğrulanamadı');
  fireEvent.click(screen.getByRole('button', { name: 'Ücret iptalini onayla' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
});
it('offers no fee cancellation for a zero-value Full Comp service', async () => {
  orders = [{ ...source, is_complimentary: true, folio_financial_total: 0 }];
  render(<LaundryTab />); await screen.findByText(/Folyoya ikram olarak yansıdı/);
  expect(screen.queryByRole('button', { name: 'Ücreti iptal et' })).not.toBeInTheDocument();
});
