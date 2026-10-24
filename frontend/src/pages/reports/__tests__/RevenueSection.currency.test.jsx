import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import RevenueSection from '../RevenueSection';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('recharts', () => {
  const Container = ({ children, data }) => <div data-series={data ? JSON.stringify(data) : undefined}>{children}</div>;
  const Empty = () => null;
  return { AreaChart: Container, BarChart: Container, ResponsiveContainer: Container, Area: ({ name }) => <span>{name}</span>, Bar: Empty, CartesianGrid: Empty, Tooltip: Empty, XAxis: Empty, YAxis: Empty };
});
const values = total => ({ total, net: null, vat: null, city_tax: null, other_tax: null, subtotal: null, discount: 0, difference: 0, count: 1 });
function payload(first = '2026-10-01', last = first, total = 1000) {
  return { date_from: first, date_to: last, snapshot: `snapshot-${total}`,
    rows: [{ category: 'room', label: 'Konaklama', count: 1, by_currency: { TRY: values(total) } }, { category: 'beverage', label: 'İçecek', count: 1, by_currency: { EUR: values(200) } }],
    totals: { count: 2 }, totals_by_currency: { TRY: values(total), EUR: values(200) },
    departments_by_currency: { room: { TRY: total }, fnb: { EUR: 200 } },
    revenue_trend: [{ date: first, revenue_by_currency: { TRY: total, EUR: 200 } }],
    room_type_revenue: [{ name: 'Standart', revenue_by_currency: { TRY: total, EUR: 100 } }],
    reconciliation: { tax_unknown_count: 2, issue_count: 0, issues: [] } };
}
const renderReport = () => render(<RevenueSection reportPeriod="daily" reportDate="2026-10-01" />);
beforeEach(() => {
  vi.resetAllMocks();
  axios.get.mockImplementation(async (_url, { params }) => ({ data: payload(params.date_from, params.date_to) }));
  window.print = vi.fn();
});
describe('one-snapshot revenue report', () => {
  it('keeps currencies separate in cards/table and never fabricates net from missing taxes', async () => {
    renderReport();
    const table = await screen.findByRole('table', { name: 'Kategori bazlı gelir' });
    expect(within(table).getAllByText(text => text.replace(/\s/g, '') === '₺1.000,00')).toHaveLength(2);
    expect(within(table).getAllByText(text => text.replace(/\s/g, '') === '€200,00')).toHaveLength(2);
    expect(within(table).queryByText('₺1.200,00')).not.toBeInTheDocument();
    expect(within(table).getAllByText(/Doğrulanamadı \((TRY|EUR)\)/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2 işlemin vergi kırılımı eksik/)).toBeInTheDocument();
    expect(screen.queryByText('Trend')).not.toBeInTheDocument();
  });
  it('selects one native chart currency without adding unlike amounts', async () => {
    renderReport(); await screen.findByRole('table');
    fireEvent.change(screen.getByLabelText('Gelir grafik para birimi'), { target: { value: 'EUR' } });
    expect(screen.getByText('Günlük işlenen tutar · EUR')).toBeInTheDocument();
    const series = [...document.querySelectorAll('[data-series]')].map(node => JSON.parse(node.dataset.series));
    expect(series[0][0].value).toBe(200);
    expect(series[1][0].value).toBe(100);
  });
  it('ignores stale responses/errors for the entire report, not just its category table', async () => {
    let finishOld;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    renderReport();
    fireEvent.change(screen.getByLabelText('Gelir bitiş tarihi'), { target: { value: '2026-10-02' } });
    await screen.findByRole('table');
    await act(async () => finishOld({ data: payload('2026-10-01', '2026-10-01', 999) }));
    expect(screen.queryByText('₺999,00')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Gelir bitiş tarihi')).toHaveValue('2026-10-02');
  });
  it('rejects empty/reversed/oversized ranges and hides all previous results', async () => {
    renderReport(); await screen.findByRole('table');
    fireEvent.change(screen.getByLabelText('Gelir başlangıç tarihi'), { target: { value: '2026-10-02' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli bir tarih aralığı');
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Gelir başlangıç tarihi'), { target: { value: '' } });
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
  it('rejects mismatched response dates instead of displaying a valid-looking stale report', async () => {
    axios.get.mockResolvedValueOnce({ data: payload('2025-01-01') });
    renderReport(); expect(await screen.findByRole('alert')).toHaveTextContent('eşleşmiyor');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
  it('shows errors as unavailable, never as a zero or empty report', async () => {
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'Kaynak defter alınamadı' } } });
    renderReport(); expect(await screen.findByRole('alert')).toHaveTextContent('Kaynak defter alınamadı');
    expect(screen.getByText('Veri alınamadı.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel indir' })).toBeDisabled();
  });
  it('exports the selected snapshot and invalidates the screen when the ledger changed', async () => {
    renderReport(); await screen.findByRole('table');
    axios.get.mockRejectedValueOnce({ response: { status: 409 } });
    fireEvent.click(screen.getByRole('button', { name: 'Excel indir' }));
    await screen.findByText(/Gelir verisi değişti/);
    expect(axios.get).toHaveBeenLastCalledWith('/folio/reports/revenue-by-category/excel', { params: { date_from: '2026-10-01', date_to: '2026-10-01', snapshot: 'snapshot-1000' }, responseType: 'blob' });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
  it('shows tax details and source discrepancies without hiding a one-lira difference', async () => {
    const data = payload();
    data.rows[0].by_currency.TRY.difference = -1;
    data.reconciliation.issue_count = 1;
    data.reconciliation.issues = [{ id: 'c1', source: 'folio', date: '2026-10-01', difference: -1, currency: 'TRY', reasons: ['Net + vergi ile toplam uyuşmuyor'] }];
    axios.get.mockResolvedValueOnce({ data }); renderReport();
    await screen.findByRole('table');
    fireEvent.click(screen.getByLabelText('Vergi / indirim ayrıntıları'));
    expect(screen.getByRole('columnheader', { name: 'Açıklanamayan fark' })).toBeInTheDocument();
    expect(screen.getByText(/1 kaynak harekette hesap uyuşmazlığı/)).toBeInTheDocument();
    expect(screen.getByText(/folio \/ c1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Yazdır / PDF' })); expect(window.print).toHaveBeenCalledOnce();
  });
});
