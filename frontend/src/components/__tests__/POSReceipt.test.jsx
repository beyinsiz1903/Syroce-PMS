import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import POSReceipt from '../POSReceipt';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('customer receipt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
