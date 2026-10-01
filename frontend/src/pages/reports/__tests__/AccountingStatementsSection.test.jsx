import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AccountingStatementsSection from '../AccountingStatementsSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/api/axios', () => ({ default: { get } }));

describe('AccountingStatementsSection', () => {
  beforeEach(() => get.mockReset());

  it('loads the real GL trial balance endpoint and renders account balances', async () => {
    get.mockResolvedValue({ data: {
      rows: [{ account_code: '100', account_name: 'Kasa', total_debit: 1500, total_credit: 500, debit_balance: 1000, credit_balance: 0 }],
      totals: { debit_balance: 1000, credit_balance: 1000, balanced: true },
    } });

    render(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-27" reportPeriod="monthly" />);

    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/trial-balance', { params: { as_of: '2026-09-27' } }));
    expect(await screen.findByText('Kasa')).toBeInTheDocument();
    expect(screen.getByText('Dengeli')).toBeInTheDocument();
  });

  it('uses the selected reporting period for the income statement', async () => {
    get.mockResolvedValue({ data: {
      revenue: [], expenses: [], totals: { revenue: 0, expenses: 0, net_income: 0 },
    } });

    render(<AccountingStatementsSection type="income_statement" reportDate="2026-09-27" reportPeriod="monthly" />);

    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/statements/income-statement', {
      params: { start: '2026-08-29', end: '2026-09-27' },
    }));
    expect(await screen.findByText('Bu dönem için muhasebeleşmiş hareket bulunmuyor.')).toBeInTheDocument();
  });

  it('loads journal entries for the selected period', async () => {
    get.mockResolvedValue({ data: { entries: [{
      id: 'entry-1', entry_no: 'YEV-2026-001', date: '2026-09-27', memo: 'Gün sonu kaydı', source: 'night_audit',
      lines: [{ debit: 250, credit: 0 }, { debit: 0, credit: 250 }],
    }] } });

    render(<AccountingStatementsSection type="journal" reportDate="2026-09-27" reportPeriod="daily" />);

    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/journal', {
      params: { start: '2026-09-27', end: '2026-09-27' },
    }));
    expect(await screen.findByText('YEV-2026-001')).toBeInTheDocument();
    expect(screen.getByText('Gün sonu kaydı')).toBeInTheDocument();
  });
});
