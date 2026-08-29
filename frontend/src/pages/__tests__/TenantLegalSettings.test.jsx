import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

import { canEditTenantLegalSettings } from '@/pages/MevzuatRaporlari';
import SettingsHotelTab from '@/pages/settings/SettingsHotelTab';
import { Tabs } from '@/components/ui/tabs';

const baseProps = {
  editMode: true,
  setEditMode: vi.fn(),
  setHotelForm: vi.fn(),
  tenant: {},
  handleSaveHotelInfo: vi.fn(),
  hotelSaving: false,
  overRoomLimit: false,
  parseInt,
  currentPlan: { label: 'Professional', maxRooms: 80 },
  subscription: { status: 'active', rooms_count: 17, users_count: 1 },
};

describe('tenant legal settings', () => {
  it('allows the hotel admin role without requiring super admin', () => {
    expect(canEditTenantLegalSettings({ role: 'admin' })).toBe(true);
    expect(canEditTenantLegalSettings({ role: 'front_desk' })).toBe(false);
  });

  it('renders the regulatory fields in hotel settings', () => {
    render(<Tabs defaultValue="hotel">
        <SettingsHotelTab
          {...baseProps}
          hotelForm={{
            property_name: 'The Canyon Kartepe',
            tax_number: '1234567890',
            license_number: 'TGA-2026-001',
            license_expires_at: '2027-08-29',
            star_rating: 4,
          }}
        />
      </Tabs>);

    expect(screen.getByText('Yasal ve Resmî Bilgiler')).toBeInTheDocument();
    expect(screen.getByLabelText('VKN / TCKN')).toHaveValue('1234567890');
    expect(screen.getByLabelText('İşletme Belgesi Numarası')).toHaveValue('TGA-2026-001');
    expect(screen.getByLabelText('Belge Son Geçerlilik Tarihi')).toHaveValue('2027-08-29');
    expect(screen.getByText('4 yıldız')).toBeInTheDocument();
  });

  it('keeps only numeric VKN/TCKN input', () => {
    const setHotelForm = vi.fn();
    render(<Tabs defaultValue="hotel">
        <SettingsHotelTab
          {...baseProps}
          setHotelForm={setHotelForm}
          hotelForm={{ tax_number: '' }}
        />
      </Tabs>);

    fireEvent.change(screen.getByLabelText('VKN / TCKN'), { target: { value: '12A34-567890' } });
    expect(setHotelForm).toHaveBeenCalledWith(expect.objectContaining({ tax_number: '1234567890' }));
  });
});
