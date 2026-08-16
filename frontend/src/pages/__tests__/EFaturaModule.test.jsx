import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import EFaturaModule from '../EFaturaModule';
import { confirmDialog } from '@/lib/dialogs';

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

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/pos/daily-closure'));
    expect(axios.post).toHaveBeenCalledTimes(1);
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
