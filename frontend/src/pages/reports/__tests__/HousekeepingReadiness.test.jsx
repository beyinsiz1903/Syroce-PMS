import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { HousekeepingSection, RoomStatusSection } from '../OperationsSection';
afterEach(cleanup);
it('does not advertise a clean occupied room as available for sale in housekeeping', () => {
  render(<HousekeepingSection reportDate="2026-11-12" hk={{ rows: [{ id: 'hk101', room_number: '101', room_status: 'available', status: 'pending' }, { id: 'hk104', room_number: '104', room_status: 'dirty', status: 'pending' }] }} />);
  expect(screen.getByRole('columnheader', { name: 'Güncel Temizlik / Bakım Durumu' })).toBeInTheDocument();
  const rows = screen.getAllByRole('row');
  expect(within(rows[1]).getByText('Temiz / hazır')).toBeInTheDocument();
  expect(within(rows[2]).getByText('Kirli')).toBeInTheDocument();
  expect(screen.queryByText('Müsait')).not.toBeInTheDocument();
  expect(screen.getByText(/satış müsaitliği veya doluluk göstermez/)).toBeInTheDocument();
});
it('retains the separate live room availability vocabulary', () => {
  render(<RoomStatusSection roomStatus={{ available: 3, occupied: 6 }} roomStatusData={[]} />);
  expect(screen.getByText('Müsait')).toBeInTheDocument();
  expect(screen.getByText('Dolu')).toBeInTheDocument();
});
