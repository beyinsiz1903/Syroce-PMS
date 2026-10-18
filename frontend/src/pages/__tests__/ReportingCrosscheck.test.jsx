import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import CostAnalyticsView from '@/components/cost/CostAnalyticsView';
import AnalyticsExportDashboard from '../AnalyticsExportDashboard';
import NoShowAnalytics from '../NoShowAnalytics';
import CashFlowModal from '@/components/mobile-finance/dialogs/CashFlowModal';
import CashierShiftModal from '@/components/mobile-finance/dialogs/CashierShiftModal';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
const { translate } = vi.hoisted(() => ({ translate: (key, options) => options?.defaultValue || key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-02' }));
vi.mock('@/components/MaybeLayout', () => ({ default: ({ children }) => <>{children}</> }));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>, BarChart: ({ children }) => <div>{children}</div>,
  PieChart: ({ children }) => <div>{children}</div>, Pie: ({ children }) => <div>{children}</div>,
  Bar: () => null, XAxis: () => null, YAxis: () => null, CartesianGrid: () => null, Tooltip: () => null, Legend: () => null, Cell: () => null,
}));

beforeEach(() => vi.clearAllMocks());
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Reporting cross-page integrity', () => {
  it('isolates expense amounts, shares and CSV by selected currency and uses PMS dates', async () => {
    axios.get.mockResolvedValue({ data: [{ currency: 'TRY', category: 'food', total_amount: 100 }, { currency: 'EUR', category: 'food', total_amount: 20 }] });
    render(<CostAnalyticsView />);
    await screen.findAllByText('₺100,00');
    expect(axios.get).toHaveBeenCalledWith('/accounting/expenses', { params: { start_date: '2026-10-01', end_date: '2026-10-02' } });
    expect(screen.queryByText('₺120,00')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Para birimi'), { target: { value: 'EUR' } });
    expect((await screen.findAllByText(/20,00\s*€/)).length).toBeGreaterThan(0);
    expect(screen.queryByText('₺100,00')).not.toBeInTheDocument();
    let blob;
    vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(value => { blob = value; return 'blob:costs'; }); static revokeObjectURL = vi.fn(); });
    vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    fireEvent.click(screen.getByRole('button', { name: 'costAnalytics.exportCsv' }));
    const csv = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob); });
    expect(csv).toContain('"EUR"');
    expect(csv).toContain('"20.00"');
    expect(csv).not.toContain('"100.00"');
  });

  it('does not turn a failed expense load into a verified zero report', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockRejectedValue(new Error('unavailable'));
    render(<CostAnalyticsView />);
    expect(await screen.findByRole('alert')).toHaveTextContent('costAnalytics.loadError');
    expect(screen.queryByText('costAnalytics.kpi.total')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'costAnalytics.exportCsv' })).toBeDisabled();
  });

  it('submits the selected export period and invalidates an old preview when dates change', async () => {
    const fetcher = vi.fn(async (url, init) => new Response(JSON.stringify(init?.method === 'POST'
      ? { success: true, report_type: 'audit_summary', headers: ['Value'], rows: [[12]], row_count: 1 }
      : url.endsWith('/available') ? { reports: [{ type: 'audit_summary', label: 'Denetim' }] } : { history: [] }), { headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetcher);
    render(<AnalyticsExportDashboard />);
    await screen.findByTestId('report-card-audit_summary');
    fireEvent.change(screen.getByLabelText('Dışa aktarma başlangıcı'), { target: { value: '2026-10-01' } });
    fireEvent.click(screen.getByTestId('export-csv-audit_summary'));
    await screen.findByText('Rapor Hazır');
    const call = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(call[1].body).filters).toEqual({ date_from: '2026-10-01', date_to: '2026-10-02' });
    fireEvent.change(screen.getByLabelText('Dışa aktarma bitişi'), { target: { value: '2026-10-03' } });
    await waitFor(() => expect(screen.queryByText('Rapor Hazır')).not.toBeInTheDocument());
  });

  it('renders no-show values separately instead of inventing one TL loss', async () => {
    axios.get.mockResolvedValue({ data: { channels: [], top3_worst: [], total_loss: null, loss_by_currency: { EUR: 100, TRY: 100 }, total_no_shows: 2 } });
    render(<NoShowAnalytics embedded />);
    const summary = await screen.findByTestId('ch-total-loss');
    expect(summary.textContent).toContain('€');
    expect(summary.textContent).toContain('₺');
    expect(summary.textContent).not.toContain('200');
    expect(screen.getByText(/gerçekleşmiş zarar veya tahsilat değildir/)).toBeInTheDocument();
  });

  it('keeps weekly collection and payment plan currencies in the cash flow dialog', async () => {
    render(<CashFlowModal cashFlowModalOpen setCashFlowModalOpen={() => {}} formatCurrency={(value, code) => `${code || 'TRY'}:${value}`} cashFlowData={{
      today: { date: '2026-10-02', inflow_by_currency: { TRY: 100, EUR: 20 }, net_by_currency: { TRY: 100, EUR: 15 } },
      weekly_plan: [{ date: '2026-10-03', day_name: 'Cumartesi', collections_by_currency: { EUR: 20 }, payments_by_currency: { USD: 40 } }],
    }} />);
    expect(await screen.findByText('EUR:20')).toBeInTheDocument();
    expect(screen.getByText('USD:40')).toBeInTheDocument();
  });

  it('does not invent shift balances, check-ins or a mixed-currency average', async () => {
    render(<CashierShiftModal cashierShiftModalOpen setCashierShiftModalOpen={() => {}} formatCurrency={(value, code) => `${code || 'TRY'}:${value}`} shiftReportData={{
      shift_date: '2026-10-02', opening_balance: null, expected_closing_balance: null, variance: null, total_paid_out: null,
      transaction_count: 2, average_transaction: null, average_by_currency: { EUR: 20, TRY: 100 }, totals_by_currency: { EUR: 20, TRY: 100 },
    }} />);
    expect((await screen.findAllByText('Doğrulanmadı')).length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByText('TRY:0')).not.toBeInTheDocument();
    expect(screen.getAllByText('EUR:20 · TRY:100').length).toBe(2);
  });
});
