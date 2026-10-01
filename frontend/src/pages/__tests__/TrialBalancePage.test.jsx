import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TrialBalancePage from '../TrialBalancePage';

const get = vi.fn();

vi.mock('@/api/axios', () => ({ default: { get: (...args) => get(...args) } }));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));

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
});
