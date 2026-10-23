import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const { translate } = vi.hoisted(() => ({ translate: (key, options) => typeof options === 'string' ? options : options?.defaultValue || key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/Layout', () => ({ default: ({ children }) => <main>{children}</main> }));
vi.mock('@/components/GlobalSearch', () => ({ default: () => null }));
vi.mock('@/utils/moduleAccess', () => ({ canAccessPmsTab: (_user, tab) => tab === 'bookings' }));
vi.mock('@/components/pms/BookingsTab', () => ({ default: ({ bookings, bookingStats, historyLoading, historyError }) => <section>
  <span data-testid="list">{bookings.map(row => row.id).join(',')}</span>
  <span data-testid="count">{bookingStats.total}</span>
  {historyLoading && <span>history loading</span>}{historyError && <span role="alert">{historyError}</span>}
</section> }));
import PMSModule from '../PMSModule';

const row = id => ({ id, guest_name: id, status: 'confirmed', room_id: null, total_amount: 0 });
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };
const user = { id: 'synthetic-user', role: 'admin', effective_permissions: ['view_bookings'] };
const tenant = { id: 'synthetic-tenant', subscription_plan: 'core_small_hotel' };
const mount = () => render(<MemoryRouter><PMSModule user={user} tenant={tenant} /></MemoryRouter>);
beforeEach(() => {
  window.location.hash = 'bookings';
  axios.get.mockReset().mockImplementation(url => {
    if (url === '/night-audit/business-date') return Promise.resolve({ data: { business_date: '2026-09-05' } });
    if (url.includes('full_history=true')) return Promise.resolve({ data: [row('full-1'), row('full-2')] });
    if (url.startsWith('/pms/bookings?')) return Promise.resolve({ data: [row('narrow')] });
    return Promise.resolve({ data: [] });
  });
});
afterEach(() => { window.location.hash = ''; vi.restoreAllMocks(); });

describe('PMS direct booking-history entry', () => {
  it('does not let a late operational bootstrap replace already-loaded full history', async () => {
    const rooms = deferred();
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.startsWith('/pms/rooms?') ? rooms.promise : original(url));
    mount();
    await waitFor(() => expect(axios.get.mock.calls.some(([url]) => url.includes('full_history=true'))).toBe(true));
    await act(async () => rooms.resolve({ data: [] }));
    expect(await screen.findByTestId('list')).toHaveTextContent('full-1,full-2');
    expect(screen.getByTestId('count')).toHaveTextContent('2');
    expect(screen.getByTestId('list')).not.toHaveTextContent('narrow');
  });

  it('refreshes full history rather than shrinking the reservation list to the business-date window', async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId('list')).toHaveTextContent('full-1,full-2'));
    const original = axios.get.getMockImplementation();
    axios.get.mockImplementation(url => url.includes('full_history=true') ? Promise.resolve({ data: [row('new-full')] }) : original(url));
    fireEvent.click(screen.getByRole('button', { name: /Yenile/ }));
    await waitFor(() => expect(screen.getByTestId('list')).toHaveTextContent('new-full'));
    expect(screen.getByTestId('list')).not.toHaveTextContent('narrow');
    expect(screen.getByTestId('count')).toHaveTextContent('1');
  });
});
