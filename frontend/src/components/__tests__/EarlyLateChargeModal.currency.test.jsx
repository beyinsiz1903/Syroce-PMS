import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('@/api/axios', () => ({
  default: { post },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key.endsWith('folyoya_ekle') ? 'Folyoya Ekle' : key,
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import EarlyLateChargeModal from '@/components/EarlyLateChargeModal';

describe('EarlyLateChargeModal currency contract', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('posts the calculated currency through the currency-aware extra charge endpoint', async () => {
    post
      .mockResolvedValueOnce({
        data: {
          applicable: true,
          amount: 25,
          nightly_rate: 100,
          nights: 1,
          currency: 'EUR',
          label: 'Erken Giriş — Erken',
        },
      })
      .mockResolvedValueOnce({ data: { success: true } });

    render(
      <EarlyLateChargeModal
        open
        onClose={vi.fn()}
        bookingId="booking-1"
        direction="early_checkin"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    expect(await screen.findByText(/25,00\s*€/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Folyoya Ekle' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post).toHaveBeenLastCalledWith(
      '/reservations/booking-1/add-extra-charge',
      expect.objectContaining({
        amount: 25,
        quantity: 1,
        input_currency: 'EUR',
      })
    );
  });
});
