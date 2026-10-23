import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DailyOccupancyReport from '../DailyOccupancyReport';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-11-10' }));
const response = params => ({ start_date: params.start_date, end_date: params.end_date, room_type: params.room_type,
  business_date: '2026-11-10', room_types: ['Standard'], snapshot: 'verified',
  rows: [{ date: params.start_date, physical_rooms: 20, available_rooms: 20, actual_rooms: 8, expected_rooms: 14, actual_occupancy: 40, expected_occupancy: 70 }],
  totals: { actual: { room_nights: 8, available_room_nights: 20, occupancy: 40 }, expected: { room_nights: 14, available_room_nights: 20, occupancy: 70 } } });

beforeEach(() => { get.mockReset().mockImplementation(async (_, { params }) => ({ data: response(params) })); });

describe('daily occupancy scope and exports', () => {
  it('shows a compact daily summary and keeps the custom range/export safeguards', async () => {
    render(<DailyOccupancyReport />);
    expect(await screen.findByTestId('daily-occupancy-table')).toHaveTextContent('%70');
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
    await screen.findByTestId('daily-occupancy-table');
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
    await act(async () => resolve({ data: response({ start_date: '2026-11-10', end_date: '2026-12-09', room_type: '' }) }));
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
  });

  it('sends the verified snapshot and invalidates stale Excel exports', async () => {
    render(<DailyOccupancyReport />);
    await screen.findByTestId('daily-occupancy-table');
    get.mockRejectedValueOnce({ response: { status: 409 } });
    fireEvent.click(screen.getByRole('button', { name: 'Excel İndir' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('verisi değişti');
    expect(get.mock.calls.at(-1)[1]).toMatchObject({ responseType: 'blob', params: { snapshot: 'verified', output: 'xlsx' } });
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
  });

  it('the 30-day quick date crosses the month boundary', async () => {
    render(<DailyOccupancyReport />);
    await screen.findByTestId('daily-occupancy-table');
    expect(screen.getByLabelText('Doluluk bitiş')).toHaveValue('2026-12-09');
  });

  it('uses one metric per date, includes todays arrivals and weights the period by capacity', async () => {
    get.mockImplementation(async (_, { params }) => ({ data: { ...response(params), rows: [
      { date: '2026-11-09', available_rooms: 10, actual_rooms: 5, actual_occupancy: 50, expected_rooms: null },
      { date: '2026-11-10', available_rooms: 20, actual_rooms: 8, actual_occupancy: 40, expected_rooms: 14, expected_occupancy: 70 },
      { date: '2026-11-11', available_rooms: 30, actual_rooms: null, expected_rooms: 3, expected_occupancy: 10 },
    ] } }));
    render(<DailyOccupancyReport />);
    const table = await screen.findByTestId('daily-occupancy-table');
    expect(within(table).getAllByRole('columnheader')).toHaveLength(6);
    expect(within(table).getByRole('row', { name: /09.11.2026/ })).toHaveTextContent('Gerçekleşen');
    const today = within(table).getByRole('row', { name: /10.11.2026/ });
    expect(today).toHaveTextContent('%70');
    expect(today).not.toHaveTextContent('%40');
    expect(within(today).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['%70', '14', '6', '20', 'Beklenen']);
    expect(screen.getByTestId('occupancy-period-total')).toHaveTextContent('%36,67'); // 22/60, not mean(50,70,10)
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Hesaplama detaylarını göster' }));
    expect(screen.getByTestId('occupancy-details-table')).toHaveTextContent('%40');
    fireEvent.click(screen.getByRole('button', { name: 'Detayları gizle' }));
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
  });

  it('retains warnings above the collapsed details and never caps excess occupancy or fabricates missing values', async () => {
    get.mockImplementation(async (_, { params }) => ({ data: { ...response(params), rows: [
      { date: '2026-11-10', available_rooms: 2, expected_rooms: 3, expected_occupancy: 150, overbooked_rooms: 1 },
      { date: '2026-11-11', available_rooms: 0, expected_rooms: 0, expected_occupancy: null },
    ] } }));
    render(<DailyOccupancyReport />);
    const table = await screen.findByTestId('daily-occupancy-table');
    expect(table).toHaveTextContent('%150');
    expect(within(table).getByRole('row', { name: /11.11.2026/ })).toHaveTextContent('—');
    expect(screen.getByRole('alert')).toHaveTextContent('1 fazla satış');
    expect(screen.queryByTestId('occupancy-details-table')).not.toBeInTheDocument();
  });
});
