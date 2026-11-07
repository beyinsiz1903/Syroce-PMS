import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CommandCenter from '@/components/CommandCenter';
import FrontdeskTab from '@/components/pms/FrontdeskTab';
import { Tabs } from '@/components/ui/tabs';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, options) => options?.defaultValue || key }) }));

const LocationProbe = () => {
  const location = useLocation();
  const navigate = useNavigate();
  return <>
    <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
    <button onClick={() => navigate('/app/pms?frontdesk_view=departures#frontdesk')}>Open departures</button>
  </>;
};
const Board = () => <Tabs defaultValue="frontdesk"><FrontdeskTab
  arrivals={[]} departures={[]} inhouse={[]} bookings={[]} rooms={[]} guests={[]}
  loading={false} tenant={{ currency: 'TRY' }} businessDate="2026-10-26"
/></Tabs>;
const mount = (url = '/app/dashboard') => render(<MemoryRouter initialEntries={[url]}>
  <LocationProbe />
  <Routes>
    <Route path="/app/dashboard" element={<CommandCenter />} />
    <Route path="/app/pms" element={<Board />} />
    <Route path="/housekeeping" element={<div>Housekeeping workspace</div>} />
    <Route path="*" element={<div>Wrong workspace</div>} />
  </Routes>
</MemoryRouter>);

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue({ data: { summary: {}, alerts: [
    { type: 'departures_with_balance', action: 'frontdesk', severity: 'high', items: [] },
    { type: 'pending_payments', action: 'payments', severity: 'medium', items: [] },
    { type: 'vip_arrivals', action: 'frontdesk', severity: 'info', items: [] },
    { type: 'dirty_rooms_blocking', action: 'housekeeping', severity: 'high', items: [] },
  ] } });
});

describe('dashboard alert destinations and actual frontdesk selection', () => {
  it.each([
    ['departures_with_balance', 'departures'],
    ['pending_payments', 'inhouse'],
    ['vip_arrivals', 'arrivals'],
  ])('opens %s in the %s list, not the default arrivals workspace', async (type, view) => {
    mount();
    fireEvent.click(await screen.findByTestId(`cc-action-${type}`));
    expect(screen.getByTestId('location')).toHaveTextContent(`/app/pms?frontdesk_view=${view}#frontdesk`);
    expect(await screen.findByRole('tab', { name: view === 'inhouse' ? 'pms.inHouse' : `pms.${view}` })).toHaveAttribute('aria-selected', 'true');
    expect(post).not.toHaveBeenCalled();
  });

  it('retains the existing housekeeping destination', async () => {
    mount();
    fireEvent.click(await screen.findByTestId('cc-action-dirty_rooms_blocking'));
    expect(await screen.findByText('Housekeeping workspace')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('restores a direct departure link when mounting or refreshing the frontdesk', () => {
    mount('/app/pms?frontdesk_view=departures#frontdesk');
    expect(screen.getByRole('tab', { name: 'pms.departures' })).toHaveAttribute('aria-selected', 'true');
  });

  it('updates the selected list on same-workspace navigation', async () => {
    mount('/app/pms?frontdesk_view=inhouse#frontdesk');
    expect(screen.getByRole('tab', { name: 'pms.inHouse' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Open departures' }));
    await waitFor(() => expect(screen.getByRole('tab', { name: 'pms.departures' })).toHaveAttribute('aria-selected', 'true'));
  });

  it('allows manual tab changes while preserving the workspace hash and unrelated query', async () => {
    mount('/app/pms?keep=1&frontdesk_view=departures#frontdesk');
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'pms.arrivals' }), { button: 0, ctrlKey: false });
    await waitFor(() => expect(screen.getByRole('tab', { name: 'pms.arrivals' })).toHaveAttribute('aria-selected', 'true'));
    expect(screen.getByTestId('location')).toHaveTextContent('/app/pms?keep=1&frontdesk_view=arrivals#frontdesk');
    expect(post).not.toHaveBeenCalled();
  });

  it.each(['', '?frontdesk_view=unsupported', '?frontdesk_view=https%3A%2F%2Fexample.invalid'])('falls back safely to arrivals for %s', search => {
    mount(`/app/pms${search}#frontdesk`);
    expect(screen.getByRole('tab', { name: 'pms.arrivals' })).toHaveAttribute('aria-selected', 'true');
  });
});
