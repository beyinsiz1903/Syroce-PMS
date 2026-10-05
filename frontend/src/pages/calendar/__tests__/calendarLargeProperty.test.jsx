import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CalendarGrid, {
  CALENDAR_ROW_OVERSCAN,
  getVirtualRoomWindow,
  LARGE_PROPERTY_ROOM_THRESHOLD,
} from '../CalendarGrid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const dates = [9, 10, 11].map((day) => new Date(`2026-09-${String(day).padStart(2, '0')}T00:00:00Z`));

const renderLargeGrid = (overrides = {}) => {
  const rooms = Array.from({ length: LARGE_PROPERTY_ROOM_THRESHOLD }, (_, index) => ({
    id: `room-${index + 1}`,
    room_number: String(100 + index),
    room_type: 'standard',
    status: 'available',
    base_price: 100,
  }));
  const onPerformanceSample = vi.fn();

  render(
    <CalendarGrid
      rooms={rooms}
      bookings={[]}
      roomBlocks={[]}
      dateRange={dates}
      daysToShow={dates.length}
      currentDate={dates[0]}
      businessDate="2026-09-10"
      conflicts={[]}
      draggingBooking={null}
      resizingBooking={null}
      showDeluxePanel={false}
      groupColorMap={{}}
      setGroupColorMap={vi.fn()}
      groupBookings={[]}
      getOccupancyForDate={() => 0}
      onCellClick={vi.fn()}
      onDragStart={vi.fn()}
      onResizeStart={vi.fn()}
      onResizePointerStart={vi.fn()}
      onResizePointerCommit={vi.fn()}
      onDragOver={vi.fn()}
      onDragLeave={vi.fn()}
      onDrop={vi.fn()}
      onDragEnd={vi.fn()}
      onBookingClick={vi.fn()}
      onBookingDoubleClick={vi.fn()}
      onPerformanceSample={onPerformanceSample}
      {...overrides}
    />,
  );
  return onPerformanceSample;
};

describe('CalendarGrid large-property mode', () => {
  it('keeps smaller properties fully rendered', () => {
    expect(getVirtualRoomWindow({
      roomCount: LARGE_PROPERTY_ROOM_THRESHOLD - 1,
      offset: 0,
      scrollTop: 0,
      viewportHeight: 100,
      enabled: false,
    })).toEqual({ start: 0, end: LARGE_PROPERTY_ROOM_THRESHOLD - 1 });
  });

  it('renders an overscanned window rather than every room for a large property', () => {
    const window = getVirtualRoomWindow({
      roomCount: 200,
      offset: 0,
      scrollTop: 64 * 50,
      viewportHeight: 64 * 5,
      enabled: true,
    });

    expect(window.start).toBe(50 - CALENDAR_ROW_OVERSCAN);
    expect(window.end).toBe(55 + CALENDAR_ROW_OVERSCAN);
  });

  it('activates virtual rows and emits a compact performance sample at the threshold', () => {
    const onPerformanceSample = renderLargeGrid({ showPrices: false });

    expect(screen.getByTestId('calendar-grid')).toHaveAttribute('data-large-property-mode', 'virtualized');
    expect(screen.getAllByTestId('room-row').length).toBeLessThan(LARGE_PROPERTY_ROOM_THRESHOLD);
    expect(screen.getByTestId('calendar-virtual-bottom-spacer')).toBeInTheDocument();
    expect(onPerformanceSample).toHaveBeenCalledWith(expect.objectContaining({
      roomCount: LARGE_PROPERTY_ROOM_THRESHOLD,
      virtualized: true,
      renderedRoomRows: expect.any(Number),
      renderMs: expect.any(Number),
    }));
    expect(screen.queryByText('₺100')).not.toBeInTheDocument();
  });
});
