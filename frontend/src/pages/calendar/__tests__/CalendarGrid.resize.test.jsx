import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CalendarGrid, { getReservationCardPresentation, getReservationCardSurface } from '../CalendarGrid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const dates = [9, 10, 11, 12, 13].map((day) => new Date(`2026-09-${String(day).padStart(2, '0')}T00:00:00Z`));
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
    onResizePointerStart: vi.fn(),
    onResizePointerCommit: vi.fn(),
    onDragOver: vi.fn(),
    onDragLeave: vi.fn(),
    onDrop: vi.fn(),
    onDragEnd: vi.fn(),
    onBookingClick: vi.fn(),
    onBookingDoubleClick: vi.fn(),
    onBookingIntent: vi.fn(),
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
  it('builds a clear, localized reservation card summary', () => {
    expect(getReservationCardPresentation({
      ...booking,
      status: 'checked_in',
      adults: 2,
      children: 1,
      source: 'booking_com',
    })).toMatchObject({
      guestName: 'Test Misafir',
      paxCount: 3,
      statusLabel: 'Otelde',
    });
  });

  it('makes the exclusive checkout boundary explicit for a completed stay', () => {
    const presentation = getReservationCardPresentation({ ...booking, status: 'checked_out' });

    expect(presentation.statusLabel).toBe('Çıkış yapıldı · oda boş');
    expect(presentation.checkoutAvailability).toContain('oda yeniden satılabilir');
    expect(presentation.ariaLabel).toContain('oda yeniden satılabilir');
  });

  it('uses distinct but readable surfaces for each reservation lifecycle state', () => {
    expect(getReservationCardSurface({ status: 'confirmed' })).toMatchObject({
      background: 'var(--calendar-arrival-bg, #eff6ff)',
      border: '#3b82f6',
    });
    expect(getReservationCardSurface({ status: 'checked_in' })).toMatchObject({
      background: 'var(--calendar-stay-bg, #ecfdf5)',
      border: '#10b981',
    });
    expect(getReservationCardSurface({ status: 'checked_out' })).toMatchObject({
      background: 'var(--calendar-departure-bg, #fff1f2)',
      border: '#f43f5e',
    });
  });

  it('shows sellable capacity and restores it on the block end date', () => {
    renderGrid({
      bookings: [],
      roomBlocks: [{ id: 'block-1', room_id: room.id, status: 'active', type: 'out_of_service', start_date: '2026-09-10', end_date: '2026-09-12' }],
    });
    expect(screen.getAllByText('0/0')).toHaveLength(2);
    expect(screen.getAllByText('0/1')).toHaveLength(3);
    expect(screen.getAllByText('1 bloklu')).toHaveLength(2);
    expect(screen.getAllByTitle('0 rezervasyon / 0 satılabilir oda · 1 bloklu · 1 toplam')).toHaveLength(2);
  });

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

  it('does not paint the checkout date when the visible range and navigation date differ', () => {
    const visibleDates = [29, 30].map((day) => new Date(`2026-09-${day}T00:00:00Z`))
      .concat([1, 2].map((day) => new Date(`2026-10-${String(day).padStart(2, '0')}T00:00:00Z`)));

    renderGrid({
      bookings: [{
        ...booking,
        status: 'checked_out',
        check_in: '2026-09-28',
        check_out: '2026-10-02',
      }],
      dateRange: visibleDates,
      daysToShow: visibleDates.length,
      // Reproduces the old navigation drift: the render starts on 29 Sep,
      // while the navigation cursor still points at 28 Sep.
      currentDate: new Date('2026-09-28T00:00:00Z'),
    });

    const card = screen.getByTestId('booking-bar-booking-1');
    // 29, 30 Sep and 1 Oct are occupied. 2 Oct is checkout, not a sold night.
    expect(card).toHaveStyle({ width: '308px' });
  });

  it('protects Turkish weekday abbreviations from browser translation', () => {
    renderGrid();
    const wednesday = screen.getByTitle('Çarşamba');
    const thursday = screen.getByTitle('Perşembe');

    expect(wednesday).toHaveTextContent('Çar');
    expect(thursday).toHaveTextContent('Per');
    expect(wednesday).toHaveAttribute('translate', 'no');
    expect(thursday).toHaveClass('notranslate');
  });

  it('lets covered calendar cells receive the drop while resizing', () => {
    renderGrid({ resizingBooking: booking });
    expect(screen.getByTestId('booking-bar-booking-1')).toHaveClass('pointer-events-none');
  });

  it('accepts a drop directly on an occupied reservation card', () => {
    const handlers = renderGrid();
    const card = screen.getByTestId('booking-bar-booking-1');
    const dataTransfer = { effectAllowed: '', dropEffect: '' };

    fireEvent.dragOver(card, { dataTransfer });
    fireEvent.drop(card, { dataTransfer });

    expect(handlers.onDrop).toHaveBeenCalledWith(expect.anything(), room.id, expect.any(Date), booking.id);
    expect(handlers.onDrop).toHaveBeenCalledTimes(1);
    expect(handlers.onDrop.mock.calls[0][2].toISOString()).toBe('2026-09-10T00:00:00.000Z');
  });

  it('opens the quick reservation panel on the first card click', () => {
    vi.useFakeTimers();
    try {
      const handlers = renderGrid();
      const card = screen.getByTestId('booking-bar-booking-1');

      fireEvent.click(card);
      expect(handlers.onBookingClick).not.toHaveBeenCalled();
      vi.advanceTimersByTime(220);

      expect(handlers.onBookingClick).toHaveBeenCalledTimes(1);
      expect(handlers.onBookingClick).toHaveBeenCalledWith(booking);
      expect(handlers.onBookingDoubleClick).not.toHaveBeenCalled();
      expect(handlers.onCellClick).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('opens the full workspace on double click without opening the side panel first', () => {
    vi.useFakeTimers();
    try {
      const handlers = renderGrid();
      const card = screen.getByTestId('booking-bar-booking-1');
      fireEvent.click(card);
      fireEvent.click(card);
      fireEvent.doubleClick(card);
      vi.advanceTimersByTime(250);

      expect(handlers.onBookingDoubleClick).toHaveBeenCalledTimes(1);
      expect(handlers.onBookingDoubleClick).toHaveBeenCalledWith(booking);
      expect(handlers.onBookingClick).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('opens on the second mouse-down even when native dblclick is suppressed by dragging', () => {
    vi.useFakeTimers();
    try {
      const handlers = renderGrid();
      const card = screen.getByTestId('booking-bar-booking-1');

      fireEvent.mouseDown(card, { button: 0, detail: 1 });
      fireEvent.mouseDown(card, { button: 0, detail: 2 });
      vi.advanceTimersByTime(250);

      expect(handlers.onBookingDoubleClick).toHaveBeenCalledTimes(1);
      expect(handlers.onBookingDoubleClick).toHaveBeenCalledWith(booking);
      expect(handlers.onBookingClick).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('warms the full reservation workspace on the first pointer intent', () => {
    const handlers = renderGrid();
    const card = screen.getByTestId('booking-bar-booking-1');

    fireEvent.mouseDown(card, { button: 0, detail: 1 });

    expect(handlers.onBookingIntent).toHaveBeenCalledTimes(1);
    expect(handlers.onBookingIntent).toHaveBeenCalledWith(booking);
    expect(handlers.onBookingDoubleClick).not.toHaveBeenCalled();
  });

  it('deduplicates the mouse-down fallback and the browser dblclick event', () => {
    vi.useFakeTimers();
    try {
      const handlers = renderGrid();
      const card = screen.getByTestId('booking-bar-booking-1');

      fireEvent.mouseDown(card, { button: 0, detail: 2 });
      fireEvent.doubleClick(card);

      expect(handlers.onBookingDoubleClick).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('provides the reservation start cell as the drag anchor for whole-stay moves', () => {
    const handlers = renderGrid();
    const card = screen.getByTestId('booking-bar-booking-1');
    const dataTransfer = { effectAllowed: '', setData: vi.fn() };

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.click(card);

    expect(handlers.onDragStart).toHaveBeenCalledWith(
      expect.anything(),
      booking,
      expect.objectContaining({ toISOString: expect.any(Function) }),
    );
    expect(handlers.onDragStart.mock.calls[0][2].toISOString()).toBe('2026-09-10T00:00:00.000Z');
    expect(handlers.onBookingClick).not.toHaveBeenCalled();
  });

  it('supports direct pointer resizing in addition to browser drag events', () => {
    const handlers = renderGrid();
    const handle = screen.getByTestId('booking-resize-handle-booking-1');
    const targetCell = screen.getByTestId('calendar-cell-101-2026-09-13');
    const originalElementFromPoint = document.elementFromPoint;
    Object.defineProperty(document, 'elementFromPoint', {
      configurable: true,
      value: vi.fn(() => targetCell),
    });

    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(screen.getByTestId('calendar-grid'), { pointerId: 1, clientX: 11, clientY: 11 });
    expect(screen.getByTestId('booking-bar-booking-1')).toHaveStyle({ width: '412px' });
    fireEvent.pointerUp(screen.getByTestId('calendar-grid'), { pointerId: 1, clientX: 11, clientY: 11 });

    expect(handlers.onResizePointerStart).toHaveBeenCalledWith(booking);
    expect(handlers.onResizePointerCommit).toHaveBeenCalledWith(booking, expect.any(Date));
    expect(handlers.onResizePointerCommit.mock.calls[0][1].toISOString()).toBe('2026-09-13T00:00:00.000Z');
    if (originalElementFromPoint) {
      Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: originalElementFromPoint });
    } else {
      delete document.elementFromPoint;
    }
  });

  it('keeps a one-night guest name readable on the reservation card', () => {
    renderGrid({
      bookings: [{
        ...booking,
        check_out: '2026-09-11',
        guest_name: 'Mustafa Oktay Dalkıran',
      }],
    });

    expect(screen.getByTestId('booking-bar-booking-1')).toHaveTextContent('Mustafa Oktay Dalkıran');
  });

  it('exposes lifecycle, source and guest count without relying on color alone', () => {
    renderGrid({
      bookings: [{ ...booking, status: 'checked_in', adults: 2, children: 1 }],
    });

    const card = screen.getByTestId('booking-bar-booking-1');
    expect(card).toHaveTextContent('Otelde');
    expect(card).toHaveTextContent('3 kişi');
    expect(card).toHaveAccessibleName(expect.stringContaining('Otelde'));
  });
});
