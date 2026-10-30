import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import api from '@/api/axios';
import FrontdeskForecastReport from '../FrontdeskForecastReport';
import ForecastReportsPage from '../../ForecastReportsPage';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-24' }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('recharts', () => {
  const Container = ({ children }) => <div>{children}</div>;
  const Chart = ({ children, onClick }) => <div data-testid="synthetic-chart" onClick={() => onClick?.({ activeTooltipIndex: '0' })}>{children}</div>;
  const Empty = () => null;
  return { ResponsiveContainer: Container, ComposedChart: Chart, LineChart: Chart,
    Bar: ({ dataKey, name, stackId, children }) => <span data-testid={`bar-${dataKey}`} data-stack={stackId}>{name}{children}</span>,
    Line: ({ dataKey, connectNulls, children }) => <span data-testid={`line-${dataKey}`} data-connect-nulls={String(connectNulls)}>{children}</span>,
    LabelList: ({ dataKey }) => <span data-testid="chart-label-list" data-key={dataKey} />,
    CartesianGrid: Empty, Legend: Empty, Tooltip: Empty, XAxis: Empty, YAxis: Empty };
});
const col = (key, label, type = 'number') => ({ key, label, type });
function payload(params) {
  const rows = [];
  for (let day = new Date(`${params.start_date}T12:00:00Z`); day <= new Date(`${params.end_date}T12:00:00Z`); day.setUTCDate(day.getUTCDate() + 1)) rows.push({
    date: day.toISOString().slice(0, 10), physical_rooms: 10, available_rooms: 8, booked_rooms: 3, block_rooms: 2,
    total_occupied_rooms: 5, vacant_rooms: 3, remaining_rooms: 3, blocked_rooms: 2, occupancy_pct: 50, sellable_occupancy_pct: 62.5,
    room_revenue_by_currency: { EUR: 300, USD: 100 }, adr_by_currency: { EUR: 150, USD: 100 }, arrivals: 1, departures: 2,
    basis: 'on_the_books', comp_rooms: 0, group_rooms: 1, day_use_rooms: 1, house_use_rooms: 0, overbooked_rooms: 0,
  });
  const revenue = [col('room_revenue_by_currency', 'Rezervasyon oda bedeli', 'money'), col('adr_by_currency', 'Ort. ücretli oda bedeli', 'money')];
  return { start_date: params.start_date, end_date: params.end_date, room_type: params.room_type || null, room_types: ['Standard', 'Suite'],
    business_date: '2026-10-24', snapshot: 'same-financial-snapshot', currency: 'TRY', rows, room_type_groups: [{ label: 'Standard', rows }], warnings: [], definitions: { rooms: 'Kapalı oda ve grup bloğu ayrıdır.' },
    columns: { availability: [col('physical_rooms', 'Oda kapasitesi'), col('total_occupied_rooms', 'Toplam dolu oda'), col('booked_rooms', 'Dolu oda'), col('block_rooms', 'Blok oda'), col('remaining_rooms', 'Net kalan (+/−)'), col('occupancy_pct', 'Doluluk % (fiziksel)', 'percent'), ...revenue],
      movements: [col('arrivals', 'Gelen oda'), col('departures', 'Ayrılan oda')], occupancy: [col('occupancy_pct', 'Doluluk % (fiziksel)', 'percent'), col('sellable_occupancy_pct', 'Doluluk % (satılabilir)', 'percent')],
      revenue, stay_types: [col('comp_rooms', 'Comp oda'), col('day_use_rooms', 'Day-use oda')] },
    totals: { occupied_room_nights: rows.length * 5, booked_room_nights: rows.length * 3, block_room_nights: rows.length * 2,
      physical_room_nights: rows.length * 10, sellable_room_nights: rows.length * 8, occupancy_pct: 50, sellable_occupancy_pct: 62.5,
      room_revenue_by_currency: { EUR: rows.length * 300, USD: rows.length * 100 }, adr_by_currency: { EUR: 150, USD: 100 } } };
}
beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (_url, { params }) => ({ data: payload(params) }));
  window.print = vi.fn();
});
afterEach(cleanup);
const loaded = () => screen.findByTestId('frontdesk-forecast-table');
const refresh = () => fireEvent.click(screen.getByTestId('button-load-frontdesk-forecast'));

it('defaults the forecast page to the operational report, without requesting a statistical prediction', async () => {
  render(<ForecastReportsPage />);
  await loaded();
  expect(screen.getByTestId('tab-operational')).toHaveAttribute('data-state', 'active');
  expect(api.get.mock.calls.every(([url]) => url === '/reports/frontdesk-forecast')).toBe(true);
  expect(screen.getByTestId('tab-forecast')).toHaveTextContent('İstatistiksel Tahmin');
});

it('shows KPIs, disjoint stacked availability, daily details and selected-day highlighting', async () => {
  render(<FrontdeskForecastReport />);
  const table = await loaded();
  expect(screen.getByTestId('forecast-occupancy-total')).toHaveTextContent('%50');
  for (const key of ['booked_rooms', 'block_rooms', 'vacant_rooms', 'blocked_rooms']) expect(screen.getByTestId(`bar-${key}`)).toHaveAttribute('data-stack', 'rooms');
  expect(screen.getAllByTestId('chart-label-list')).toHaveLength(1);
  expect(screen.getByTestId('chart-label-list')).toHaveAttribute('data-key', 'remaining_rooms');
  expect(screen.getByText(/Her günün üzerindeki sayı net kalan odadır/)).toBeInTheDocument();
  expect(table).toHaveTextContent('Net kalan (+/−)');
  expect(table).toHaveTextContent('+3');
  fireEvent.click(screen.getByTestId('synthetic-chart'));
  expect(within(table).getAllByRole('row')[1]).toHaveAttribute('aria-selected', 'true');
  fireEvent.click(screen.getByRole('button', { name: '2026-10-24 gününü vurgula' }));
  expect(within(table).getAllByRole('row')[1]).toHaveAttribute('aria-selected', 'false');
});

it('hides old results until an explicitly refreshed date/type scope matches and ignores the old response', async () => {
  let finishOld;
  api.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
  render(<FrontdeskForecastReport />);
  fireEvent.change(screen.getByLabelText('Forecast bitiş'), { target: { value: '2026-10-26' } });
  refresh();
  await loaded();
  expect(within(screen.getByTestId('frontdesk-forecast-table')).getAllByRole('row')).toHaveLength(4);
  await act(async () => finishOld({ data: payload({ start_date: '2026-10-24', end_date: '2026-11-22' }) }));
  expect(within(screen.getByTestId('frontdesk-forecast-table')).getAllByRole('row')).toHaveLength(4);
  fireEvent.change(screen.getByLabelText('Forecast oda tipi'), { target: { value: 'Suite' } });
  expect(screen.queryByTestId('frontdesk-forecast-table')).not.toBeInTheDocument();
  refresh(); await loaded();
  expect(api.get).toHaveBeenLastCalledWith('/reports/frontdesk-forecast', { params: { start_date: '2026-10-24', end_date: '2026-10-26', room_type: 'Suite' } });
});

it('supports week/month/year and adjacent ranges with inclusive dates', async () => {
  render(<FrontdeskForecastReport />); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'Bu hafta', exact: true })); await loaded();
  expect(screen.getByLabelText('Forecast başlangıç')).toHaveValue('2026-10-19');
  expect(screen.getByLabelText('Forecast bitiş')).toHaveValue('2026-10-25');
  fireEvent.click(screen.getByRole('button', { name: 'Sonraki dönem' })); await loaded();
  expect(screen.getByLabelText('Forecast başlangıç')).toHaveValue('2026-10-26');
  expect(screen.getByLabelText('Forecast bitiş')).toHaveValue('2026-11-01');
  fireEvent.click(screen.getByRole('button', { name: 'Bu ay', exact: true })); await loaded();
  expect(screen.getByLabelText('Forecast bitiş')).toHaveValue('2026-10-31');
  fireEvent.click(screen.getByRole('button', { name: 'Bu yıl', exact: true })); await loaded();
  expect(screen.getByLabelText('Forecast başlangıç')).toHaveValue('2026-01-01');
  expect(screen.getByLabelText('Forecast bitiş')).toHaveValue('2026-12-31');
});

it('rejects inverted or oversized ranges without a new request', async () => {
  render(<FrontdeskForecastReport />); await loaded();
  const count = api.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Forecast bitiş'), { target: { value: '2026-10-23' } }); refresh();
  expect(screen.getByRole('alert')).toHaveTextContent('en fazla 366');
  fireEvent.change(screen.getByLabelText('Forecast bitiş'), { target: { value: '2028-10-23' } }); refresh();
  expect(api.get).toHaveBeenCalledTimes(count);
});

it('keeps revenue currencies separate, changes chart/table view, and uses the selected occupancy denominator', async () => {
  render(<FrontdeskForecastReport />); const table = await loaded();
  expect(table).not.toHaveTextContent('EUR:');
  expect(table).toHaveTextContent('Toplam dolu oda');
  fireEvent.click(screen.getByLabelText('Tüm sütunları göster (kişi, hareket, gelir)'));
  expect(table).toHaveTextContent('EUR:'); expect(table).toHaveTextContent('USD:'); expect(table).not.toHaveTextContent('₺');
  fireEvent.change(screen.getByLabelText('Forecast doluluk bazı'), { target: { value: 'sellable' } });
  expect(screen.getByTestId('forecast-occupancy-total')).toHaveTextContent('%62,5');
  expect(table).toHaveTextContent('Doluluk % (satılabilir)');
  fireEvent.click(within(screen.getByRole('group', { name: 'Forecast görünümü' })).getByRole('button', { name: 'Gelir', exact: true }));
  expect(screen.getByTestId('line-chart_revenue')).toHaveAttribute('data-connect-nulls', 'false');
  expect(screen.getByLabelText('Forecast grafik para birimi')).toHaveValue('EUR');
  fireEvent.change(screen.getByLabelText('Forecast grafik para birimi'), { target: { value: 'USD' } });
  fireEvent.click(within(screen.getByRole('group', { name: 'Forecast görünümü' })).getByRole('button', { name: 'Geliş–Ayrılış', exact: true }));
  expect(table).toHaveTextContent('Gelen oda'); expect(table).not.toHaveTextContent('Rezervasyon oda bedeli');
});

it('binds export to the displayed snapshot/view/basis and refuses changed data', async () => {
  render(<FrontdeskForecastReport />); await loaded();
  fireEvent.change(screen.getByLabelText('Forecast doluluk bazı'), { target: { value: 'sellable' } });
  fireEvent.click(within(screen.getByRole('group', { name: 'Forecast görünümü' })).getByRole('button', { name: 'Gelir', exact: true }));
  api.get.mockRejectedValueOnce({ response: { status: 409 } });
  fireEvent.click(screen.getByRole('button', { name: 'Excel', exact: true }));
  await screen.findByText(/Forecast verisi değişti/);
  expect(api.get).toHaveBeenLastCalledWith('/reports/frontdesk-forecast', { params: { start_date: '2026-10-24', end_date: '2026-11-22', room_type: '',
    output: 'xlsx', snapshot: 'same-financial-snapshot', view: 'revenue', basis: 'sellable', detail: 'summary' }, responseType: 'blob' });
  expect(screen.queryByTestId('frontdesk-forecast-table')).not.toBeInTheDocument();
});

it('clears stale data on refresh failure and prints only after a successful scope', async () => {
  render(<FrontdeskForecastReport />); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'Yazdır / PDF' })); expect(window.print).toHaveBeenCalledOnce();
  api.get.mockRejectedValueOnce(new Error('Test network failure')); refresh();
  expect(await screen.findByRole('alert')).toHaveTextContent('Test network failure');
  expect(screen.queryByTestId('frontdesk-forecast-table')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Yazdır / PDF' })).toBeDisabled();
});

it('rejects an incomplete response instead of displaying empty subviews as a valid report', async () => {
  api.get.mockImplementation(async (_url, { params }) => { const data = payload(params); delete data.columns.stay_types; return { data }; });
  render(<FrontdeskForecastReport />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Forecast yanıtı');
  expect(screen.queryByTestId('frontdesk-forecast-table')).not.toBeInTheDocument();
});

it('reuses the daily snapshot for the room-type matrix and paginates all dates for printing', async () => {
  render(<FrontdeskForecastReport />); await loaded();
  const calls = api.get.mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Oda tipi matrisi', exact: true }));
  expect(screen.getByTestId('forecast-room-type-matrix')).toHaveTextContent('Standard');
  expect(document.querySelectorAll('.forecast-matrix-print-page')).toHaveLength(5);
  expect(api.get).toHaveBeenCalledTimes(calls);
  fireEvent.change(screen.getByLabelText('Forecast doluluk bazı'), { target: { value: 'sellable' } });
  expect(screen.getByTestId('forecast-room-type-matrix')).toHaveTextContent('%62,5');
  fireEvent.click(within(screen.getByTestId('forecast-room-type-matrix')).getAllByRole('button')[0]);
  expect(screen.getByTestId('frontdesk-forecast-table')).toBeInTheDocument();
  expect(within(screen.getByTestId('frontdesk-forecast-table')).getAllByRole('row')[1]).toHaveAttribute('aria-selected', 'true');
});
