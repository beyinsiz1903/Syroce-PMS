import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TrialBalancePage from '../TrialBalancePage';

const get = vi.fn();

vi.mock('@/api/axios', () => ({ default: { get: (...args) => get(...args) } }));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-07' }));

const response = {
  date: '2026-10-01',
  generated_at: '2026-10-01T09:00:00Z',
  currency: 'TRY',
  occupancy: { occupancy_pct: 29.4, occupied: 5, total_rooms: 17, out_of_order: 0, basis: 'actual_stay_nights' },
  movements: { arrivals: 0, departures: 0, in_house: 5, no_shows: 0 },
  revenue: {
    rooms: 5000, fnb: 0, other: 0, total: 5000, adr: 1000, revpar: 294.12,
    by_category: {}, room_revenue_source: 'accrued', posting_pending: true,
  },
  payments: { total: 0, by_method: {} },
  ledger: { ar_balance: 0, deposit_balance: 0, open_folios: 5 },
  balance_check: { in_balance: false, revenue_minus_payments: 5000 },
  last_night_audit: null,
};

describe('TrialBalancePage', () => {
  beforeEach(() => get.mockReset());

  it('explains accrued room revenue before Night Audit instead of showing zero ADR', async () => {
    get.mockResolvedValue({ data: response });
    render(<TrialBalancePage reportDate="2026-10-01" />);

    await waitFor(() => expect(get).toHaveBeenCalledWith('/trial-balance', { params: { date: '2026-10-01' } }));
    expect(await screen.findByTestId('room-revenue-source-notice')).toHaveTextContent('tahakkuk eden konaklama tutarı');
    expect(screen.getByText(/Tahakkuk eden/)).toBeInTheDocument();
    expect(screen.getByText('Günlük gelir ve tahsilat farklı')).toBeInTheDocument();
    expect(screen.getByText(/Bu bir muhasebe dengesizliği değildir/)).toBeInTheDocument();
  });

  it('renders every native currency instead of turning a mixed scalar into TRY zero', async () => {
    get.mockResolvedValue({ data: {
      ...response,
      revenue: { ...response.revenue, rooms: null, total: null, net_total: null, adr: null,
        rooms_by_currency: { EUR: 100, TRY: 20 }, total_by_currency: { EUR: 100, TRY: 20 }, net_total_by_currency: { EUR: 95, TRY: 20 },
        adjustments_by_currency: { EUR: 5 }, adr_by_currency: { EUR: 50, TRY: 10 }, by_category: { spa: null }, by_category_currency: { spa: { EUR: 10, TRY: 5 } } },
      payments: { total: null, total_by_currency: { EUR: 40, TRY: 5 }, by_method: { cash: { total: null, count: 2, by_currency: { EUR: 40, TRY: 5 } } } },
      balance_check: { in_balance: false, revenue_minus_payments: null, by_currency: { EUR: 55, TRY: 15 } },
      ledger: { ...response.ledger, ar_balance: null, ar_balance_by_currency: { EUR: 70, TRY: 30 }, snapshot_scope: 'current' },
    } });
    render(<TrialBalancePage reportDate="2026-10-01" />);
    await screen.findByTestId('current-ledger-scope');
    expect(screen.getAllByText(text => text.includes('EUR:') && text.includes('95,00')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(text => text.includes('EUR:') && text.includes('40,00')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('current-ledger-scope')).toHaveTextContent('tarihsel kapanış bakiyesi değildir');
    expect(screen.queryByText('₺120,00')).not.toBeInTheDocument();
  });

  it('does not let a previous date response overwrite the selected daily reconciliation', async () => {
    let finishOld;
    get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    get.mockResolvedValueOnce({ data: { ...response, revenue: { ...response.revenue, total: 777, net_total: 777 } } });
    const view = render(<TrialBalancePage reportDate="2026-10-01" />);
    view.rerender(<TrialBalancePage reportDate="2026-10-02" />);
    await waitFor(() => expect(screen.getAllByText(/777,00/).length).toBeGreaterThan(0));
    await act(async () => finishOld({ data: { ...response, revenue: { ...response.revenue, total: 999 } } }));
    expect(screen.queryByText(/999,00/)).not.toBeInTheDocument();
    expect(screen.getByTestId('input-tb-date')).toHaveValue('2026-10-02');
  });

  it('clears stale monetary results after a refresh fails and does not claim balance', async () => {
    get.mockResolvedValueOnce({ data: response });
    get.mockRejectedValueOnce(new Error('Defter bağlantısı kesildi'));
    render(<TrialBalancePage reportDate="2026-10-01" />);
    await screen.findByTestId('room-revenue-source-notice');
    fireEvent.click(screen.getByTestId('button-tb-refresh'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Defter bağlantısı kesildi');
    expect(screen.getByRole('alert')).toHaveTextContent('sıfır bakiye veya dengeli sonuç anlamına gelmez');
    expect(screen.queryByText('Günlük gelir ve tahsilat farklı')).not.toBeInTheDocument();
    expect(screen.queryByTestId('room-revenue-source-notice')).not.toBeInTheDocument();
  });

  it('rejects a cleared date without requesting the calendar day as a fallback', async () => {
    get.mockResolvedValue({ data: response });
    render(<TrialBalancePage reportDate="2026-10-01" />);
    await screen.findByTestId('room-revenue-source-notice');
    fireEvent.change(screen.getByTestId('input-tb-date'), { target: { value: '' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli bir rapor tarihi');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('defaults the request to the PMS business day', async () => {
    get.mockResolvedValue({ data: response });
    render(<TrialBalancePage />);
    await waitFor(() => expect(get).toHaveBeenCalledWith('/trial-balance', { params: { date: '2026-10-07' } }));
  });

  it('does not replace an explicitly empty report-center date with the business day', async () => {
    render(<TrialBalancePage reportDate="" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli bir rapor tarihi');
    expect(get).not.toHaveBeenCalled();
  });
});
