import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    await waitFor(() => expect(screen.getByTestId('save-occupancy-rule-STD')).toBeEnabled());
  });
});

describe('occupancy rule currency', () => {
  const editor = (rule, currency) => render(<OccupancyPricingEditor
    roomType={{ code: 'Standard', name: 'Standard' }} open={false} onToggle={vi.fn()} rule={rule}
    onSave={vi.fn()} currentBaseRate={4000} currencySymbol="₺" currency={currency} channelProvider="exely"
  />);

  it('warns when fixed supplements were entered in another currency', () => {
    editor({ pricing_type: 'per_person', base_occupancy: 2, extra_adult_rate: 20, currency: 'USD' }, 'TRY');
    expect(screen.getByTestId('occupancy-currency-warning-Standard')).toHaveTextContent('USD girilmiş');
  });

  it('stays quiet for currency-neutral rules', () => {
    editor({ pricing_type: 'per_person', base_occupancy: 2, extra_adult_rate_type: 'percentage', extra_adult_rate: 50, currency: 'USD' }, 'TRY');
    expect(screen.queryByTestId('occupancy-currency-warning-Standard')).not.toBeInTheDocument();
  });
});

describe('Exely child policy attestation', () => {
  const editor = (onSave, verified = false) => render(<OccupancyPricingEditor
    roomType={{ code: 'STD', name: 'Standart' }} open onToggle={vi.fn()}
    rule={{ pricing_type: 'per_person', base_occupancy: 2, extra_adult_rate: 1000, child_free_age_max: 6, provider_pricing_verified: verified }}
    onSave={onSave} currentBaseRate={5000} currencySymbol="₺" currency="TRY" channelProvider="exely"
  />);

  it('does not claim to send child age bands and requires explicit operator confirmation', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    editor(onSave);
    expect(screen.getByText(/Çocuk yaş kademeleri bu işlemle kanal yöneticisine gönderilmez/)).toBeInTheDocument();
    const attestation = screen.getByTestId('exely-pricing-attestation-STD');
    expect(attestation).not.toBeChecked();
    fireEvent.click(attestation);
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ provider_pricing_verified: true }));
    await waitFor(() => expect(screen.getByTestId('save-occupancy-rule-STD')).toBeEnabled());
  });

  it('clears the previous provider confirmation when a child policy changes', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    editor(onSave, true);
    expect(screen.getByTestId('exely-pricing-attestation-STD')).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: /0–6 ücretsiz/ }));
    expect(screen.getByTestId('exely-pricing-attestation-STD')).not.toBeChecked();
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ provider_pricing_verified: false }));
    await waitFor(() => expect(screen.getByTestId('save-occupancy-rule-STD')).toBeEnabled());
  });
});
