import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkUpdatePanel } from '@/pages/rate-manager/BulkUpdatePanel';
import { buildRateUpdateReview } from '@/pages/rate-manager/updateReview';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

const input = {
  dateFrom: '2030-01-01', dateTo: '2030-01-02', allDays: true, channelProvider: 'exely',
  selections: { STD: new Set(['BASE']) }, enabledFields: new Set(['rate']), roomValues: { STD: { rate: '100' } },
};

describe('explicit Exely price occupancy', () => {
  it('never invents single/double occupancy or takes an unsaved normalization default', () => {
    for (const rule of [undefined, {}, { base_occupancy: 2, base_occupancy_explicit: false },
      { base_occupancy: 2, policy_invalid: true }, { base_occupancy: '2' }]) {
      expect(buildRateUpdateReview({ ...input, occupancyPricingRules: { STD: rule } }).errors.join(' ')).toContain('yetişkin sayısını kaydedin');
    }
  });

  it.each([1, 2, 3])('reviews the nightly room total for %i adults, not a per-adult charge', count => {
    const review = buildRateUpdateReview({ ...input, occupancyPricingRules: { STD: { base_occupancy: count } } });
    expect(review.errors).toEqual([]);
    expect(review.warnings.join(' ')).toContain(`100 — ${count} yetişkin için oda/gece toplam fiyatı`);
    expect(review.warnings.join(' ')).toContain(`NumberOfGuests=${count}`);
  });

  it('does not apply this Exely-only requirement to agency, HotelRunner, or availability updates', () => {
    for (const scope of [{ agenciesOnly: true }, { channelProvider: 'hotelrunner' },
      { enabledFields: new Set(['availability']), roomValues: { STD: { availability: 3 } } }]) {
      expect(buildRateUpdateReview({ ...input, ...scope }).errors).toEqual([]);
    }
  });

  it('shows the saved occupancy and existing rule editor even for per-room pricing', () => {
    render(<BulkUpdatePanel {...input} ratePlans={[{ code: 'BASE', name: 'Base' }]}
      roomTypeTree={[{ code: 'STD', name: 'Standart', plans: [{ code: 'BASE', name: 'Base' }] }]}
      roomTypes={[{ code: 'STD', name: 'Standart' }]}
      toggleRoomType={vi.fn()} toggleAllRoomTypes={vi.fn()} toggleRatePlan={vi.fn()}
      isRoomTypeSelected={() => true} isRoomTypeFullySelected={() => true} isRatePlanSelected={() => true}
      getDefaultValues={() => ({})} updateRoomValue={vi.fn()} applyToAllSelected={vi.fn()}
      expandedRoomTypes={new Set()} pricingSettings={{ STD: 'per_room' }} occupancyPricingRules={{ STD: { base_occupancy: 3 } }}
      getPricingLabel={() => 'Oda bazlı'} togglePricingType={vi.fn()} currencySymbol="$" currency="USD"
      totalSelectedRoomTypes={1} totalSelectedPlans={1} selectedChannelCodes={new Set()} activeChannels={[]}
      toggleAllDays={vi.fn()} selectedDays={new Set()} />);
    expect(screen.getByTestId('exely-price-occupancy-STD')).toHaveTextContent('3 yetişkin için oda/gece toplamı');
    fireEvent.click(screen.getByText('Kuralı düzenle'));
    expect(screen.getByText('Fiyata dahil yetişkin')).toBeInTheDocument();
  });
});
