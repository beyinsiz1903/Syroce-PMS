import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const mockEntitlements = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
  },
}));

vi.mock('@/context/EntitlementContext', () => ({
  useEntitlements: () => mockEntitlements(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import MicePage, { omitEmptySpaceBookings } from '@/pages/MicePage';

describe('MicePage event payload normalization', () => {
  it('omits the untouched convenience space row', () => {
    expect(omitEmptySpaceBookings([
      {
        space_id: '',
        starts_at: '',
        ends_at: '',
        setup_style: 'theatre',
        expected_pax: 50,
      },
    ])).toEqual([]);
  });

  it('keeps configured and partially configured rows for server validation', () => {
    const configured = {
      space_id: 'space-1',
      starts_at: '2026-08-20T10:00',
      ends_at: '2026-08-20T12:00',
    };
    const partial = { space_id: 'space-2', starts_at: '', ends_at: '' };

    expect(omitEmptySpaceBookings([configured, partial])).toEqual([configured, partial]);
  });
});

describe('MicePage entitlement usage contract', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    mockEntitlements.mockReset();
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: [],
          limits: { spaces_limit: 10, concurrent_events: 50 },
          usage: { spaces_limit: 2, concurrent_events: 3 },
        },
      },
    });
    axiosGet.mockImplementation((url) => {
      if (url === '/mice/events') {
        return Promise.resolve({ data: { events: [], summary: {}, counts: {} } });
      }
      if (url === '/mice/spaces') {
        return Promise.resolve({ data: { spaces: [] } });
      }
      if (url === '/mice/accounts') {
        return Promise.resolve({ data: { accounts: [] } });
      }
      return Promise.reject(new Error(`Unexpected GET: ${url}`));
    });
  });

  it('renders after loading quota usage from the entitlement payload', async () => {
    render(
      <MemoryRouter>
        <MicePage user={{}} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /yeni_etkinlik/ })).toBeEnabled();
    expect(axiosGet).toHaveBeenCalledWith('/mice/events');
    expect(axiosGet).toHaveBeenCalledWith('/mice/spaces');
    expect(axiosGet).toHaveBeenCalledWith('/mice/accounts');
  });

  it('keeps the new event action disabled when entitlement usage reaches the limit', async () => {
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: [],
          limits: { spaces_limit: 10, concurrent_events: 5 },
          usage: { spaces_limit: 2, concurrent_events: 5 },
        },
      },
    });

    render(
      <MemoryRouter>
        <MicePage user={{}} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /yeni_etkinlik/ })).toBeDisabled();
  });

  it('fails closed without crashing when the feature payload is malformed', async () => {
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: { banquet_operations: true },
          limits: { spaces_limit: 10, concurrent_events: 50 },
          usage: { spaces_limit: 2, concurrent_events: 3 },
        },
      },
    });

    render(
      <MemoryRouter>
        <MicePage user={{}} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /gunun_ops_sheet_i/ })).not.toBeInTheDocument();
  });
});
