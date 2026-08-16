import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet, axiosPost, toast } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPost: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('axios', () => ({
  default: { get: axiosGet, post: axiosPost },
}));

vi.mock('sonner', () => ({ toast }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
}));

vi.mock('@/components/MaybeLayout', () => ({
  default: ({ children }) => <>{children}</>,
}));

import GuestRelationsDashboard from '@/pages/GuestRelationsDashboard';

const directive = {
  id: 'directive-1',
  guest_name: 'Test Misafir',
  room_id: 'room-1',
  check_in: '2026-08-20T12:00:00Z',
  pillow_preference: 'Ortopedik',
  minibar_preference: 'Standart',
  spa_preference: 'Aroma',
};

describe('guest relations directive contract', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
    toast.error.mockReset();
    toast.success.mockReset();
  });

  afterEach(() => cleanup());

  it('renders canonical backend directive fields', async () => {
    axiosGet.mockResolvedValue({ data: { directives: [directive] } });

    render(<GuestRelationsDashboard embedded />);

    expect(await screen.findByText('Test Misafir')).toBeInTheDocument();
    expect(screen.getByText('Yastık: Ortopedik · Minibar: Standart · SPA: Aroma')).toBeInTheDocument();
    expect(screen.getByText(/Check-in:/)).toBeInTheDocument();
    expect(screen.getByText('Bekliyor')).toBeInTheDocument();
  });

  it('reports directives_generated after triggering preparations', async () => {
    axiosGet.mockResolvedValue({ data: { directives: [] } });
    axiosPost.mockResolvedValue({
      data: { success: true, processed_bookings: 3, directives_generated: 2 },
    });

    render(<GuestRelationsDashboard embedded />);
    fireEvent.click(await screen.findByRole('button', {
      name: "Yaklaşan Check-in'ler İçin Direktif Tetikle",
    }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      '2 adet oda hazırlık direktifi tetiklendi!',
    ));
    expect(axiosPost).toHaveBeenCalledTimes(1);
  });
});
