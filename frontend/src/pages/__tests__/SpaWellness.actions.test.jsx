import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { confirmDialog } from '@/lib/dialogs';
import SpaWellness from '@/pages/SpaWellness';
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));
vi.mock('@/lib/idle', () => ({ runIdle: fn => { void fn(); } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
let appointmentStatus = 'scheduled';
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({ getLimit: () => 100, hasFeature: () => true, hasModule: () => true, loading: false, isSuperAdmin: true }) }));
beforeEach(() => {
  vi.clearAllMocks();
  appointmentStatus = 'scheduled';
  axios.get.mockImplementation(async url => ({ data: url === '/spa/appointments' ? { appointments: [{ id: 'a', guest_name: 'Şule Acar', status: appointmentStatus, starts_at: '2026-11-12T12:00:00Z', price: 1000, currency: 'TRY' }] } : url === '/spa/daily-summary' ? { timezone: 'Europe/Istanbul', total: 1 } : {} }));
  axios.post.mockResolvedValue({ data: {} });
});
afterEach(cleanup);
const mount = () => render(<MemoryRouter><SpaWellness /></MemoryRouter>);
it('requires explicit completion confirmation before posting a sale', async () => {
  mount();
  const complete = await screen.findByRole('button', { name: 'Şule Acar — Hizmeti tamamla' });
  confirmDialog.mockResolvedValueOnce(false);
  fireEvent.click(complete);
  await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
  expect(axios.post).not.toHaveBeenCalled();
  confirmDialog.mockResolvedValueOnce(true);
  fireEvent.click(complete);
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/spa/appointments/a/status', { status: 'completed' }));
  expect(confirmDialog.mock.calls[1][0].message).toContain('satış');
});
it('requests the selected day for the SPA summary', async () => {
  const { container } = mount();
  await screen.findByText('Şule Acar');
  fireEvent.change(container.querySelector('input[type="date"]'), { target: { value: '2026-11-12' } });
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/spa/daily-summary', { params: { date: '2026-11-12' } }));
  expect(screen.getByText('Seçilen gün toplamı')).toBeInTheDocument();
});

it('keeps the supported cancellation action available for an in-progress service', async () => {
  appointmentStatus = 'in_progress';
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Şule Acar — Randevuyu iptal et' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/spa/appointments/a/status', { status: 'cancelled' }));
  expect(confirmDialog).not.toHaveBeenCalled();
});
