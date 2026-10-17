import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import PerformanceReport, { csvCell, reportPeriodError, toCsv } from '@/components/statements/PerformanceReport';

const section = (extra = {}) => ({
  performance: { bookings: 2, cancelled: 1, room_nights: 4, gross: 16000, commission: 2400, net_to_hotel: 13600, cancel_rate: 0.3333 },
  receivables: { agency_owes_hotel: 500, hotel_owes_agency: 1200, awaiting_agreement: 500, open_statements: 2,
    aging: { not_due: 0, overdue_1_30: 0, overdue_31_60: 1200, overdue_61_90: 0, overdue_90_plus: 0 },
    pending_notices: { agency_to_hotel: 0, hotel_to_agency: 1200, count: 1 } },
  unbilled: { bookings: 2, agency_owes_hotel: 10800, hotel_owes_agency: 0 },
  forward: { 30: { bookings: 1, room_nights: 2, gross: 8000 }, 60: { bookings: 1, room_nights: 2, gross: 8000 }, 90: { bookings: 2, room_nights: 5, gross: 16000 } },
  pickup_7d: { bookings: 1, gross: 8000, cancelled: 1 },
  ...extra,
});

const chooseView = label => fireEvent.mouseDown(screen.getByRole('tab', { name: label }), { button: 0, ctrlKey: false });
const reportOf = (extra = {}) => ({
  period_start: '2026-10-01', period_end: '2026-10-31', as_of: '2026-10-17',
  rows: [{ party_id: 'a1', party_name: 'Acente Bir', currency: 'TRY', ...section() }],
  totals: [{ currency: 'TRY', ...section() }], ...extra,
});

describe('PerformanceReport', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('shows each agency per currency with overdue and unbilled amounts, totals never mixed', async () => {
    const report = {
      period_start: '2026-12-01', period_end: '2026-12-31', as_of: '2026-12-15',
      rows: [{ party_id: 'a1', party_name: 'Acente Bir', currency: 'TRY', ...section() },
        { party_id: 'a2', party_name: 'Acente İki', currency: 'EUR', ...section() }],
      totals: [{ currency: 'TRY', ...section() }, { currency: 'EUR', ...section() }],
    };
    const api = { get: vi.fn(() => Promise.resolve({ data: report })) };
    render(<PerformanceReport side="hotel" api={api} path="/marketplace/hotel/reports/agency-performance" />);
    const row = await screen.findByTestId('performance-row-a1-TRY');
    expect(within(row).getByText('Acente Bir')).toBeTruthy();
    const tableRegion = screen.getByRole('region', { name: 'Satış performansı tablosu' });
    expect(within(tableRegion).getAllByRole('columnheader')).toHaveLength(7);
    for (const cell of within(row).getAllByRole('cell')) expect(cell).toHaveClass('px-4');
    expect(tableRegion).toHaveClass('overflow-x-auto');
    expect(within(row).getByText('4').closest('td')).not.toBe(within(row).getByText('16.000,00 TRY').closest('td'));
    expect(within(row).getByText('2.400,00 TRY')).toBeTruthy();
    expect(within(row).getByText('13.600,00 TRY')).toBeTruthy();
    expect(screen.getByTestId('performance-totals-TRY')).toBeTruthy();
    expect(screen.getByTestId('performance-totals-EUR')).toBeTruthy();
    const overdue = within(screen.getByTestId('performance-totals-EUR')).getByText('Vadesi geçen').parentElement;
    expect(overdue.textContent).toContain('1.200,00 EUR');
    chooseView('Alacak ve takip');
    expect(within(row).getByText('10.800,00 TRY')).toBeTruthy();
    expect(within(row).getByText('2 rezervasyon')).toBeTruthy();
    chooseView('Gelecek satışlar');
    expect(within(row).getByText('+1 rezervasyon')).toBeTruthy();
    expect(within(row).getByText('−1 rezervasyon')).toBeTruthy();
    expect(api.get).toHaveBeenCalledWith('/marketplace/hotel/reports/agency-performance', expect.objectContaining({ params: expect.any(Object) }));
  });

  it('does not call an unexpected response an empty financial report', async () => {
    const api = { get: vi.fn(() => Promise.resolve({ data: { detail: 'x' } })) };
    render(<PerformanceReport side="agency" api={api} path="/r" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Rapor yüklenemedi.');
    expect(screen.queryByText('Seçilen dönemde satış veya açık alacak kaydı yok.')).toBeNull();
  });
});

describe('PerformanceReport safety', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('neutralises formulas in CSV text cells but keeps negative numbers', () => {
    expect(csvCell('=1+1')).toBe(`"'=1+1"`);
    expect(csvCell('@SUM(A1)')).toBe(`"'@SUM(A1)"`);
    expect(csvCell(-1200)).toBe('"-1200"');
    const csv = toCsv({ rows: [{ party_id: 'a1', party_name: '=HYPERLINK("x")', currency: 'TRY', ...section() }] }, 'Acente');
    expect(csv).toContain(`"'=HYPERLINK(""x"")"`);
  });

  it('keeps the latest period when an older answer arrives late', async () => {
    let resolveOld;
    const api = { get: vi.fn((_path, { params }) => (params.period_start === '2026-08-01'
      ? Promise.resolve({ data: { rows: [{ party_id: 'aug', party_name: 'Ağustos', currency: 'TRY', ...section() }], totals: [] } })
      : new Promise(resolve => { resolveOld = () => resolve({ data: { rows: [{ party_id: 'sep', party_name: 'Eylül', currency: 'TRY', ...section() }], totals: [] } }); }))) };
    const { fireEvent } = await import('@testing-library/react');
    render(<PerformanceReport side="hotel" api={api} path="/r" />);
    fireEvent.change(screen.getByLabelText('Giriş tarihi başlangıç'), { target: { value: '2026-08-01' } });
    expect(await screen.findByText('Ağustos')).toBeTruthy();
    resolveOld();  // the first (older) request answers last
    await new Promise(r => setTimeout(r, 0));
    expect(screen.queryByText('Eylül')).toBeNull();
    expect(screen.getByText('Ağustos')).toBeTruthy();
  });
});

describe('PerformanceReport readability and financial context', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('keeps opposing unbilled amounts and payment notices separate, not netted or added', async () => {
    const data = reportOf();
    data.rows[0].unbilled = { bookings: 2, agency_owes_hotel: 8000, hotel_owes_agency: 8000 };
    data.rows[0].receivables.pending_notices = { count: 2, agency_to_hotel: 1500, hotel_to_agency: 2500 };
    render(<PerformanceReport side="agency" api={{ get: vi.fn().mockResolvedValue({ data }) }} path="/r" />);
    await screen.findByTestId('performance-row-a1-TRY');
    chooseView('Alacak ve takip');
    const row = screen.getByTestId('performance-row-a1-TRY');
    const cells = within(row).getAllByRole('cell');
    expect(within(cells[4]).getAllByText('8.000,00 TRY')).toHaveLength(2);
    expect(cells[4]).toHaveTextContent('Acente → otel');
    expect(cells[4]).toHaveTextContent('Otel → acente');
    expect(cells[5]).toHaveTextContent('1.500,00 TRY');
    expect(cells[5]).toHaveTextContent('2.500,00 TRY');
    expect(cells[5]).not.toHaveTextContent('4.000,00');
  });

  it('preserves large USD and EUR values and marks an unknown currency without calling it TRY', async () => {
    const data = reportOf({ rows: ['USD', 'EUR', 'UNKNOWN'].map(currency => ({
      party_id: currency, party_name: currency + ' hotel', currency,
      ...section({ performance: { bookings: 2, room_nights: 4, gross: 12345678.91, commission: 1851851.84, net_to_hotel: 10493827.07 } }),
    })), totals: [] });
    render(<PerformanceReport side="agency" api={{ get: vi.fn().mockResolvedValue({ data }) }} path="/r" />);
    const row = await screen.findByTestId('performance-row-USD-USD');
    expect(row).toHaveTextContent('12.345.678,91 USD');
    expect(row).toHaveTextContent('10.493.827,07 USD');
    expect(row).not.toHaveTextContent('TRY');
    expect(screen.getByTestId('performance-row-EUR-EUR')).toHaveTextContent('12.345.678,91 EUR');
    expect(screen.getByTestId('performance-row-UNKNOWN-UNKNOWN')).toHaveTextContent('para birimi eksik');
  });

  it('removes old amounts while a different period is loading or fails', async () => {
    const get = vi.fn().mockResolvedValueOnce({ data: reportOf() }).mockRejectedValueOnce({ response: { data: { detail: 'Bağlantı kesildi' } } });
    render(<PerformanceReport side="agency" api={{ get }} path="/r" />);
    await screen.findByTestId('performance-row-a1-TRY');
    fireEvent.change(screen.getByLabelText('Giriş tarihi başlangıç'), { target: { value: '2026-08-01' } });
    expect(screen.queryByTestId('performance-row-a1-TRY')).toBeNull();
    expect(await screen.findByRole('alert')).toHaveTextContent('Bağlantı kesildi');
    expect(screen.queryByRole('button', { name: 'CSV indir' })).toBeNull();
  });

  it('rejects an inverted period without requesting or retaining old amounts', async () => {
    const get = vi.fn().mockResolvedValue({ data: reportOf() });
    render(<PerformanceReport side="agency" api={{ get }} path="/r" />);
    await screen.findByTestId('performance-row-a1-TRY');
    fireEvent.change(screen.getByLabelText('Bitiş'), { target: { value: '2000-01-01' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Dönem bitişi başlangıçtan önce olamaz.');
    expect(get).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('performance-row-a1-TRY')).toBeNull();
  });

  it.each([
    [{ start: '', end: '2026-10-17' }, 'Geçerli'],
    [{ start: '2026-02-30', end: '2026-03-01' }, 'Geçerli'],
    [{ start: '2025-01-01', end: '2026-10-17' }, 'en fazla bir yıl'],
    [{ start: '2026-10-01', end: '2026-10-31' }, ''],
  ])('validates the check-in period %o', (period, expected) => {
    expect(reportPeriodError(period)).toContain(expected);
  });

  it('exports every view with original numeric amounts and releases the download URL', async () => {
    const create = vi.fn().mockReturnValue('blob:review');
    const revoke = vi.fn();
    class DownloadURL extends URL {}
    DownloadURL.createObjectURL = create;
    DownloadURL.revokeObjectURL = revoke;
    vi.stubGlobal('URL', DownloadURL);
    vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const data = reportOf();
    render(<PerformanceReport side="agency" api={{ get: vi.fn().mockResolvedValue({ data }) }} path="/r" />);
    fireEvent.click(await screen.findByRole('button', { name: 'CSV indir' }));
    expect(create).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:review'));
    const csv = toCsv(data, 'Otel');
    expect(csv.split('\n')[0].split(';')).toHaveLength(27);
    expect(csv.split('\n')[1].split(';')).toHaveLength(27);
    expect(csv).toContain('"16000";"2400";"13600"');
    vi.unstubAllGlobals();
  });
});
