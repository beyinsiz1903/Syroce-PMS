import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import FolioDetailView, { isSupportedFolioId } from '@/pages/FolioDetailView';

const { get, axiosMock } = vi.hoisted(() => {
  const get = vi.fn();
  return {
    get,
    axiosMock: { get },
  };
});

vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

describe('FolioDetailView identifier contract', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation(() => new Promise(() => {}));
  });

  afterEach(() => cleanup());

  it('accepts both persisted folio identifier formats', () => {
    expect(isSupportedFolioId('507f1f77bcf86cd799439011')).toBe(true);
    expect(isSupportedFolioId('cb6d687f-7011-43f6-8dd6-570c36fc8936')).toBe(true);
    expect(isSupportedFolioId('not-a-folio-id')).toBe(false);
  });

  it('loads a UUID folio instead of rejecting it in the browser', async () => {
    const folioId = 'cb6d687f-7011-43f6-8dd6-570c36fc8936';

    render(
      <MemoryRouter>
        <FolioDetailView folioId={folioId} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(get).toHaveBeenCalledWith(
      `/pms-core/folio/detail/${folioId}`,
      { headers: {} },
    ));
    expect(screen.queryByTestId('folio-not-found')).not.toBeInTheDocument();
  });

  it('still rejects malformed folio identifiers without a backend request', async () => {
    render(
      <MemoryRouter>
        <FolioDetailView folioId="not-a-folio-id" />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('folio-not-found')).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});
