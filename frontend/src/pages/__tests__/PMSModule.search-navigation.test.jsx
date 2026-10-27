import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const { translate, hasModule } = vi.hoisted(() => ({ translate: (key, options) => typeof options === 'string' ? options : options?.defaultValue || key, hasModule: () => true }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/Layout', () => ({ default: ({ children }) => <main>{children}</main> }));
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({ hasModule }) }));
vi.mock('@/config/navItems', () => ({ NAV_ITEMS: [] }));
vi.mock('@/utils/moduleAccess', () => ({ canAccessPmsTab: () => true, canAccessNavItem: () => true }));
vi.mock('@/components/pms/BookingsTab', () => ({ default: ({ businessDate }) => <section>Reservation workspace {businessDate}</section> }));
vi.mock('@/components/pms/GuestsTab', () => ({ default: () => <section>Guest workspace</section> }));
vi.mock('@/components/pms/Guest360Dialog', () => ({ default: ({ open, onClose, guest360Data, loadingGuest360, error, selectedGuest360, loadGuest360 }) => open && <section role="dialog" aria-label="Guest profile">
  {loadingGuest360 ? 'Loading guest' : error ? <div role="alert">{error}<button onClick={() => loadGuest360(selectedGuest360)}>Retry</button></div> : <span>{guest360Data?.guest?.name} ({selectedGuest360})</span>}
  <button onClick={onClose}>Close profile</button>
</section> }));
vi.mock('@/pages/ReservationDetailModal', () => ({ default: ({ bookingId }) => <section role="dialog">Reservation detail {bookingId}</section> }));
import PMSModule from '../PMSModule';

const guest = { id: 'guest-outside-bootstrap', name: 'Murat Sutay' };
const booking = { id: 'booking-outside-window', check_in: '2026-11-20', check_out: '2026-11-22' };
const user = { id: 'synthetic-user', role: 'admin', effective_permissions: ['view_bookings'] };
const tenant = { id: 'synthetic-tenant', subscription_plan: 'core_small_hotel' };
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };
const mount = (extra = {}) => render(<MemoryRouter><PMSModule user={user} tenant={{ ...tenant, ...extra }} /></MemoryRouter>);
const search = async () => {
  fireEvent.change(await screen.findByPlaceholderText('Misafir, rezervasyon, oda, sayfa ara...'), { target: { value: 'Murat' } });
  return screen.findByRole('button', { name: 'Murat Sutay' });
};
beforeEach(() => {
  window.location.hash = 'bookings';
  vi.clearAllMocks();
  axios.get.mockImplementation(url => {
    if (url === '/night-audit/business-date') return Promise.resolve({ data: { business_date: '2026-10-26' } });
    if (url.startsWith('/pms/guests/search?')) return Promise.resolve({ data: [guest] });
    if (url.startsWith('/pms/bookings?search=')) return Promise.resolve({ data: { bookings: [booking] } });
    if (url === `/crm/guest/${guest.id}`) return Promise.resolve({ data: { guest } });
    return Promise.resolve({ data: [] });
  });
});
afterEach(() => { window.location.hash = ''; });

describe('global search opens the selected PMS entity', () => {
  it('opens the exact guest 360 profile even outside the bootstrap list, not frontdesk', async () => {
    mount();
    expect(await screen.findByText('Reservation workspace 2026-10-26')).toBeInTheDocument();
    fireEvent.click(await search());
    expect(await screen.findByRole('dialog', { name: 'Guest profile' })).toHaveTextContent(`Murat Sutay (${guest.id})`);
    expect(window.location.hash).toBe('#guests');
    expect(screen.getByText('Guest workspace')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith(`/crm/guest/${guest.id}`, { timeout: 15000 });
    expect(toast.info).not.toHaveBeenCalled();
  });

  it('opens a reservation result by its exact ID without requiring it in the 30-day dataset', async () => {
    mount();
    await search();
    fireEvent.click(screen.getByRole('button', { name: /Booking #booking-/ }));
    expect(await screen.findByRole('dialog')).toHaveTextContent(`Reservation detail ${booking.id}`);
    expect(window.location.hash).toBe('#bookings');
    expect(toast.info).not.toHaveBeenCalled();
  });

  it('shows a truthful inline error and retries the selected guest on a read failure', async () => {
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url === `/crm/guest/${guest.id}` ? Promise.reject(new Error('unavailable')) : original(url));
    mount();
    fireEvent.click(await search());
    expect(await screen.findByRole('alert')).toHaveTextContent('Misafir profili yüklenemedi');
    axios.get.mockImplementation(original);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent(`Murat Sutay (${guest.id})`));
    expect(toast.info).not.toHaveBeenCalled();
  });

  it('never displays a mismatched guest returned by the service', async () => {
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.startsWith('/crm/guest/') ? Promise.resolve({ data: { guest: { id: 'wrong', name: 'Wrong guest' } } }) : original(url));
    mount();
    fireEvent.click(await search());
    expect(await screen.findByRole('alert')).toHaveTextContent('Misafir profili yüklenemedi');
    expect(screen.queryByText(/Wrong guest/)).not.toBeInTheDocument();
  });

  it('does not reopen a closed profile from a delayed response', async () => {
    const slow = deferred();
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url === `/crm/guest/${guest.id}` ? slow.promise : original(url));
    mount();
    fireEvent.click(await search());
    expect(await screen.findByRole('dialog')).toHaveTextContent('Loading guest');
    fireEvent.click(screen.getByRole('button', { name: 'Close profile' }));
    await act(async () => slow.resolve({ data: { guest } }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not replace the latest selected guest with an earlier slow profile', async () => {
    const slow = deferred(), other = { id: 'selin', name: 'Selin Demir' };
    const original = axios.get.getMockImplementation();
    let selectedSearchGuest = guest;
    axios.get.mockImplementation(url => {
      if (url.startsWith('/pms/guests/search?')) return Promise.resolve({ data: [selectedSearchGuest] });
      if (url === `/crm/guest/${guest.id}`) return slow.promise;
      if (url === '/crm/guest/selin') return Promise.resolve({ data: { guest: other } });
      return original(url);
    });
    mount();
    fireEvent.click(await search());
    expect(await screen.findByRole('dialog')).toHaveTextContent('Loading guest');
    selectedSearchGuest = other;
    fireEvent.change(screen.getByPlaceholderText('Misafir, rezervasyon, oda, sayfa ara...'), { target: { value: 'Selin' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Selin Demir' }));
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent('Selin Demir (selin)'));
    await act(async () => slow.resolve({ data: { guest } }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Selin Demir (selin)');
    expect(screen.getByRole('dialog')).not.toHaveTextContent('Murat Sutay');
  });

  it('does not navigate to a tenant-disabled entity tab', async () => {
    mount({ modules: { 'pms.guests': false } });
    fireEvent.click(await search());
    expect(toast.error).toHaveBeenCalledWith('Bu ekrana erişim yetkiniz yok.');
    expect(axios.get.mock.calls.some(([url]) => url.startsWith('/crm/guest/'))).toBe(false);
    expect(window.location.hash).toBe('#bookings');
  });
});
