import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OccupancyPricingEditor } from '@/pages/rate-manager/BulkUpdatePanel';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

describe('HotelRunner occupancy pricing verification', () => {
  it('requires an explicit provider-side rule attestation and persists it', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<OccupancyPricingEditor
      roomType={{ code: 'STD', name: 'Standart' }}
      open
      onToggle={vi.fn()}
      rule={{ base_occupancy: 2, extra_adult_rate: 1500, extra_child_rate: 750, child_free_age_max: 6, provider_pricing_verified: false }}
      onSave={onSave}
      currentBaseRate={5000}
      currencySymbol="₺"
      channelProvider="hotelrunner"
    />);

    expect(screen.getByText(/HotelRunner'a taban fiyat gönderilir/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('hotelrunner-pricing-attestation-STD'));
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      base_occupancy: 2,
      extra_adult_rate: 1500,
      child_free_age_max: 6,
      provider_pricing_verified: true,
    }));
  });
});
