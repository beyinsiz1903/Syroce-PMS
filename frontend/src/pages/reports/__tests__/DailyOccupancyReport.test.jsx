import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DailyOccupancyReport from '../DailyOccupancyReport';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-11-10' }));
const response = params => ({ start_date: params.start_date, end_date: params.end_date, room_type: params.room_type,
  business_date: '2026-11-10', room_types: ['Standard'], snapshot: 'verified',
  rows: [{ date: params.start_date, physical_rooms: 20, available_rooms: 20, actual_rooms: 8, expected_rooms: 14, actual_occupancy: 40, expected_occupancy: 70 }],
  room_type_groups: [{ room_type: 'Standard', label: 'Standard', physical_rooms: 20,
    rows: [{ date: params.start_date, physical_rooms: 20, available_rooms: 20, actual_rooms: 8, expected_rooms: 14, actual_occupancy: 40, expected_occupancy: 70 }] }],
  totals: { actual: { room_nights: 8, available_room_nights: 20, occupancy: 40 }, expected: { room_nights: 14, available_room_nights: 20, occupancy: 70 } } });

const dailyTable = async () => {
  await screen.findByTestId('occupancy-matrix');
  fireEvent.click(screen.getByRole('button', { name: 'Günlük liste' }));
  return screen.findByTestId('daily-occupancy-table');
};

beforeEach(() => { get.mockReset().mockImplementation(async (_, { params }) => ({ data: response(params) })); });

describe('daily occupancy scope and exports', () => {
  it('shows a compact daily summary and keeps the custom range/export safeguards', async () => {
    render(<DailyOccupancyReport />);
    expect(await dailyTable()).toHaveTextContent('%70');
    fireEvent.change(screen.getByLabelText('Doluluk başlangıç'), { target: { value: '2026-11-12' } });
    fireEvent.change(screen.getByLabelText('Doluluk bitiş'), { target: { value: '2026-11-14' } });
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel İndir' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Göster / Yenile' }));
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/reports/occupancy-calendar', { params: { start_date: '2026-11-12', end_date: '2026-11-14', room_type: '' } }));
    expect(await screen.findByTestId('daily-occupancy-table')).toHaveTextContent('12.11.2026');
  });

  it('rejects a reversed range before the API', async () => {
    render(<DailyOccupancyReport />);
    await dailyTable();
    fireEvent.change(screen.getByLabelText('Doluluk bitiş'), { target: { value: '2026-11-09' } });
    fireEvent.click(screen.getByRole('button', { name: 'Göster / Yenile' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('366 gün');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('rejects a response from another scope and makes it unexportable', async () => {
    get.mockResolvedValue({ data: response({ start_date: '2026-01-01', end_date: '2026-01-01', room_type: '' }) });
    render(<DailyOccupancyReport />);
    expect(await screen.findByRole('alert')).toHaveTextContent('kapsamı');
    expect(screen.getByRole('button', { name: 'Yazdır / PDF' })).toBeDisabled();
  });

  it('does not revive an old request after unmount', async () => {
    let resolve;
    get.mockReturnValue(new Promise(done => { resolve = done; }));
    const page = render(<DailyOccupancyReport />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    page.unmount();
    await act(async () => resolve({ data: response({ start_date: '2026-11-10', end_date: '2026-11-23', room_type: '' }) }));
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
  });

  it('sends the verified snapshot and invalidates stale Excel exports', async () => {
    render(<DailyOccupancyReport />);
    await screen.findByTestId('occupancy-matrix');
    get.mockRejectedValueOnce({ response: { status: 409 } });
    fireEvent.click(screen.getByRole('button', { name: 'Excel İndir' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('verisi değişti');
    expect(get.mock.calls.at(-1)[1]).toMatchObject({ responseType: 'blob', params: { snapshot: 'verified', output: 'xlsx' } });
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
  });

  it('defaults to 14 days and offers a 30-day quick range crossing the month boundary', async () => {
    render(<DailyOccupancyReport />);
    await screen.findByTestId('occupancy-matrix');
    expect(screen.getByLabelText('Doluluk bitiş')).toHaveValue('2026-11-23');
    fireEvent.click(screen.getByRole('button', { name: '30 gün' }));
    expect(screen.getByLabelText('Doluluk bitiş')).toHaveValue('2026-12-09');
  });

  it('uses one metric per date, includes todays arrivals and weights the period by capacity', async () => {
    get.mockImplementation(async (_, { params }) => ({ data: { ...response(params), room_type_groups: [], rows: [
      { date: '2026-11-09', available_rooms: 10, actual_rooms: 5, actual_occupancy: 50, expected_rooms: null },
      { date: '2026-11-10', available_rooms: 20, actual_rooms: 8, actual_occupancy: 40, expected_rooms: 14, expected_occupancy: 70 },
      { date: '2026-11-11', available_rooms: 30, actual_rooms: null, expected_rooms: 3, expected_occupancy: 10 },
    ] } }));
    render(<DailyOccupancyReport />);
    const table = await dailyTable();
    expect(within(table).getAllByRole('columnheader')).toHaveLength(6);
    expect(within(table).getByRole('row', { name: /09.11.2026/ })).toHaveTextContent('Gerçekleşen');
    const today = within(table).getByRole('row', { name: /10.11.2026/ });
    expect(today).toHaveTextContent('%70');
    expect(today).not.toHaveTextContent('%40');
    expect(within(today).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['%70', '14', '+6', '20', 'Beklenen']);
    expect(screen.getByTestId('occupancy-period-total')).toHaveTextContent('%36,67'); // 22/60, not mean(50,70,10)
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Hesaplama detaylarını göster' }));
    expect(screen.getByTestId('occupancy-details-table')).toHaveTextContent('%40');
    fireEvent.click(screen.getByRole('button', { name: 'Detayları gizle' }));
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
  });

  it('retains warnings above the collapsed details and never caps excess occupancy or fabricates missing values', async () => {
    get.mockImplementation(async (_, { params }) => ({ data: { ...response(params), room_type_groups: [], rows: [
      { date: '2026-11-10', available_rooms: 2, expected_rooms: 3, expected_occupancy: 150, overbooked_rooms: 1 },
      { date: '2026-11-11', available_rooms: 0, expected_rooms: 0, expected_occupancy: null },
    ] } }));
    render(<DailyOccupancyReport />);
    const table = await dailyTable();
    expect(table).toHaveTextContent('%150');
    expect(table).toHaveTextContent('−1');
    expect(within(table).getByRole('row', { name: /11.11.2026/ })).toHaveTextContent('—');
    expect(screen.getByRole('alert')).toHaveTextContent('1 fazla satış');
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
  });

  it('defaults to a room-type matrix, changes indicator without refetching and opens read-only cell details', async () => {
    render(<DailyOccupancyReport />);
    const table = await screen.findByTestId('occupancy-matrix');
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
    expect(within(table).getByRole('rowheader', { name: /Tüm tesis/ })).toBeInTheDocument();
    expect(within(table).getByRole('rowheader', { name: /Standard/ })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Günlük doluluk grafiği/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Doluluk göstergesi'), { target: { value: 'remaining' } });
    const cell = within(table).getByRole('button', { name: /^Standard,/ });
    expect(within(cell).getByText('+6')).toBeInTheDocument();
    fireEvent.click(cell);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Standard');
    expect(dialog).toHaveTextContent('Net kalan');
    expect(dialog).toHaveTextContent('+6');
    expect(dialog).toHaveTextContent('Satışa kapalı oda');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('prints at most seven dates per table and preserves all dates in order', async () => {
    get.mockImplementation(async (_, { params }) => {
      const data = response(params);
      data.rows = Array.from({ length: 14 }, (_, i) => ({ ...data.rows[0], date: `2026-11-${String(i + 10).padStart(2, '0')}` }));
      data.room_type_groups[0].rows = data.rows;
      return { data };
    });
    render(<DailyOccupancyReport />);
    await screen.findByTestId('occupancy-matrix');
    const sections = screen.getByTestId('occupancy-print-matrix').querySelectorAll('section');
    expect(sections).toHaveLength(2);
    expect(sections[0]).toHaveTextContent('10.11.2026');
    expect(sections[0]).toHaveTextContent('16.11.2026');
    expect(sections[0]).not.toHaveTextContent('17.11.2026');
    expect(sections[1]).toHaveTextContent('17.11.2026');
    expect(sections[1]).toHaveTextContent('23.11.2026');
    expect(sections[1].querySelectorAll('thead th')).toHaveLength(8);
  });

  it('exports the active matrix metric and the daily view explicitly', async () => {
    render(<DailyOccupancyReport />);
    await screen.findByTestId('occupancy-matrix');
    fireEvent.change(screen.getByLabelText('Doluluk göstergesi'), { target: { value: 'remaining' } });
    get.mockRejectedValueOnce(new Error('download test'));
    fireEvent.click(screen.getByRole('button', { name: 'Excel İndir' }));
    await waitFor(() => expect(get.mock.calls.at(-1)[1].params).toMatchObject({ view: 'matrix', metric: 'remaining', snapshot: 'verified' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Günlük liste' }));
    get.mockRejectedValueOnce(new Error('download test'));
    fireEvent.click(screen.getByRole('button', { name: 'Excel İndir' }));
    await waitFor(() => expect(get.mock.calls.at(-1)[1].params).toMatchObject({ view: 'daily', metric: 'remaining' }));
  });

  it('rejects room-type rows for a different date instead of silently misaligning the matrix', async () => {
    get.mockImplementation(async (_, { params }) => {
      const data = response(params);
      data.room_type_groups[0].rows[0].date = '2025-01-01';
      return { data };
    });
    render(<DailyOccupancyReport />);
    expect(await screen.findByRole('alert')).toHaveTextContent('kapsamı');
    expect(screen.getByRole('button', { name: 'Excel İndir' })).toBeDisabled();
  });

  it('shows a type-level shortfall when the house still has availability and charts percentages above 100', async () => {
    get.mockImplementation(async (_, { params }) => {
      const data = response(params);
      data.room_type_groups[0].rows[0] = { ...data.rows[0], available_rooms: 2, expected_rooms: 3, expected_occupancy: 150 };
      return { data };
    });
    render(<DailyOccupancyReport />);
    const table = await screen.findByTestId('occupancy-matrix');
    expect(table).toHaveTextContent('%150');
    expect(table).toHaveTextContent('−1 kalan');
    expect(table).toHaveTextContent('+6 kalan');
    expect(screen.getByRole('alert')).toHaveTextContent('Tesis toplamında boş oda olması');
  });
});
