import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import POSReceipt from '../POSReceipt';
import { confirmDialog } from '@/lib/dialogs';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('customer receipt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    confirmDialog.mockResolvedValue(true);
    axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/receipt') ? {
      header: 'Hotel', order_number: 'ORD1', currency: 'EUR', total: 110, tax_amount: 10,
      items: [{ name: 'Çay', quantity: 1, line_total: 100 }], footer: 'Mali belge değildir.',
    } : { printers: [{ printer_id: 'sim', driver: 'simulator', name: 'Test' }] } }));
  });

  it('shows the saved currency and clearly labels the non-fiscal document', async () => {
    render(<POSReceipt orderId="order1" />);
    fireEvent.click(screen.getByRole('button', { name: /Müşteri fişi/ }));
    expect(await screen.findByText(/Toplam: 110,00\s*€/)).toBeInTheDocument();
    expect(screen.getByText('Mali belge değildir.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Yazıcıya gönder/ })).toBeDisabled();
    expect(axios.get).toHaveBeenCalledWith('/pos/v2/orders/order1/receipt');
  });

  it('does not print a zero-valued receipt after a loading error', async () => {
    axios.get.mockRejectedValue(new Error('unavailable'));
    render(<POSReceipt orderId="order1" />);
    fireEvent.click(screen.getByRole('button', { name: /Müşteri fişi/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('sıfır tutarlı belge oluşturulmadı');
    expect(screen.queryByRole('button', { name: /Tarayıcıdan yazdır/ })).not.toBeInTheDocument();
  });

  it('keeps the same print key after an uncertain response', async () => {
    axios.post.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ data: { success: true, message: 'Simülasyon' } });
    render(<POSReceipt orderId="order1" />);
    fireEvent.click(screen.getByRole('button', { name: /Müşteri fişi/ }));
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'sim' } });
    fireEvent.click(screen.getByRole('button', { name: /Yazıcıya gönder/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Yazıcıya gönder/ })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /Yazıcıya gönder/ }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1]).toEqual(axios.post.mock.calls[0]);
  });
});


describe('historical receipt refund', () => {
  let refunded;
  beforeEach(() => {
    vi.clearAllMocks(); refunded = 0;
    confirmDialog.mockResolvedValue(true);
    axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/receipt') ? {
      header: 'Hotel', order_number: 'ORD1', currency: 'TRY', total: 66,
      refunded_amount: refunded, items: [], footer: 'Mali belge değildir.',
    } : { printers: [] } }));
  });
  const openRefund = async () => {
    render(<POSReceipt orderId="historical-order" />);
    fireEvent.click(screen.getByRole('button', { name: /Müşteri fişi/ }));
    await waitFor(() => expect(screen.getByLabelText('İade nedeni')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('İade nedeni'), { target: { value: 'Sentetik karma ödeme kabulü' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Kalan tutarı iade et' })); });
  };
  it('refunds the original historical order without sending a print job', async () => {
    axios.post.mockImplementation(() => { refunded = 66; return Promise.resolve({ data: { refund_id: 'r' } }); });
    await openRefund();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kalan tutarı iade et' })).toBeDisabled());
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('/pos/v2/orders/historical-order/refund', expect.objectContaining({ amount: 66, reason: 'Sentetik karma ödeme kabulü', idempotency_key: expect.any(String) }));
    expect(await screen.findByText('İade: ₺66,00')).toBeInTheDocument();
  });
  it('does not send after the manager cancels confirmation', async () => {
    confirmDialog.mockResolvedValue(false);
    await openRefund();
    await waitFor(() => expect(confirmDialog).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kalan tutarı iade et' })).toBeEnabled());
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('reconciles a committed timeout without refunding twice', async () => {
    axios.post.mockImplementation(() => { refunded = 66; return Promise.reject(new Error('timeout')); });
    await openRefund();
    const refresh = await screen.findByRole('button', { name: 'İade durumunu yenile' });
    await act(async () => { fireEvent.click(refresh); });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'İade durumunu yenile' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Kalan tutarı iade et' })).toBeDisabled();
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
  it('reuses the frozen request only after an explicit readback and retry', async () => {
    axios.post.mockRejectedValueOnce(new Error('timeout')).mockImplementationOnce(() => { refunded = 66; return Promise.resolve({ data: {} }); });
    await openRefund();
    const refresh = await screen.findByRole('button', { name: 'İade durumunu yenile' });
    await act(async () => { fireEvent.click(refresh); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kalan tutarı iade et' })).toBeEnabled());
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Kalan tutarı iade et' })); });
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1]).toEqual(axios.post.mock.calls[0]);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kalan tutarı iade et' })).toBeDisabled());
  });
});
