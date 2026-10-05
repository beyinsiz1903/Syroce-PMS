import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet } = vi.hoisted(() => ({ axiosGet: vi.fn() }));

vi.mock('axios', () => ({ default: { get: axiosGet } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback || _key }) }));

import GuestJourney from '@/pages/GuestJourney';

describe('GuestJourney accessibility', () => {
  beforeEach(() => {
    axiosGet.mockImplementation((url) => {
      if (url.startsWith('/nps/score')) return Promise.resolve({ data: { nps_score: 50, total_responses: 1, promoters: 1, passives: 0, detractors: 0 } });
      if (url.startsWith('/nps/recent')) return Promise.resolve({ data: { items: [] } });
      return Promise.resolve({ data: { rooms: [] } });
    });
  });

  it('offers named report and category filter controls to keyboard users', async () => {
    render(<MemoryRouter><GuestJourney /></MemoryRouter>);

    expect(await screen.findByRole('combobox', { name: 'NPS rapor dönemi' })).toBeInTheDocument();
    const promoterFilter = screen.getByRole('button', { name: 'Destekçi (9-10) yorumlarını filtrele' });
    fireEvent.keyDown(promoterFilter, { key: 'Enter' });
    expect(promoterFilter).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the newest filter result when an earlier request resolves last', async () => {
    const pending = [];
    axiosGet.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));
    render(<MemoryRouter><GuestJourney /></MemoryRouter>);

    await waitFor(() => expect(pending).toHaveLength(3));
    fireEvent.click(screen.getByTestId('cat-card-promoter'));
    await waitFor(() => expect(pending).toHaveLength(6));

    await act(async () => {
      pending[3]({ data: { nps_score: 100, total_responses: 1, promoters: 1, passives: 0, detractors: 0 } });
      pending[4]({ data: { items: [{ id: 'newest', nps_score: 10, category: 'promoter' }] } });
      pending[5]({ data: { rooms: [] } });
    });
    expect(await screen.findByTestId('feedback-newest')).toBeInTheDocument();

    await act(async () => {
      pending[0]({ data: { nps_score: -100, total_responses: 1, promoters: 0, passives: 0, detractors: 1 } });
      pending[1]({ data: { items: [{ id: 'stale', nps_score: 0, category: 'detractor' }] } });
      pending[2]({ data: { rooms: [] } });
    });
    expect(screen.getByTestId('feedback-newest')).toBeInTheDocument();
    expect(screen.queryByTestId('feedback-stale')).not.toBeInTheDocument();
  });
});
