import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import POSRoomChargeReversal from './POSRoomChargeReversal';
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), warning: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const source = { order_id: 'order-1', order_number: 'ORD-1', payment_method: 'room_charge', total: 132, refunded_amount: 0, currency: 'TRY', business_date: '2026-11-11' };
const start = async props => {
  axios.get.mockResolvedValue({ data: source });
  render(<POSRoomChargeReversal orderId="order-1" {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'POS kaynak kaydını geri al' }));
  await screen.findByText(/ORD-1/);
  fireEvent.change(screen.getByLabelText('İşlem nedeni'), { target: { value: 'Tam ikram eski kaynak düzeltmesi' } });
};
describe('guest-card POS source reversal', () => {
  it('retries the identical source request after a lost response, without a standalone folio payment', async () => {
    axios.post.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ data: {} });
    const onChanged = vi.fn();
    await start({ onChanged });
    fireEvent.click(screen.getByRole('button', { name: 'POS ve folyo ters kaydını onayla' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('İşlem nedeni')).toBeDisabled();
    const first = axios.post.mock.calls[0];
    expect(first[0]).toBe('/pos/v2/orders/order-1/refund');
    expect(first[1]).toEqual({ reason: 'Tam ikram eski kaynak düzeltmesi', idempotency_key: expect.any(String) });
    fireEvent.click(screen.getByRole('button', { name: 'POS ve folyo ters kaydını onayla' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(axios.post.mock.calls[1]).toEqual(first);
    expect(axios.post).toHaveBeenCalledTimes(2);
  });
  it.each([{ ...source, payment_method: 'cash' }, { ...source, order_id: 'different' }])('rejects a mismatched source or non-room tender', async data => {
    axios.get.mockResolvedValue({ data });
    render(<POSRoomChargeReversal orderId="order-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'POS kaynak kaydını geri al' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: 'POS ve folyo ters kaydını onayla' })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('does not present a committed reversal as failed when refresh fails', async () => {
    axios.post.mockResolvedValue({ data: {} });
    await start({ onChanged: vi.fn().mockRejectedValue(new Error('refresh')) });
    fireEvent.click(screen.getByRole('button', { name: 'POS ve folyo ters kaydını onayla' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(axios.post).toHaveBeenCalledOnce();
  });
});
