import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MoveReasonDialog } from '../CalendarDialogs';

const moveData = {
  booking: { guest_name: 'Test Misafir' },
  oldRoom: '208',
  newRoom: '102',
  oldCheckIn: '2026-08-22',
  newCheckIn: '2026-08-24',
  oldCheckOut: '2026-08-25',
  newCheckOut: '2026-08-27',
  requiresReason: false,
};

describe('reservation move confirmation', () => {
  it('shows the old and new room and dates before an ordinary move', () => {
    const onConfirmMove = vi.fn();
    render(<MoveReasonDialog
      open
      onOpenChange={vi.fn()}
      moveData={moveData}
      moveReason=""
      setMoveReason={vi.fn()}
      onConfirmMove={onConfirmMove}
    />);

    expect(screen.getByTestId('booking-move-summary')).toHaveTextContent('208');
    expect(screen.getByTestId('booking-move-summary')).toHaveTextContent('102');
    expect(screen.getByTestId('booking-move-summary')).toHaveTextContent('2026-08-22');
    expect(screen.getByTestId('booking-move-summary')).toHaveTextContent('2026-08-27');
    expect(screen.queryByLabelText('Oda değişikliği nedeni')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Taşımayı Onayla' }));
    expect(onConfirmMove).toHaveBeenCalledOnce();
  });

  it('asks for a reason when the destination room type changes', () => {
    render(<MoveReasonDialog
      open
      onOpenChange={vi.fn()}
      moveData={{ ...moveData, requiresReason: true }}
      moveReason=""
      setMoveReason={vi.fn()}
      onConfirmMove={vi.fn()}
    />);
    expect(screen.getByLabelText('Oda değişikliği nedeni')).toBeInTheDocument();
  });
});
