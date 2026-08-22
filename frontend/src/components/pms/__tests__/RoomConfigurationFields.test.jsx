import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  normalizeRoomConfiguration,
  RoomTypeInput,
  roomToConfiguration,
  validateRoomConfiguration,
} from '@/components/pms/RoomConfigurationFields';

describe('RoomConfigurationFields', () => {
  it('accepts a manually entered custom room type', () => {
    const onChange = vi.fn();
    render(<RoomTypeInput value="" onChange={onChange} suggestions={['Deluxe']} testId="custom-room-type" />);

    fireEvent.change(screen.getByTestId('custom-room-type'), { target: { value: 'Ağaç Ev' } });

    expect(onChange).toHaveBeenCalledWith('Ağaç Ev');
    expect(screen.getByText('Listede yoksa oda tipini doğrudan yazabilirsiniz.')).toBeInTheDocument();
  });

  it('normalizes the 207 twin-room edit payload', () => {
    expect(normalizeRoomConfiguration({
      room_number: ' 207 ',
      room_type: ' Ağaç Ev ',
      floor: '2',
      capacity: '2',
      base_price: '3250.50',
      view: ' Orman ',
      bed_type: 'twin',
    })).toEqual({
      room_number: '207',
      room_type: 'Ağaç Ev',
      floor: 2,
      capacity: 2,
      base_price: 3250.5,
      view: 'Orman',
      bed_type: 'twin',
    });
  });

  it('prepares existing room values for editing and validates capacity', () => {
    const form = roomToConfiguration({
      room_number: '207',
      room_type: 'standard',
      floor: 2,
      capacity: 2,
      base_price: 150,
      bed_type: 'king',
    });

    expect(form.room_number).toBe('207');
    expect(form.bed_type).toBe('king');
    expect(validateRoomConfiguration({ ...form, capacity: 0 })).toBe('Kapasite en az 1 olmalıdır');
  });
});
