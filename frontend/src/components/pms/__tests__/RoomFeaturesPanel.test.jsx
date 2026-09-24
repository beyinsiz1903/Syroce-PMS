import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosPost = vi.fn();

vi.mock('axios', () => ({
  default: {
    patch: vi.fn(),
    post: (...args) => axiosPost(...args),
  },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('@/lib/currency', () => ({
  cachedTenantCurrency: () => 'TRY',
  formatCurrency: (value) => `${Number(value).toFixed(2)} TRY`,
}));

import RoomFeaturesPanel from '@/components/pms/RoomFeaturesPanel';

describe('RoomFeaturesPanel', () => {
  beforeEach(() => {
    axiosPost.mockReset();
    axiosPost.mockResolvedValue({ data: { success: true } });
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('posts minibar consumption through the canonical frontdesk charge endpoint', async () => {
    render(<RoomFeaturesPanel room={{ id: 'room-1', room_number: '101', booking_id: 'booking-1' }} />);

    fireEvent.click(screen.getByRole('button', { name: /Minibar Girişi/i }));
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /Su \(500ml\)/i }));
    fireEvent.click(screen.getAllByRole('button').find((button) => button.querySelector('svg.lucide-plus')));
    fireEvent.click(screen.getByRole('button', { name: /folyoya_ekle/i }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/frontdesk/v2/post-charge', {
      booking_id: 'booking-1',
      charge_type: 'minibar',
      description: 'Minibar - 1x Su (500ml)',
      amount: 5,
      charge_category: 'minibar',
    }));
  });
});
