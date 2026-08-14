import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: vi.fn(),
    delete: vi.fn(),
  },
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

import { ChannelHealth } from '@/components/ChannelHealthDashboard';
import { TechDebtDashboard } from '@/components/TechDebtDashboard';
import { WeeklyProof } from '@/components/WeeklyProofDashboard';
import { VCCTab } from '@/pages/reservation-detail/VCCTab';

describe('loading placeholder safety', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockImplementation(() => new Promise(() => {}));
  });

  it.each([
    ['weekly proof', WeeklyProof, 'weekly-proof-loading', 6],
    ['technical debt', TechDebtDashboard, 'tech-debt-loading', 5],
    ['channel health', ChannelHealth, 'channel-health-loading', 7],
  ])('renders %s placeholders without dereferencing empty values', (_name, Component, testId, count) => {
    const { container } = render(<Component />);

    expect(screen.getByTestId(testId)).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(count);
  });

  it('renders the VCC view counter for an existing card', async () => {
    axiosGet.mockResolvedValueOnce({
      data: {
        has_vcc: true,
        vcc: {
          view_count: 1,
          max_views: 3,
          locked: false,
          card_mask: '411111******1111',
        },
      },
    });

    const { container } = render(<VCCTab booking={{ id: 'booking-test' }} />);

    await waitFor(() => expect(screen.getByTestId('vcc-tab')).toBeInTheDocument());
    expect(container.querySelectorAll('.h-2.flex-1')).toHaveLength(3);
  });
});
