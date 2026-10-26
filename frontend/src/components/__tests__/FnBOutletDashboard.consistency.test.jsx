import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
import FnBOutletDashboard from '@/components/FnBOutletDashboard';

describe('F&B verified financial display', () => {
  beforeEach(() => { get.mockReset(); });

  it('does not turn missing cost into zero profit or relabel EUR sales as TRY', async () => {
    get.mockImplementation(url => Promise.resolve({ data: url === '/pos/outlets' ? { outlets: [] } : {
      currency: 'EUR', basis: 'PMS iş günü', period: { start_date: '2026-10-25', end_date: '2026-10-25' },
      summary: { total_revenue: 220, total_cost: null, gross_profit: null, profit_margin: null, cost_basis: 'current_catalog' },
      menu_items: [{ item_name: 'Izgara levrek', quantity_sold: 1, total_revenue: 220, total_cost: null, gross_profit: null }],
    } }));
    render(<FnBOutletDashboard />);
    expect(await screen.findByText('Izgara levrek')).toBeInTheDocument();
    expect(screen.getAllByText('Doğrulanamadı')).toHaveLength(5);
    expect(screen.getAllByText(/220,00/).every(node => node.textContent.includes('€'))).toBe(true);
    expect(screen.getByText(/geçmiş dönemin kesin kârlılığı değildir/)).toBeInTheDocument();
    expect(screen.getByText('2026-10-25 – 2026-10-25 · PMS iş günü')).toBeInTheDocument();
  });

  it('clears a previous successful report if refreshing fails', async () => {
    let fail = false;
    get.mockImplementation(async url => {
      if (url === '/pos/outlets') return { data: { outlets: [] } };
      if (fail) throw new Error('offline');
      return { data: {
        summary: { total_revenue: 100, total_cost: 20, gross_profit: 80, profit_margin: 80 },
        menu_items: [{ item_name: 'Eski rapor ürünü', quantity_sold: 1, total_revenue: 100, total_cost: 20, gross_profit: 80 }],
      } };
    });
    render(<FnBOutletDashboard />);
    expect(await screen.findByText('Eski rapor ürünü')).toBeInTheDocument();
    fail = true;
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    await waitFor(() => expect(screen.queryByText('Eski rapor ürünü')).not.toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('rapor doğrulanamadı');
  });

  it('shows separate currency totals instead of an aggregate', async () => {
    get.mockResolvedValue({ data: { outlets: [], requires_currency_selection: true,
      totals_by_currency: { EUR: { revenue: 10 }, USD: { revenue: 20 } },
      summary: { total_revenue: null, total_cost: null, gross_profit: null, profit_margin: null },
      report_warnings: ['Farklı para birimleri toplanmadı.'],
    } });
    render(<FnBOutletDashboard />);
    expect(await screen.findByText(/EUR:/)).toHaveTextContent('10,00');
    expect(screen.getByText(/USD:/)).toHaveTextContent(/20[.,]00/);
    expect(screen.getByRole('alert')).toHaveTextContent('toplanmadı');
  });
});
