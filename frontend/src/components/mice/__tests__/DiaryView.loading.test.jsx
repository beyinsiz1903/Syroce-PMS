import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import DiaryView from '../DiaryView';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.includes('musait') ? 'müsait' : key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
afterEach(cleanup);
const spaces = [{ id: 'board', name: 'Boardroom' }];
const props = { spaces, spaceById: { board: spaces[0] }, revision: 1 };
const freeCells = () => screen.queryAllByRole('button', { name: /1\/1 müsait/ });

it('does not advertise free halls before the diary response is verified', async () => {
  let resolve;
  axios.get.mockReturnValue(new Promise(done => { resolve = done; }));
  render(<DiaryView {...props} />);
  expect(screen.getByRole('status')).toHaveTextContent('Salon takvimi doğrulanıyor');
  expect(freeCells()).toHaveLength(0);
  await act(async () => resolve({ data: { events: [] } }));
  expect(freeCells().length).toBeGreaterThan(0);
});

it('hides prior availability immediately while a new revision is pending', async () => {
  axios.get.mockResolvedValueOnce({ data: { events: [] } });
  const view = render(<DiaryView {...props} />);
  await act(async () => {});
  expect(freeCells().length).toBeGreaterThan(0);
  axios.get.mockReturnValue(new Promise(() => {}));
  view.rerender(<DiaryView {...props} revision={2} />);
  expect(freeCells()).toHaveLength(0);
  expect(screen.getByRole('status')).toHaveTextContent('doğrulanıyor');
});

it('does not reinterpret a malformed response as an empty free calendar', async () => {
  axios.get.mockResolvedValue({ data: {} });
  render(<DiaryView {...props} />);
  await act(async () => {});
  expect(freeCells()).toHaveLength(0);
  expect(screen.queryByText('Salon takvimi doğrulanıyor…')).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'uiQuality.states.error.title' })).toBeInTheDocument();
});

it.each([false, true])('excludes inactive halls from availability while retaining their history (active booked: %s)', async activeBooked => {
  const now = new Date();
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-10`;
  const venues = [...spaces, { id: 'closed', name: 'Retired hall', active: false }];
  const reservations = [{ space_id: 'closed', starts_at: `${day}T10:00:00`, ends_at: `${day}T11:00:00` }];
  if (activeBooked) reservations.push({ ...reservations[0], space_id: 'board' });
  axios.get.mockResolvedValue({ data: { events: [{ id: 'historical', name: 'Preserved event', status: 'completed',
    start_date: day, end_date: day, space_bookings: reservations }] } });
  render(<DiaryView spaces={venues} spaceById={Object.fromEntries(venues.map(s => [s.id, s]))} revision={1} />);
  await act(async () => {});
  const cell = screen.getByRole('button', { name: new RegExp(`^10 1 ${activeBooked ? 0 : 1}/1 müsait$`) });
  fireEvent.click(cell);
  expect(screen.getAllByText('Preserved event').length).toBeGreaterThan(0);
  expect(screen.queryAllByRole('button', { name: /\/2 müsait/ })).toHaveLength(0);
});
