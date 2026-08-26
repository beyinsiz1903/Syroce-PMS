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
    fireEvent.click(screen.getByRole('button', { name: /0–6 ücretsiz/ }));
    fireEvent.click(screen.getByTestId('hotelrunner-pricing-attestation-STD'));
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      base_occupancy: 2,
      extra_adult_rate: 1500,
      child_free_age_max: 6,
      child_age_bands: [
        { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
        { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
        { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
      ],
      provider_pricing_verified: true,
    }));
  });
});
