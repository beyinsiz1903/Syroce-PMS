import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import GuestAlertModal from '@/components/GuestAlertModal';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('@/api/axios', () => ({
  default: { get },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

describe('GuestAlertModal nested layering', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({
      data: {
        alerts: [],
        blacklisted: false,
        total_stays: 0,
      },
    });
  });

  afterEach(() => cleanup());

  it('renders its overlay and content above the reservation detail layer', async () => {
    render(
      <div className="fixed inset-0 z-[60]" data-testid="parent-reservation-modal">
        <GuestAlertModal
          guestId="guest-a"
          open
          onClose={() => {}}
          onConfirm={() => {}}
        />
      </div>,
    );

    const modal = await screen.findByTestId('guest-alert-modal');
    await waitFor(() => expect(get).toHaveBeenCalledOnce());

    expect(modal).toHaveClass('z-[80]');
    expect(
      Array.from(document.body.querySelectorAll('*')).some((element) =>
        element.classList.contains('z-[70]'),
      ),
    ).toBe(true);
  });
});
