import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import CalendarHeader from '@/pages/calendar/CalendarHeader';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key.split('.').at(-1) }),
}));

const defaultProps = {
  dateRange: [new Date('2026-08-26T00:00:00'), new Date('2026-09-08T00:00:00')],
  daysToShow: 14,
  setDaysToShow: vi.fn(),
  bookings: [],
  conflicts: [],
  syncing: false,
  onNavigatePrevious: vi.fn(),
  onNavigateNext: vi.fn(),
  onGoToDate: vi.fn(),
  onSyncReservations: vi.fn(),
  onShowFindRoomDialog: vi.fn(),
  onShowNewBookingDialog: vi.fn(),
  onShowUnassigned: vi.fn(),
  onShowConflicts: vi.fn(),
  viewPreferences: { compactMode: true, showOccupancy: true, showTimeline: false },
  onViewPreferenceChange: vi.fn(),
};

describe('CalendarHeader mobile toolbar', () => {
  it('keeps primary controls compact and moves secondary actions into one menu', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><CalendarHeader {...defaultProps} /></MemoryRouter>);

    expect(screen.getByTestId('mobile-calendar-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-calendar-nav-prev')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-calendar-nav-today')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-calendar-nav-next')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-add-reservation-button')).toBeInTheDocument();

    await user.click(screen.getByTestId('mobile-calendar-actions'));
    expect(screen.getByRole('menu')).toHaveTextContent('Takvim işlemleri');
    expect(screen.getByRole('menu')).toHaveTextContent('OTA senkronizasyonu');
    expect(screen.getByRole('menu')).toHaveTextContent('Gün aralığı');
  });

  it('wires the compact date navigation to calendar callbacks', () => {
    const onPrevious = vi.fn();
    const onNext = vi.fn();
    const onGoToDate = vi.fn();
    render(
      <MemoryRouter>
        <CalendarHeader {...defaultProps} onNavigatePrevious={onPrevious} onNavigateNext={onNext} onGoToDate={onGoToDate} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('mobile-calendar-nav-prev'));
    fireEvent.click(screen.getByTestId('mobile-calendar-nav-today'));
    fireEvent.click(screen.getByTestId('mobile-calendar-nav-next'));

    expect(onPrevious).toHaveBeenCalledTimes(1);
    expect(onGoToDate).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});
