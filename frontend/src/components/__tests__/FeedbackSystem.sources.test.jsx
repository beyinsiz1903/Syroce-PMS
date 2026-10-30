import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
import FeedbackSystem from '@/components/FeedbackSystem';

beforeEach(() => { get.mockReset(); post.mockReset(); });
afterEach(cleanup);

it('shows a partial-source warning rather than treating a failed read as empty', async () => {
  get.mockImplementation(path => path === '/feedback/external-reviews'
    ? Promise.reject(new Error('offline'))
    : Promise.resolve({ data: { reviews: [], surveys: [], feedback: [] } }));
  render(<FeedbackSystem />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Dış Platform');
  fireEvent.click(screen.getByTestId('btn-feedback-refresh'));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(8));
});

it('loads responses beyond the first ten surveys and distinguishes missing response sources', async () => {
  get.mockImplementation(path => {
    if (path === '/feedback/surveys') return Promise.resolve({ data: { surveys: Array.from({ length: 11 }, (_, i) => ({ id: `s${i}`, survey_name: `Survey ${i}` })) } });
    if (path === '/feedback/surveys/s0/responses') return Promise.reject(new Error('offline'));
    if (path === '/feedback/surveys/s10/responses') return Promise.resolve({ data: { responses: [{ id: 'r11', guest_name: 'Eleventh survey guest', overall_rating: 4, responses: [] }] } });
    return Promise.resolve({ data: { reviews: [], responses: [], feedback: [] } });
  });
  render(<FeedbackSystem />);
  expect(await screen.findByText('Eleventh survey guest')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('Survey 0');
});
