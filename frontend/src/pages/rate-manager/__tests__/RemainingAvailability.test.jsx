import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkUpdatePanel } from '@/pages/rate-manager/BulkUpdatePanel';
import { buildRateUpdateReview, isValidExelyAvailability } from '@/pages/rate-manager/updateReview';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

const editor = (channelProvider = 'exely', agenciesOnly = false) => {
  const update = vi.fn();
  render(<BulkUpdatePanel
    roomTypeTree={[{ code: 'STD', name: 'Standart', plans: [{ code: 'BASE', name: 'Base' }] }]}
    roomTypes={[{ code: 'STD' }]} ratePlans={[{ code: 'BASE' }]}
    enabledFields={new Set(['availability'])} toggleField={vi.fn()}
    dateFrom="2026-11-10" dateTo="2026-11-12" allDays selectedDays={new Set()}
    selections={{ STD: new Set(['BASE']) }} roomValues={{ STD: { availability: 0 } }}
    updateRoomValue={update} getDefaultValues={() => ({})} applyToAllSelected={vi.fn()}
    expandedRoomTypes={new Set(['STD'])} isRoomTypeSelected={() => true} isRoomTypeFullySelected={() => true}
    isRatePlanSelected={() => true} pricingSettings={{ STD: 'per_room' }} getPricingLabel={() => ''}
    currencySymbol="$" currency="USD" totalSelectedRoomTypes={1} totalSelectedPlans={1}
    saving={false} loading={false} activeChannels={[]} selectedChannelCodes={new Set()}
    channelProvider={channelProvider} agenciesOnly={agenciesOnly}
  />);
  return update;
};

describe('Exely remaining-room editor', () => {
  it('labels the exact net value, explains no second deduction, and preserves zero in plan preview', () => {
    const update = editor();
    expect(screen.getByTestId('remaining-availability-help')).toHaveTextContent('doluluktan bağımsız manuel satış kontenjanı');
    expect(screen.getByTestId('remaining-availability-help')).toHaveTextContent('overbooking');
    const input = screen.getByRole('spinbutton', { name: 'Net müsait oda — Standart' });
    expect(input).toHaveValue(0);
    expect(input).toHaveAttribute('step', '1');
    expect(input).toHaveAttribute('max', '999');
    expect(input).toHaveAttribute('placeholder', 'Boş: otomatik');
    expect(screen.getByTestId('rate-plan-row-STD-BASE')).toHaveTextContent('0');
    fireEvent.change(input, { target: { value: '5' } });
    expect(update).toHaveBeenCalledWith('STD', 'availability', '5');
    fireEvent.change(input, { target: { value: '' } });
    expect(update).toHaveBeenCalledWith('STD', 'availability', '');
  });

  it.each([['hotelrunner', false], ['exely', true]])('does not relabel the legacy %s / agency-only=%s contract', (provider, agencyOnly) => {
    editor(provider, agencyOnly);
    expect(screen.queryByTestId('remaining-availability-help')).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton', { name: 'Net müsait oda — Standart' })).not.toBeInTheDocument();
  });

  it('explains net inventory in the publish review and accepts zero', () => {
    const review = buildRateUpdateReview({ channelProvider: 'exely', enabledFields: new Set(['availability']),
      dateFrom: '2026-11-10', dateTo: '2026-11-12', allDays: true,
      selections: { STD: new Set(['BASE']) }, roomValues: { STD: { availability: '0' } } });
    expect(review.errors).toEqual([]);
    expect(review.warnings.join(' ')).toContain('Manuel satış kontenjanı 0 oda');
    expect(review.warnings.join(' ')).toContain('overbooking');
  });

  it.each(['', null, undefined])('allows %s as an explicit automatic reset without a new button', value => {
    const review = buildRateUpdateReview({ channelProvider: 'exely', enabledFields: new Set(['availability']),
      dateFrom: '2026-11-10', dateTo: '2026-11-12', allDays: true,
      selections: { STD: new Set(['BASE']) }, roomValues: { STD: { availability: value } } });
    expect(review.errors).toEqual([]);
    expect(review.warnings.join(' ')).toContain('Müsaitlik otomatik hesaba dönecek');
    expect(review.warnings.join(' ')).toContain('manuel kontenjan seçili günlerde kaldırılacak');
    expect(isValidExelyAvailability(value)).toBe(true);
  });

  it.each([-1, 1000, 1.5, ' ', 'garbage', true, false])('rejects malformed manual value %s', value => {
    expect(isValidExelyAvailability(value)).toBe(false);
    const review = buildRateUpdateReview({ channelProvider: 'exely', enabledFields: new Set(['availability']),
      dateFrom: '2026-11-10', dateTo: '2026-11-12', allDays: true,
      selections: { STD: new Set(['BASE']) }, roomValues: { STD: { availability: value } } });
    expect(review.errors).toContain('STD için müsaitliği boş bırakın veya 0–999 arasında tam sayı girin.');
  });

  it('does not allow a blank field to reset HotelRunner or agency-only inventory', () => {
    for (const scope of [{ channelProvider: 'hotelrunner' }, { channelProvider: 'exely', agenciesOnly: true }]) {
      const review = buildRateUpdateReview({ ...scope, enabledFields: new Set(['availability']),
        dateFrom: '2026-11-10', dateTo: '2026-11-12', allDays: true,
        selections: { STD: new Set(['BASE']) }, roomValues: { STD: { availability: '' } } });
      expect(review.errors).toContain('STD için müsaitlik sıfır veya pozitif tam sayı olmalıdır.');
    }
  });

  it('blocks a net publication longer than 731 nights in preview', () => {
    const review = buildRateUpdateReview({ channelProvider: 'exely', enabledFields: new Set(['availability']),
      dateFrom: '2026-11-02', dateTo: '2028-11-02', allDays: true,
      selections: { STD: new Set(['BASE']) }, roomValues: { STD: { availability: '5' } } });
    expect(review.errors).toContain('Net müsaitlik için tek gönderimde en fazla 731 gece seçin.');
  });
});
