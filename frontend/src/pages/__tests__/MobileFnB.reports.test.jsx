import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: vi.fn(),
  },
}));

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-09-30' }));

import MobileFnB from '@/pages/MobileFnB';

describe('MobileFnB report scope', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/outlets') {
        return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Ana Restoran', status: 'active' }] } });
      }
      if (url === '/pos/daily-summary') {
        return Promise.resolve({ data: {
          total_sales: 150,
          transaction_count: 2,
          average_transaction: 75,
          top_items: [{ name: 'Türk Kahvesi', quantity: 3, revenue: 90 }],
        } });
      }
      if (url === '/pos/transactions') return Promise.resolve({ data: { transactions: [] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url === '/pos/z-report') return Promise.resolve({ data: { report_date: '2026-09-30' } });
      if (url === '/pos/void-transactions') return Promise.resolve({ data: { void_transactions: [] } });
      throw new Error(`Unexpected GET ${url}`);
    });
  });

  it('uses the PMS business date and active outlet for every daily report', async () => {
    render(<MobileFnB />);

    await waitFor(() => expect(axiosGet).toHaveBeenCalledWith('/pos/daily-summary', {
      params: { date: '2026-09-30', outlet_id: 'outlet-1' },
    }));

    fireEvent.click(screen.getByText('Z Raporu'));
    await waitFor(() => expect(axiosGet).toHaveBeenCalledWith('/pos/z-report', {
      params: { date: '2026-09-30', outlet_id: 'outlet-1' },
    }));

    fireEvent.click(screen.getByText('İptal Raporu'));
    await waitFor(() => expect(axiosGet).toHaveBeenCalledWith('/pos/void-transactions', {
      params: { date: '2026-09-30', outlet_id: 'outlet-1' },
    }));
  });

  it('shows actual sold quantity and revenue instead of the first menu items', async () => {
    render(<MobileFnB />);
    fireEvent.click(await screen.findByText('Günlük Satış Özetini Gör'));

    expect(await screen.findByText('Türk Kahvesi')).toBeInTheDocument();
    expect(screen.getByText('3 adet')).toBeInTheDocument();
  });
});
