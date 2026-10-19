import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import BasicReports, { REPORT_MENU } from '../BasicReports';
import { REPORT_CONTRACTS } from '@/lib/reportContracts';

const { fetchJson, get } = vi.hoisted(() => ({ fetchJson: vi.fn(), get: vi.fn() }));
vi.mock('@/lib/fetchRetry', () => ({ fetchJsonWithRetry: fetchJson }));
vi.mock('@/api/axios', () => ({ default: { get } }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-07' }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => typeof fallback === 'string' ? fallback : key }) }));
vi.mock('@/components/pms/FlashReportContent', () => ({ default: ({ targetDate }) => <div data-testid="flash-content">{targetDate}</div> }));
vi.mock('@/components/cost/CostAnalyticsView', () => ({ default: () => <div data-testid="expense-content">Giderler</div> }));
vi.mock('recharts', () => {
  const Container = ({ children }) => <div>{children}</div>;
  const Empty = () => null;
  return { AreaChart: Container, BarChart: Container, ComposedChart: Container, LineChart: Container, PieChart: Container,
    ResponsiveContainer: Container, Pie: Container, Area: Empty, Bar: Empty, Line: Empty, Cell: Empty,
    XAxis: Empty, YAxis: Empty, Tooltip: Empty, Legend: Empty, CartesianGrid: Empty };
});

const daily = { currency: 'EUR', occupancy: {}, movements: {}, revenue: { by_category: {} }, payments: { by_method: {} }, ledger: {}, balance_check: {} };
const payload = day => ({ date: day, summary: {}, period_metrics: {}, period_comparison: {}, guest_list: [], payments: {}, daily_lists: {}, housekeeping: {}, maintenance: {}, finance: {} });
const official = (day, name) => ({ date: day, rows: name ? [{ id: name, booking_id: name, guest_name: name, check_in: day, check_out: '2026-10-09', adults: 1, total_amount: 100, currency: 'EUR' }] : [], privacy: {} });
const open = (section = 'overview') => render(<MemoryRouter initialEntries={[`/?section=${section}`]}><BasicReports tenant={{ name: 'Test Hotel' }} user={{ name: 'Operator' }} /></MemoryRouter>);

beforeEach(() => {
  fetchJson.mockReset().mockImplementation(async url => url.includes('basic-dashboard') ? payload(new URL(url, 'https://example.test').searchParams.get('date')) : { rates: {} });
  get.mockReset().mockImplementation(async url => ({ data: url === '/trial-balance' ? daily : { rows: [], totals: {}, revenue: [], expenses: [], assets: [], liabilities: [], equity: [], entries: [], daily: [] } }));
});

describe('Complete active report workspace', () => {
  it('renders the unassigned revenue bucket with a human-readable name and no invented bookings', async () => {
    fetchJson.mockResolvedValue({ ...payload('2026-10-07'), booking_sources: {
      distribution: { unassigned: 0 }, revenue: { unassigned: 30 }, revenue_by_currency: { unassigned: { EUR: 30 } },
    } });
    open('channels');
    const table = await screen.findByTestId('channel-table');
    expect(table).toHaveTextContent('Rezervasyonla eşleştirilmemiş');
    expect(table).toHaveTextContent('€30');
    expect(table).not.toHaveTextContent('unassigned');
  });

  it.each(REPORT_MENU.filter(item => item.id).map(item => item.id))('renders %s once with an explicit source contract', async section => {
    open(section);
    await waitFor(() => expect(screen.queryByTestId('product-state')).not.toBeInTheDocument());
    expect(screen.getAllByTestId('report-active-content')).toHaveLength(1);
    expect(screen.getByTestId('report-active-content')).toHaveAttribute('data-report-section', section);
    expect(document.querySelectorAll('.report-document')).toHaveLength(1);
    expect(document.querySelector('[data-testid="reports-mobile-content"]')).toBeNull();
    expect(REPORT_CONTRACTS[section]).toBeDefined();
    await waitFor(() => expect(get.mock.calls.filter(([url]) => url === '/trial-balance').length).toBeLessThanOrEqual(1));
  });

  it('mounts self-contained financial readers once, not once for each viewport', async () => {
    open('trial_balance');
    await waitFor(() => expect(get).toHaveBeenCalledWith('/trial-balance', { params: { date: '2026-10-07' } }));
    expect(get.mock.calls.filter(([url]) => url === '/trial-balance')).toHaveLength(1);
    expect(screen.getAllByTestId('operational-reconciliation-report')).toHaveLength(1);
  });

  it('does not require the unrelated heavy dashboard to show the self-contained flash report', async () => {
    fetchJson.mockRejectedValue(new Error('Dashboard unavailable'));
    open('flash_report');
    expect(await screen.findByTestId('flash-content')).toHaveTextContent('2026-10-07');
    expect(fetchJson).not.toHaveBeenCalled();
  });

  it('keeps the daily reconciliation picker synchronized with the printable report date', async () => {
    open('trial_balance');
    await screen.findByTestId('input-tb-date');
    fireEvent.change(screen.getByTestId('input-tb-date'), { target: { value: '2026-10-08' } });
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/trial-balance', { params: { date: '2026-10-08' } }));
    expect(document.querySelector('.report-print-header')).toHaveTextContent('08 Ekim 2026');
  });

  it('keeps GL contents, disclosure and print header on the edited date after dashboard navigation', async () => {
    open();
    await screen.findByTestId('section-overview');
    fireEvent.click(screen.getByTestId('report-nav-gl_trial_balance'));
    await waitFor(() => expect(get).toHaveBeenCalledWith('/gl/trial-balance', { params: { as_of: '2026-10-07' } }));
    fireEvent.change(screen.getByTestId('report-date-input'), { target: { value: '2026-10-08' } });
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/gl/trial-balance', { params: { as_of: '2026-10-08' } }));
    expect(screen.getByTestId('report-data-contract')).toHaveTextContent('08 Ekim 2026');
    expect(document.querySelector('.report-print-header')).toHaveTextContent('08 Ekim 2026');
    expect(document.querySelector('.report-print-header')).toHaveTextContent('Tarih itibarıyla');
  });

  it('rejects cleared dates before requesting a fallback dashboard and keeps navigation available', async () => {
    open();
    await screen.findByTestId('section-overview');
    fireEvent.change(screen.getByTestId('report-date-input'), { target: { value: '' } });
    await screen.findByText('Geçerli bir rapor tarihi seçin.');
    expect(fetchJson.mock.calls.filter(([url]) => url.includes('basic-dashboard'))).toHaveLength(1);
    expect(screen.queryByTestId('section-overview')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-nav-official')).toBeInTheDocument();
  });

  it('clears a failed refresh instead of keeping stale data exportable', async () => {
    open('guests');
    await waitFor(() => expect(screen.getByTestId('report-csv')).toBeEnabled());
    fetchJson.mockRejectedValueOnce(new Error('Defter bağlantısı kesildi'));
    fireEvent.click(screen.getByTestId('refresh-reports-btn'));
    await screen.findByText('Defter bağlantısı kesildi');
    expect(screen.getByTestId('report-csv')).toBeDisabled();
    expect(screen.getByTestId('mobile-report-csv')).toBeDisabled();
  });

  it('refuses a response from a different dashboard date', async () => {
    fetchJson.mockResolvedValue(payload('2026-10-06'));
    open('guests');
    expect(await screen.findByRole('alert')).toHaveTextContent('Rapor yanıtının tarihi seçili tarihle eşleşmiyor');
    expect(screen.getByTestId('report-csv')).toBeDisabled();
  });

  it('refuses an official response from a different date', async () => {
    fetchJson.mockResolvedValue(official('2026-10-06', 'Yanlış tarih misafiri'));
    open('official');
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Resmi liste yanıtının tarihi seçili tarihle eşleşmiyor');
    expect(screen.queryByText('Yanlış tarih misafiri')).not.toBeInTheDocument();
    expect(screen.getByTestId('official-csv-btn')).toBeDisabled();
  });

  it('does not export old official rows under a newly selected date', async () => {
    fetchJson.mockResolvedValue(official('2026-10-07', 'Eski misafir'));
    open('official');
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    await screen.findByText('Eski misafir');
    fireEvent.change(screen.getByTestId('official-date-input'), { target: { value: '2026-10-08' } });
    expect(screen.queryByText('Eski misafir')).not.toBeInTheDocument();
    expect(screen.getByTestId('official-csv-btn')).toBeDisabled();
    expect(screen.getByTestId('official-print-btn')).toBeDisabled();
  });

  it.each([false, true])('ignores an old official request after the selection changes (failure %s)', async fails => {
    let finishOld, failOld;
    fetchJson.mockImplementationOnce(() => new Promise((resolve, reject) => { finishOld = resolve; failOld = reject; }));
    fetchJson.mockResolvedValueOnce(official('2026-10-08', 'Yeni misafir'));
    open('official');
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    fireEvent.change(screen.getByTestId('official-date-input'), { target: { value: '2026-10-08' } });
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    await screen.findByText('Yeni misafir');
    await act(async () => { if (fails) failOld(new Error('Eski hata')); else finishOld(official('2026-10-07', 'Eski misafir')); });
    expect(screen.getByText('Yeni misafir')).toBeInTheDocument();
    expect(screen.queryByText('Eski misafir')).not.toBeInTheDocument();
    expect(screen.queryByText('Eski hata')).not.toBeInTheDocument();
  });

  it('does not allow official exports after an error or invalid date', async () => {
    fetchJson.mockRejectedValueOnce(new Error('Liste alınamadı'));
    open('official');
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Liste alınamadı');
    expect(screen.getByTestId('official-csv-btn')).toBeDisabled();
    fireEvent.change(screen.getByTestId('official-date-input'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('official-fetch-btn'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli bir rapor tarihi');
    expect(fetchJson).toHaveBeenCalledTimes(1);
  });

  it('exports the single visible guest table on mobile with native currency and one header', async () => {
    fetchJson.mockResolvedValue({ ...payload('2026-10-07'), guest_list: [{ id: 'b', guest_name: 'Test misafiri', room_number: '101', check_in: '2026-10-07', check_out: '2026-10-09', total_amount: 100, currency: 'EUR', status: 'checked_in' }] });
    let file;
    const create = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => { file = blob; return 'blob:test'; });
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    open('guests');
    await screen.findByText('Test misafiri');
    fireEvent.click(screen.getByTestId('mobile-report-csv'));
    const csv = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(file); });
    expect(csv).toContain('Test misafiri');
    expect(csv).toContain('100');
    expect(within(screen.getByTestId('report-active-content')).getAllByRole('table')).toHaveLength(1);
    create.mockRestore(); revoke.mockRestore(); click.mockRestore();
  });
});
