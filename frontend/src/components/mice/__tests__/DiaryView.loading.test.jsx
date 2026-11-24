import { act, cleanup, render, screen } from '@testing-library/react';
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
