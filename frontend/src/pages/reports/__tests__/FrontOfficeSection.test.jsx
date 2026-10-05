import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import FrontOfficeSection, { reservationCount } from '../FrontOfficeSection';

describe('FrontOfficeSection', () => {
  it('counts reservations once while still showing the number of guest rows', () => {
    const arrivals = [
      { id: 'g1', booking_id: 'b1', guest_name: 'Ana misafir', room_number: '101' },
      { id: 'g2', booking_id: 'b1', guest_name: 'Ek misafir', room_number: '101' },
      { id: 'g3', booking_id: 'b2', guest_name: 'Diğer misafir', room_number: '102' },
    ];

    expect(reservationCount(arrivals)).toBe(2);
    render(<FrontOfficeSection
      s={{ total_rooms: 10, occupied_rooms: 2, in_house: 3 }}
      todayArrivals={arrivals}
      todayDepartures={[]}
      reportDate="2026-09-30"
      exchangeRates={{}}
    />);

    expect(screen.getByText('Girişler (2 rezervasyon · 3 misafir)')).toBeInTheDocument();
    expect(screen.getByText('Ana misafir')).toBeInTheDocument();
    expect(screen.getByText('Ek misafir')).toBeInTheDocument();
  });
});
