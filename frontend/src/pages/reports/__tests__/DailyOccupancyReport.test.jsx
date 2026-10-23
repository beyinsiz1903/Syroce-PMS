import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('shows each date and separate actual/expected values with a custom range', async () => {
    render(<DailyOccupancyReport />);
    expect(await screen.findByTestId('daily-occupancy-table')).toHaveTextContent('%70');
    fireEvent.change(screen.getByLabelText('Doluluk başlangıç'), { target: { value: '2026-11-12' } });
    fireEvent.change(screen.getByLabelText('Doluluk bitiş'), { target: { value: '2026-11-14' } });
    expect(screen.queryByTestId('daily-occupancy-table')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel İndir' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Göster / Yenile' }));
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/reports/occupancy-calendar', { params: { start_date: '2026-11-12', end_date: '2026-11-14', room_type: '' } }));
    expect(await screen.findByTestId('daily-occupancy-table')).toHaveTextContent('2026-11-12');
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
});
