import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AccountingStatementsSection from '../AccountingStatementsSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/api/axios', () => ({ default: { get } }));

describe('AccountingStatementsSection', () => {
  beforeEach(() => { get.mockReset(); });

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

  it('does not mark an empty trial balance as unbalanced when the API omits the legacy balanced flag', async () => {
    get.mockResolvedValue({ data: {
      rows: [],
      totals: { debit_balance: 0, credit_balance: 0 },
    } });

    render(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-27" reportPeriod="daily" />);

    expect(await screen.findByText('Dengeli — kayıt yok')).toBeInTheDocument();
    expect(screen.queryByText('Dengesiz')).not.toBeInTheDocument();
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

    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/reports/journal', {
      params: { start: '2026-09-27', end: '2026-09-27', limit: 200, offset: 0 },
    }));
    expect(await screen.findByText('YEV-2026-001')).toBeInTheDocument();
    expect(screen.getByText('Gün sonu kaydı')).toBeInTheDocument();
  });

  it('does not claim balance when legacy totals disagree or are unknown', async () => {
    get.mockResolvedValueOnce({ data: { rows: [{ account_code: '100', account_name: 'Kasa' }], totals: { debit_balance: 100, credit_balance: 90 } } });
    const view = render(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-27" reportPeriod="daily" />);
    expect(await screen.findByText('Dengesiz')).toBeInTheDocument();
    get.mockResolvedValueOnce({ data: { rows: [{ account_code: '100', account_name: 'Kasa' }] } });
    view.rerender(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-28" reportPeriod="daily" />);
    expect(await screen.findByText('Kontrol verisi eksik')).toBeInTheDocument();
    expect(screen.queryByText('Dengeli')).not.toBeInTheDocument();
  });

  it('ignores a late response for a previous date and clears stale data on failure', async () => {
    let finishOld;
    get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    get.mockResolvedValueOnce({ data: { rows: [{ account_code: '200', account_name: 'Yeni dönem' }], totals: { debit_balance: 0, credit_balance: 0 } } });
    const view = render(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-27" reportPeriod="daily" />);
    view.rerender(<AccountingStatementsSection type="gl_trial_balance" reportDate="2026-09-28" reportPeriod="daily" />);
    expect(await screen.findByText('Yeni dönem')).toBeInTheDocument();
    await act(async () => finishOld({ data: { rows: [{ account_code: '100', account_name: 'Eski dönem' }] } }));
    expect(screen.queryByText('Eski dönem')).not.toBeInTheDocument();
    get.mockRejectedValueOnce(new Error('Bağlantı hatası'));
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    expect(await screen.findByText('Bağlantı hatası')).toBeInTheDocument();
    expect(screen.queryByText('Yeni dönem')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel' })).toBeDisabled();
  });

  it('downloads Excel through the authenticated client with the displayed filters', async () => {
    get.mockResolvedValueOnce({ data: { entries: [] } });
    get.mockResolvedValueOnce({ data: new Blob(['xlsx']) });
    const create = vi.fn(() => 'blob:test');
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
    render(<AccountingStatementsSection type="journal" reportDate="2026-09-27" reportPeriod="monthly" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Excel' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Excel' }));
    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/reports/export', {
      params: { report: 'journal', format: 'xlsx', start: '2026-08-29', end: '2026-09-27' }, responseType: 'blob',
    }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    click.mockRestore();
    vi.unstubAllGlobals();
  });

  it('shows current earnings so equity detail reconciles to the balance sheet total', async () => {
    get.mockResolvedValue({ data: {
      assets: [{ account_code: '100', account_name: 'Kasa', amount: 60 }], liabilities: [], equity: [],
      current_earnings: { amount: 60 }, totals: { assets: 60, liabilities_and_equity: 60, balanced: true },
    } });
    render(<AccountingStatementsSection type="balance_sheet" reportDate="2026-09-27" reportPeriod="daily" />);
    expect(await screen.findByText('Dönem net sonucu')).toBeInTheDocument();
  });

  it('paginates posted journal rows and resets the page when the period changes', async () => {
    get.mockResolvedValue({ data: { entries: [{ id: '1', entry_no: 'YEV-1', lines: [] }], total: 201, has_more: true } });
    const view = render(<AccountingStatementsSection type="journal" reportDate="2026-09-27" reportPeriod="daily" />);
    await screen.findByText('YEV-1');
    fireEvent.click(screen.getByRole('button', { name: 'Sonraki sayfa' }));
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/gl/reports/journal', {
      params: { start: '2026-09-27', end: '2026-09-27', limit: 200, offset: 200 },
    }));
    view.rerender(<AccountingStatementsSection type="journal" reportDate="2026-09-28" reportPeriod="daily" />);
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/gl/reports/journal', {
      params: { start: '2026-09-28', end: '2026-09-28', limit: 200, offset: 0 },
    }));
  });
});
