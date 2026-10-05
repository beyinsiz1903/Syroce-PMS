import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { NotesTab } from '@/pages/reservation-detail/GuestServiceTabs';

afterEach(() => cleanup());

describe('reservation notes provider projection', () => {
  it('shows HotelRunner agency notes inside the existing Notes tab', () => {
    render(
      <NotesTab
        booking={{ id: 'booking-a' }}
        notes={[
          {
            id: 'note-a',
            note_type: 'general',
            source: 'hotelrunner',
            created_by: 'HotelRunner / Acente',
            created_at: '2026-08-30T14:00:00Z',
            content: 'Late arrival requested by Expedia',
          },
        ]}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByTestId('notes-tab')).toBeInTheDocument();
    expect(screen.getByText('Late arrival requested by Expedia')).toBeInTheDocument();
    expect(screen.getByText('HotelRunner / Acente')).toBeInTheDocument();
    expect(screen.getByText('- HotelRunner / Acente')).toBeInTheDocument();
  });
});
