import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CalendarGrid from '../CalendarGrid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const dates = [10, 11, 12, 13].map((day) => new Date(`2026-09-${day}T00:00:00Z`));
const room = { id: 'room-1', room_number: '101', room_type: 'standard', status: 'available' };
const booking = {
  id: 'booking-1',
  room_id: room.id,
  guest_name: 'Test Misafir',
  status: 'confirmed',
  check_in: '2026-09-10',
  check_out: '2026-09-12',
  adults: 1,
};

const renderGrid = (overrides = {}) => {
  const handlers = {
    onCellClick: vi.fn(),
    onDragStart: vi.fn(),
    onResizeStart: vi.fn(),
    onDragOver: vi.fn(),
    onDragLeave: vi.fn(),
    onDrop: vi.fn(),
    onDragEnd: vi.fn(),
    onBookingDoubleClick: vi.fn(),
  };
  render(
    <CalendarGrid
      rooms={[room]}
      bookings={[booking]}
      roomBlocks={[]}
      dateRange={dates}
      daysToShow={dates.length}
      currentDate={dates[0]}
      businessDate="2026-09-10"
      conflicts={[]}
      draggingBooking={null}
      resizingBooking={null}
      dragOverCell={null}
      showDeluxePanel={false}
      groupColorMap={{}}
      setGroupColorMap={vi.fn()}
      groupBookings={[]}
      getOccupancyForDate={() => 0}
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
};

describe('CalendarGrid stay resize handle', () => {
  it('starts resize without starting the whole-booking move gesture', () => {
    const handlers = renderGrid();
    const handle = screen.getByTestId('booking-resize-handle-booking-1');
    const dataTransfer = { effectAllowed: '', setData: vi.fn() };

    fireEvent.dragStart(handle, { dataTransfer });

    expect(handlers.onResizeStart).toHaveBeenCalledWith(expect.anything(), booking);
    expect(handlers.onDragStart).not.toHaveBeenCalled();
  });

  it('does not offer resizing for a completed stay', () => {
    renderGrid({ bookings: [{ ...booking, status: 'checked_out' }] });
    expect(screen.queryByTestId('booking-resize-handle-booking-1')).not.toBeInTheDocument();
  });

  it('lets covered calendar cells receive the drop while resizing', () => {
    renderGrid({ resizingBooking: booking });
    expect(screen.getByTestId('booking-bar-booking-1')).toHaveClass('pointer-events-none');
  });
});
