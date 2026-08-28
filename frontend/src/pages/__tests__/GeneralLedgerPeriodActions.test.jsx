import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { MemoryRouter } from 'react-router-dom';

import GeneralLedgerModule, { GL_ENDPOINTS } from '@/pages/GeneralLedgerModule';

const renderModule = () => render(<MemoryRouter><GeneralLedgerModule /></MemoryRouter>);

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const period = (periodNo, status = 'open') => ({
  id: `tenant-A:2026:${periodNo}`,
  name: `2026-${String(periodNo).padStart(2, '0')}`,
  fiscal_year: 2026,
  period_no: periodNo,
  start_date: `2026-${String(periodNo).padStart(2, '0')}-01`,
  end_date: `2026-${String(periodNo).padStart(2, '0')}-28`,
  status,
});

describe('GeneralLedgerModule period action dialogs', () => {
  let periods;

  beforeEach(() => {
    vi.clearAllMocks();
    periods = [period(1)];
    axios.get.mockImplementation((url) => {
      if (url === GL_ENDPOINTS.accounts) return Promise.resolve({ data: { accounts: [] } });
      if (url === GL_ENDPOINTS.trialBalance) return Promise.resolve({ data: { rows: [], totals: { balanced: true } } });
      if (url === GL_ENDPOINTS.periods) return Promise.resolve({ data: { periods } });
      if (url === `${GL_ENDPOINTS.yearEnd}/2026`) return Promise.resolve({ data: { closed: false } });
      return Promise.resolve({ data: {} });
    });
    axios.post.mockResolvedValue({ data: {} });
  });

  it('collects a period-close reason in an application dialog before posting', async () => {
    const user = userEvent.setup();
    const legacyPrompt = vi.spyOn(window, 'prompt');
    renderModule();

    await user.click(screen.getByRole('tab', { name: 'Mali Dönemler' }));
    await user.click(await screen.findByRole('button', { name: 'Dönemi Kapat' }));

    expect(screen.getByTestId('gl-period-action-dialog')).toBeInTheDocument();
    expect(legacyPrompt).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Gerekçe'), { target: { value: 'Test dönem kapanışı' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kapat ve Onayla' }));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      `${GL_ENDPOINTS.periods}/tenant-A:2026:1/close`,
      { reason: 'Test dönem kapanışı' },
    ));
    legacyPrompt.mockRestore();
  });

  it('collects the year-end reason before creating the closing and carry-forward entries', async () => {
    const user = userEvent.setup();
    periods = Array.from({ length: 12 }, (_, index) => period(index + 1, index < 11 ? 'closed' : 'open'));
    axios.post.mockResolvedValue({ data: { closure: { closing_entry_no: 'YEV-2026-CLOSE' } } });
    renderModule();

    await user.click(screen.getByRole('tab', { name: 'Mali Dönemler' }));
    await user.click(await screen.findByRole('button', { name: 'Yıl Sonunu Kapat ve Devret' }));
    fireEvent.change(screen.getByLabelText('Gerekçe'), { target: { value: 'Test yıl sonu kapanışı' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kapat ve Onayla' }));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(GL_ENDPOINTS.closeYear, {
      fiscal_year: 2026,
      reason: 'Test yıl sonu kapanışı',
    }));
  });
});
