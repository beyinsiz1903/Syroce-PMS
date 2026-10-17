import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('axios', () => ({ default: { get: (...a) => apiGet(...a) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AgencyReadiness from '@/pages/AgencyReadiness';

const agencies = [
  { agency_id: 'norate', agency_name: 'Norate Travel', status: 'error', contract: { code: 'SOZ-1', status: 'approved' }, searches_here: 3, bookings: 0,
    checks: [{ key: 'agency', level: 'ok', message: 'Acente hesabı aktif', action: null },
      { key: 'searches', level: 'error', message: '3 aramanın hiçbirinde oteliniz sonuç vermedi; en sık neden: Fiyat paylaşılmamış (2).',
        action: { label: 'Fiyat paylaş', path: '/unified-rate-manager' } }] },
  { agency_id: 'good', agency_name: 'Good Travel', status: 'ok', contract: { code: 'SOZ-2', status: 'approved' }, searches_here: 1, bookings: 1,
    checks: [{ key: 'agency', level: 'ok', message: 'Acente hesabı aktif', action: null }] },
];

describe('AgencyReadiness', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('lists problems with the screen that fixes them and checks the next nights on demand', async () => {
    apiGet.mockImplementation(url => Promise.resolve({ data: url.endsWith('/nights')
      ? { nights: [{ date: '2026-10-17', status: 'ok' }, { date: '2026-10-18', status: 'no_rate' }], counts: { ok: 1, no_rate: 1 },
        actions: { no_rate: { label: 'Fiyat paylaş', path: '/unified-rate-manager' } } }
      : { search_window_days: 30, agencies } }));
    render(<MemoryRouter><AgencyReadiness /></MemoryRouter>);
    const card = await screen.findByTestId('readiness-norate');
    expect(within(card).getByText('Satış engelli')).toBeTruthy();
    expect(within(card).getByText('Fiyat paylaş').getAttribute('href')).toBe('/unified-rate-manager');
    expect(within(screen.getByTestId('readiness-good')).getByText('Hazır')).toBeTruthy();
    await userEvent.click(within(card).getByTestId('check-nights-norate'));
    const nights = await within(card).findByTestId('nights-norate');
    expect(within(nights).getByText('1 gece satılabilir')).toBeTruthy();
    expect(apiGet).toHaveBeenCalledWith('/marketplace/hotel/agency-readiness/norate/nights', { params: { days: 30 } });
  });

  it('survives an unexpected response', async () => {
    apiGet.mockResolvedValue({ data: { detail: 'x' } });
    render(<MemoryRouter><AgencyReadiness /></MemoryRouter>);
    expect(await screen.findByText('Henüz acente sözleşmesi yok.')).toBeTruthy();
  });
});
