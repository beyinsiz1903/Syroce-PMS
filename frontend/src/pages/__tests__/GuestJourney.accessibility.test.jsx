import { fireEvent, render, screen } from '@testing-library/react';
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
});
