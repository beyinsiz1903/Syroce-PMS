import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import MobileDashboard from '@/pages/MobileDashboard';
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, values) => values?.count != null ? `${key}: ${values.count}` : key }) }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it('uses the server business day and real zero arrivals rather than calendar time or sample alerts', async () => {
  axios.get.mockImplementation(async path => ({ data: path === '/frontdesk/business-day'
    ? { business_date: '2026-11-12', arrivals: [] } : { status_counts: { dirty: 26 } } }));
  render(<MemoryRouter><MobileDashboard user={{ role: 'super_admin', tenant_id: 'test' }} /></MemoryRouter>);
  expect(await screen.findByText('12.11.2026')).toBeVisible();
  expect(screen.getByText('mobileDashboard.arrivalsExpected: 0')).toBeVisible();
  expect(screen.getByText('mobileDashboard.roomsNeedCleaning: 26')).toBeVisible();
  expect(screen.queryByText('mobileDashboard.pendingRequests: 5')).not.toBeInTheDocument();
});
it('shows unknown rather than fabricated zeroes when operational sources fail', async () => {
  axios.get.mockRejectedValue(new Error('Unavailable'));
  render(<MemoryRouter><MobileDashboard user={{ role: 'front_desk', tenant_id: 'test' }} /></MemoryRouter>);
  expect(await screen.findByText('Beklenen girişler: Doğrulanamadı')).toBeVisible();
  expect(screen.getByText('Temizlik bekleyen oda: Doğrulanamadı')).toBeVisible();
  expect(screen.queryByText(/arrivalsExpected: 8/)).not.toBeInTheDocument();
});
