import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkUpdatePanel } from '@/pages/rate-manager/BulkUpdatePanel';
import { buildRateUpdateReview } from '@/pages/rate-manager/updateReview';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').at(-1) }) }));

const plans = ['BASE', 'NRF', 'DYNAMIC'].map(code => ({ code, name: code }));
const input = {
  dateFrom: '2026-11-05', dateTo: '2028-11-01', allDays: true,
  selectedDays: new Set([0, 1, 2, 3, 4, 5, 6]), channelProvider: 'exely',
  selections: { STD: new Set(['BASE', 'NRF', 'DYNAMIC']), DLX: new Set(['BASE', 'NRF', 'DYNAMIC']) },
  enabledFields: new Set(['rate']), roomValues: { STD: { rate: '100' }, DLX: { rate: '110' } }, ratePlans: plans,
  occupancyPricingRules: { STD: { base_occupancy: 2 }, DLX: { base_occupancy: 3 } },
};

describe('Exely single-request price review', () => {
  it('blocks the screenshot selection without advising retries, splitting, or relaxing the quota', () => {
    const review = buildRateUpdateReview(input);
    expect(review.dateCount).toBe(728);
    expect(review.cellCount).toBe(4368);
    expect(review.errors).toHaveLength(2);
    expect(review.errors[0]).toContain('728 gece × 3 fiyat planı = 2184');
    expect(review.errors[0]).toContain('1460');
    expect(review.warnings.join(' ')).toContain('tek fiyat XML isteğinde');
  });

  it('keeps both rooms and the complete selected period when two explicitly chosen plans fit', () => {
    const review = buildRateUpdateReview({ ...input, selections: { STD: new Set(['BASE', 'NRF']), DLX: new Set(['BASE', 'NRF']) } });
    expect(review.errors).toEqual([]);
    expect(review).toMatchObject({ dateCount: 728, planCount: 4, cellCount: 2912 });
  });

  it('counts only selected weekdays and keeps multiple rooms separate for quota purposes', () => {
    const review = buildRateUpdateReview({ ...input, allDays: false, selectedDays: new Set([1]) });
    expect(review.dateCount).toBe(104);
    expect(review.errors).toEqual([]);
  });

  it('does not infer derivation from plan names or omit forbidden plans silently', () => {
    expect(buildRateUpdateReview({ ...input, dateTo: '2026-11-06' }).errors).toEqual([]);
    const review = buildRateUpdateReview({ ...input, dateTo: '2026-11-06',
      ratePlans: plans.map(plan => ({ ...plan, price_upload_is_allowed: plan.code !== 'DYNAMIC' })) });
    expect(review.errors).toHaveLength(2);
    expect(review.errors[0]).toContain('doğrudan fiyat yüklemesi kapalı');
    expect(review.planCount).toBe(6); // the choice has not been silently changed
  });

  it.each([{ channelProvider: 'hotelrunner' }, { agenciesOnly: true }])('does not apply Exely limits outside Exely delivery: %j', scope => {
    expect(buildRateUpdateReview({ ...input, ...scope }).errors).toEqual([]);
  });

  it('does not multiply category-wide availability by every tariff', () => {
    expect(buildRateUpdateReview({ ...input, enabledFields: new Set(['availability']),
      roomValues: { STD: { availability: 3 }, DLX: { availability: 3 } } }).errors).toEqual([]);
  });

  it('also preflights the combined restriction envelope', () => {
    const review = buildRateUpdateReview({ ...input, enabledFields: new Set(['cta', 'ctd']) });
    expect(review.errors.join(' ')).toContain('4368');
  });
});

describe('Exely price plan selection on the existing editor', () => {
  const panel = (overrides = {}) => render(<BulkUpdatePanel
    {...input}
    roomTypeTree={[{ code: 'STD', name: 'Standart', plans }]}
    roomTypes={[{ code: 'STD', name: 'Standart' }]}
    toggleField={vi.fn()} setDateFrom={vi.fn()} setDateTo={vi.fn()} toggleDay={vi.fn()} toggleAllDays={vi.fn()}
    toggleRoomType={vi.fn()} toggleAllRoomTypes={vi.fn()} toggleRatePlan={vi.fn()}
    isRoomTypeSelected={() => true} isRoomTypeFullySelected={() => true}
    isRatePlanSelected={(_room, plan) => input.selections.STD.has(plan)}
    updateRoomValue={vi.fn()} getDefaultValues={() => ({})} applyToAllSelected={vi.fn()}
    expandedRoomTypes={new Set()} toggleExpanded={vi.fn()} pricingSettings={{ STD: 'per_room' }}
    getPricingLabel={() => 'Oda bazlı'} togglePricingType={vi.fn()} currencySymbol="$" currency="USD"
    totalSelectedRoomTypes={2} totalSelectedPlans={6} saving={false} loading={false}
    handleBulkUpdate={vi.fn()} handleReset={vi.fn()} activeChannels={[]} activeChannelsStale={false}
    selectedChannelCodes={new Set()} toggleChannel={vi.fn()} toggleAllChannels={vi.fn()}
    {...overrides}
  />);

  it('shows selected price plans without requiring a hidden expand action and disables an oversized publish', () => {
    panel();
    expect(screen.getByTestId('rate-plan-check-STD-BASE')).toBeInTheDocument();
    expect(screen.getByTestId('rate-plan-check-STD-DYNAMIC')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    expect(screen.getByTestId('rate-confirm-publish')).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('2184');
  });

  it('allows clearing a selected forbidden plan and prevents selecting it again', () => {
    const toggle = vi.fn();
    const tagged = plans.map(plan => ({ ...plan, price_upload_is_allowed: plan.code !== 'DYNAMIC' }));
    panel({ ratePlans: tagged, roomTypeTree: [{ code: 'STD', name: 'Standart', plans: tagged }], toggleRatePlan: toggle });
    const forbidden = screen.getByTestId('rate-plan-check-STD-DYNAMIC');
    expect(forbidden).toBeEnabled();
    fireEvent.click(forbidden);
    expect(toggle).toHaveBeenCalledWith('STD', 'DYNAMIC');
    expect(screen.getByText('Exely doğrudan fiyat yüklemesi kapalı')).toBeInTheDocument();
  });
});
