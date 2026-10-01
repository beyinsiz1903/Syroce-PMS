import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Tabs } from '@/components/ui/tabs';
import SettingsRoomsTab from '../SettingsRoomsTab';

describe('SettingsRoomsTab', () => {
  it('shows room view and operational status in Turkish', () => {
    render(
      <MemoryRouter>
        <Tabs value="rooms">
          <SettingsRoomsTab
            loadRooms={vi.fn()}
            roomsLoading={false}
            setShowBulkRoomsDialog={vi.fn()}
            setShowAddRoomDialog={vi.fn()}
            roomsList={[{
              id: 'room-101',
              room_number: '101',
              room_type: 'Standard',
              floor: 1,
              capacity: 2,
              view: 'city',
              bed_type: 'twin',
              status: 'dirty',
            }]}
            handleDeleteRoom={vi.fn()}
            onEditRoom={vi.fn()}
          />
        </Tabs>
      </MemoryRouter>,
    );

    expect(screen.getByText('Şehir · Twin / İki Tek Kişilik Yatak')).toBeInTheDocument();
    expect(screen.getByText('Kirli')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '101 numaralı odayı düzenle' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '101 numaralı odayı sil' })).toBeInTheDocument();
  });
});
