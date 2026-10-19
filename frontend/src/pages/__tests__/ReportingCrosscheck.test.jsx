import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import CostAnalyticsView from '@/components/cost/CostAnalyticsView';
import AnalyticsExportDashboard from '../AnalyticsExportDashboard';
import NoShowAnalytics from '../NoShowAnalytics';
import CashFlowModal from '@/components/mobile-finance/dialogs/CashFlowModal';
import CashierShiftModal from '@/components/mobile-finance/dialogs/CashierShiftModal';
import ReportsModal from '@/components/mobile-finance/dialogs/ReportsModal';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
const { translate } = vi.hoisted(() => ({ translate: (key, options) => options?.defaultValue || key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-02' }));
vi.mock('@/components/MaybeLayout', () => ({ default: ({ children }) => <>{children}</> }));
vi.mock('@/components/ui/select', () => ({
  Select: ({ value, onValueChange, children }) => <select aria-label="Rapor dönemi" value={value} onChange={e => onValueChange(e.target.value)}>{children}</select>,
  SelectContent: ({ children }) => <>{children}</>, SelectItem: ({ value, children }) => <option value={value}>{children}</option>,
  SelectTrigger: () => null, SelectValue: () => null,
}));
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

  it('closes the report without pretending to close a cashier shift', async () => {
    const close = vi.fn();
    render(<CashierShiftModal cashierShiftModalOpen setCashierShiftModalOpen={close} formatCurrency={value => String(value)} shiftReportData={{ transaction_count: 0 }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Raporu kapat' }));
    expect(close).toHaveBeenCalledWith(false);
  });

  it('keeps absent monthly metrics unknown and formats the daily average in its reporting currency', () => {
    render(<ReportsModal reportsModalOpen setReportsModalOpen={() => {}} formatCurrency={(value, currency) => `${currency || 'EUR'}:${value}`} formatPercent={value => `${value}%`}
      dailyCollections={{ total_collected: 100, average_transaction: 50, payment_count: 2, reporting_currency: 'TRY' }}
      monthlyCollections={{ total_collected: 100, reporting_currency: 'TRY' }} monthlyCosts={{ total_costs: 40, currency: 'TRY' }} />);
    expect(screen.getByText('TRY:50')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.queryByText('EUR:0')).not.toBeInTheDocument();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it.each([false, true])('does not let an outdated no-show response overwrite the selected period (old error: %s)', async (oldError) => {
    let resolveOld, rejectOld;
    const old = new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; });
    const data = amount => ({ channels: [], top3_worst: [], total_loss: amount, loss_by_currency: { TRY: amount }, total_no_shows: 1 });
    axios.get.mockImplementation(url => url.endsWith('days=30') ? old : Promise.resolve({ data: data(90) }));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<NoShowAnalytics embedded />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/pms/channel-loss-analytics?days=30'));
    fireEvent.change(screen.getByLabelText('Rapor dönemi'), { target: { value: '90' } });
    expect(await screen.findByTestId('ch-total-loss')).toHaveTextContent('90,00');
    await act(async () => { if (oldError) rejectOld(new Error('old failure')); else resolveOld({ data: data(30) }); });
    expect(screen.getByTestId('ch-total-loss')).toHaveTextContent('90,00');
  });

  it('does not turn an invalid successful no-show response into a zero dashboard', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockResolvedValue({ data: { detail: 'broken payload' } });
    render(<NoShowAnalytics embedded />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Kanal kaybı verileri yüklenemedi');
    expect(screen.queryByTestId('ch-total-loss')).not.toBeInTheDocument();
  });

  it('marks omitted reference amounts and does not call sample size calibrated reliability', async () => {
    axios.get.mockResolvedValue({ data: { channels: [], top3_worst: [], total_loss: null, loss_by_currency: {}, total_no_shows: 1,
      start_date: '2026-09-03', end_date: '2026-10-02', data_quality: { invalid_amounts: 1, confidence: 'high', note: 'sample only' } } });
    render(<NoShowAnalytics embedded />);
    expect(await screen.findByRole('alert')).toHaveTextContent('1 rezervasyonun tutarı');
    expect(screen.getByTestId('ch-total-loss')).toHaveTextContent('—');
    expect(screen.getByTestId('data-quality-banner')).toHaveTextContent('Veri kapsamı');
    expect(screen.getByText(/2026-09-03 – 2026-10-02/)).toBeInTheDocument();
  });

  it.each([7, 90, 365])('shows every selected heatmap day, not only the last sixty (%i)', async days => {
    const heatmap = Array.from({ length: days }, (_, i) => ({ date: `day-${i}`, overbooking_count: 0, total_noshow: 0 }));
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('overbooking-heatmap')
      ? { heatmap, total_overbookings: 0, peak_days: [], weekly_pattern: [], channel_overlay: [], total_loss: 0, loss_by_currency: { EUR: 0 } }
      : { channels: [], top3_worst: [], total_no_shows: 0 } }));
    render(<NoShowAnalytics embedded />);
    fireEvent.change(screen.getByLabelText('Rapor dönemi'), { target: { value: String(days) } });
    fireEvent.click(screen.getByTestId('tab-heatmap'));
    await screen.findByTestId('heatmap-tab');
    expect(screen.getAllByTestId(/^heat-cell-/)).toHaveLength(days);
    expect(screen.getByText(/yalnız fazla satış olarak işaretlenen/)).toBeInTheDocument();
  });

  it('preserves a nested channel named date and gives trend bars a real height', async () => {
    axios.get.mockResolvedValue({ data: { channels: [], top3_worst: [], total_loss: 100, total_no_shows: 1,
      trend_channels: ['date'], trend: [{ date: '2026-10-02', counts_by_channel: { date: 1 } }] } });
    render(<NoShowAnalytics embedded />);
    const bar = await screen.findByTestId('trend-bar-0');
    expect(bar).toHaveClass('h-full');
    expect(bar).toHaveTextContent('2026-10-02: 1');
    expect(bar.querySelector('[style]')).toHaveStyle({ height: '100%' });
  });

  it('rejects invalid heatmap payloads with a retry action', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockResolvedValue({ data: {} });
    render(<NoShowAnalytics embedded />);
    fireEvent.click(screen.getByTestId('tab-heatmap'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Fazla satış risk haritası yüklenemedi');
    expect(screen.getByRole('button', { name: 'Yeniden dene' })).toBeInTheDocument();
  });

  it('uses the same risk model for summary, row badge, order, score and bar even for zero scores', async () => {
    axios.get.mockResolvedValue({ data: { predictions: [
      { booking_id: 'high', guest_name: 'High guest', risk_score: 80, risk_level: 'high', total_amount: 100, currency: 'EUR' },
      { booking_id: 'zero', guest_name: 'Zero guest', risk_score: 0, risk_level: 'low', total_amount: null, currency: 'USD' },
    ], summary: { high_risk: 1, medium_risk: 0, low_risk: 1, potential_loss_by_currency: { EUR: 100 } } } });
    axios.post.mockResolvedValue({ data: { results: { high: { score: 0, level: 'low' }, zero: { score: 90, level: 'high' } } } });
    render(<NoShowAnalytics embedded />);
    fireEvent.click(screen.getByTestId('tab-prediction'));
    const row = await screen.findByTestId('pred-row-0');
    expect(row).toHaveTextContent('High guest');
    expect(row).toHaveTextContent('YÜKSEK');
    expect(row.querySelector('[style]')).toHaveStyle({ width: '80%' });
    expect(screen.getByTestId('pred-row-1')).toHaveTextContent('DÜŞÜK');
    expect(screen.getByTestId('pred-row-1').querySelector('[style]')).toHaveStyle({ width: '0%' });
    expect(screen.getByTestId('pred-high-risk')).toHaveTextContent('1');
    expect(screen.getByTestId('pred-potential-loss')).toHaveTextContent('Risk altındaki rezervasyon bedeli');
    expect(screen.getByRole('region', { name: 'Rezervasyon risk tablosu' })).toHaveAttribute('tabIndex', '0');
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('shows a retry error rather than zero risk for a malformed prediction response', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockResolvedValue({ data: { detail: 'broken prediction' } });
    render(<NoShowAnalytics embedded />);
    fireEvent.click(screen.getByTestId('tab-prediction'));
    expect(await screen.findByRole('alert')).toHaveTextContent('No-show tahminleri yüklenemedi');
    expect(screen.queryByTestId('pred-low-risk')).not.toBeInTheDocument();
  });
});
