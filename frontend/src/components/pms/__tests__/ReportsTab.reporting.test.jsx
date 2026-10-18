import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import ReportsTab from '../ReportsTab';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-09-15' }));
vi.mock('@/components/pms/ReservationReportsTab', () => ({ default: () => null }));

function mockApi({ failRevenue = false } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.startsWith('/reports/occupancy?')) return Promise.resolve({ data: { occupancy_rate: 50, occupied_room_nights: 15, total_room_nights: 30, total_rooms: 2 } });
    if (url.startsWith('/reports/revenue?')) return failRevenue ? Promise.reject(new Error('unavailable')) : Promise.resolve({ data: { total_revenue_by_currency: { TRY: 1000.49, EUR: 25.75 }, revenue_by_type_currency: {} } });
    if (url.startsWith('/reports/market-segment?')) return Promise.resolve({ data: { total_bookings: 2, market_segments: {
      direct: { bookings: 1, nights: 1, revenue: 1000.49, adr: 1000.49, revenue_by_currency: { TRY: 1000.49 }, adr_by_currency: { TRY: 1000.49 } },
      ota: { bookings: 1, nights: 1, revenue: 25.75, adr: 25.75, revenue_by_currency: { EUR: 25.75 }, adr_by_currency: { EUR: 25.75 } },
    }, rate_types: {} } });
    if (url.startsWith('/reports/forecast?')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: null });
  });
}

describe('ReportsTab reporting contracts', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses the PMS business month to date, not the browser month or future capacity', async () => {
    mockApi();
    render(<ReportsTab />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/reports/occupancy?start_date=2026-09-01&end_date=2026-09-15'));
    expect(axios.get).toHaveBeenCalledWith('/reports/revenue?start_date=2026-09-01&end_date=2026-09-15');
    expect(await screen.findByText(/Gerçekleşen dönem: 2026-09-01 – 2026-09-15/)).toBeInTheDocument();
  });

  it('renders each market currency and does not compare them in one pie', async () => {
    mockApi();
    render(<ReportsTab />);
    await screen.findByText(/Gerçekleşen dönem:/);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Pazar Segmenti' }), { button: 0, ctrlKey: false });
    expect(await screen.findByText(/Farklı para birimlerinin gelir payları karşılaştırılamaz/)).toBeInTheDocument();
    expect(screen.getAllByText(/1\.000,49/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/25,75/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Segment Gelir Grafigi')).not.toBeInTheDocument();
  });

  it('shows endpoint failures rather than a fake zero or permanent loading result', async () => {
    mockApi({ failRevenue: true });
    render(<ReportsTab />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Gelir');
    expect(screen.getAllByText('Alınamadı')).toHaveLength(3);
    expect(screen.getByRole('alert')).toHaveTextContent('Boş veya sıfır sonuç olarak değerlendirmeyin');
  });
});
