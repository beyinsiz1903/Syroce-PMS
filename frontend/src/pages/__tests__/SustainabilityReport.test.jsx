import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import SustainabilityReport, { currentMonth } from '../SustainabilityReport';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const report = { period_start: '2026-10-01', period_end: '2026-10-31', total_scope_1: 0, total_scope_2: 4.29, total_scope_3: 0,
  total_emissions: 4.29, total_room_nights: 0, emissions_per_room_night: null, record_count: 1, prorated_record_count: 1,
  allocation: 'Kayıt dönemi rapor dönemini aşıyorsa tüketim gün oranında bölüştürülür (tahmin).' };

describe('SustainabilityReport', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks the signed-in API for the current month, not a fixed July 2026', async () => {
    axios.get.mockImplementation((url) => Promise.resolve({ data: url.endsWith('/report') ? report : [] }));
    render(<SustainabilityReport />);
    const month = currentMonth();
    expect(axios.get).toHaveBeenCalledWith('/sustainability/report', { params: { start_date: month.start, end_date: month.end } });
    expect(JSON.stringify(axios.get.mock.calls)).not.toContain('2026-07');
    expect(await screen.findByTestId('sustainability-per-night')).toHaveTextContent('Hesaplanamaz');
    expect(screen.getByTestId('sustainability-allocation')).toHaveTextContent('gün oranında');
  });

  it('shows a load failure as an error, not an empty report', async () => {
    axios.get.mockRejectedValue({ response: { status: 403, data: { detail: 'Bu işlem için yetkiniz yok' } } });
    render(<SustainabilityReport />);
    expect(await screen.findByRole('alert')).toHaveTextContent('yetkiniz yok');
  });

  it('computes the calendar month bounds', () => {
    expect(currentMonth(new Date(2026, 1, 15))).toEqual({ start: '2026-02-01', end: '2026-02-28' });
    expect(currentMonth(new Date(2026, 11, 31))).toEqual({ start: '2026-12-01', end: '2026-12-31' });
  });
});
