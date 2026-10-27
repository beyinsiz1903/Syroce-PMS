import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import EFaturaModule from '../EFaturaModule';
import { confirmDialog } from '@/lib/dialogs';
import { toast } from 'sonner';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

describe('EFaturaModule POS closure integrity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn(() => 'blob:pos-report');
    window.URL.revokeObjectURL = vi.fn();
    axios.get.mockImplementation((url) => {
      if (url === '/efatura/invoices') return Promise.resolve({ data: { invoices: [] } });
      if (url === '/pos/daily-closures') return Promise.resolve({ data: { closures: [] } });
      if (url === '/efatura/settings') return Promise.resolve({ data: { enabled: false } });
      if (url === '/pos/daily-closure-preview') return Promise.resolve({ data: {
        closure_date: '2026-10-25', preview_hash: 'a'.repeat(64),
        totals_by_currency: { TRY: { net_sales: 350, tips: 50 } },
      } });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  it('does not write a financial closure when confirmation is declined', async () => {
    confirmDialog.mockResolvedValue(false);
    render(<EFaturaModule />);

    const button = await screen.findByRole('button', { name: /daily pos closure/i });
    fireEvent.click(button);

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledOnce());
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('creates at most one closure after explicit confirmation', async () => {
    confirmDialog.mockResolvedValue(true);
    axios.post.mockResolvedValue({ data: { total_sales: 400, replayed: false } });
    render(<EFaturaModule />);

    const button = await screen.findByRole('button', { name: /daily pos closure/i });
    fireEvent.click(button);

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/pos/daily-closure', {
      business_date: '2026-10-25', expected_preview_hash: 'a'.repeat(64), reason: expect.any(String),
    }));
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it('does not close or show a fake zero when preview fails', async () => {
    axios.get.mockImplementation((url) => url === '/pos/daily-closure-preview'
      ? Promise.reject({ response: { data: { detail: { message: 'Kaynak doğrulanamadı' } } } })
      : Promise.resolve({ data: {} }));
    render(<EFaturaModule />);
    fireEvent.click(await screen.findByRole('button', { name: /daily pos closure/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Kaynak doğrulanamadı'));
    expect(axios.post).not.toHaveBeenCalled();
    expect(confirmDialog).not.toHaveBeenCalled();
  });

  it('renders each native currency separately and labels room charge as non-cash', async () => {
    axios.get.mockResolvedValue({ data: { closures: [{ id: 'multi', closure_date: '2026-10-25', transaction_count: 2,
      totals_by_currency: { USD: { net_sales: 100, tips: 5, refund_total: 0, cash_sales: 105, card_sales: 0, room_charge_sales: 0 },
        EUR: { net_sales: 50, tips: 0, refund_total: 10, cash_sales: 0, card_sales: 0, room_charge_sales: 50 } } }] } });
    render(<EFaturaModule />);
    expect(await screen.findAllByText(/Gelir:/)).toHaveLength(2);
    expect(screen.getAllByText(/tahsilat değil/)).toHaveLength(2);
  });

  it('downloads the selected closure report without another financial write', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/efatura/invoices') return Promise.resolve({ data: { invoices: [] } });
      if (url === '/pos/daily-closures') {
        return Promise.resolve({
          data: {
            closures: [{
              id: 'closure-1',
              closure_date: '2026-08-17',
              transaction_count: 2,
              total_sales: 400,
              cash_sales: 100,
              card_sales: 300,
              other_sales: 0,
            }],
          },
        });
      }
      if (url === '/efatura/settings') return Promise.resolve({ data: { enabled: false } });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<EFaturaModule />);

    fireEvent.click(await screen.findByRole('button', { name: /report/i }));

    expect(window.URL.createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(axios.post).not.toHaveBeenCalled();
  });
});
