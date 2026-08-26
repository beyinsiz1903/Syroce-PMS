import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { BulkUpdatePanel } from '@/pages/rate-manager/BulkUpdatePanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key.split('.').at(-1) }),
}));

function WizardHarness({ onUpdate = vi.fn(), onReset = vi.fn() }) {
  const [mobileStep, setMobileStep] = useState(1);
  const [enabledFields, setEnabledFields] = useState(new Set());
  const toggleField = (field) => setEnabledFields((current) => {
    const next = new Set(current);
    if (next.has(field)) next.delete(field); else next.add(field);
    return next;
  });

  return (
    <BulkUpdatePanel
      roomTypeTree={[]}
      roomTypes={[]}
      ratePlans={[]}
      enabledFields={enabledFields}
      toggleField={toggleField}
      dateFrom="2026-08-26"
      setDateFrom={vi.fn()}
      dateTo="2026-09-02"
      setDateTo={vi.fn()}
      allDays
      selectedDays={new Set([0, 1, 2, 3, 4, 5, 6])}
      toggleDay={vi.fn()}
      toggleAllDays={vi.fn()}
      selections={{ STD: ['BAR'] }}
      toggleRoomType={vi.fn()}
      toggleAllRoomTypes={vi.fn()}
      toggleRatePlan={vi.fn()}
      isRoomTypeSelected={() => false}
      isRoomTypeFullySelected={() => false}
      isRatePlanSelected={() => false}
      roomValues={{}}
      updateRoomValue={vi.fn()}
      getDefaultValues={() => ({})}
      applyToAllSelected={vi.fn()}
      expandedRoomTypes={new Set()}
      toggleExpanded={vi.fn()}
      pricingSettings={{}}
      getPricingLabel={() => ''}
      togglePricingType={vi.fn()}
      currencySymbol="₺"
      currency="TRY"
      totalSelectedRoomTypes={1}
      totalSelectedPlans={1}
      saving={false}
      handleBulkUpdate={onUpdate}
      handleReset={onReset}
      loading={false}
      activeChannels={[]}
      activeChannelsStale={false}
      channelProvider="hotelrunner"
      mobileStep={mobileStep}
      setMobileStep={setMobileStep}
    />
  );
}

describe('BulkUpdatePanel mobile wizard', () => {
  it('guides the mobile update through fields, rooms, and confirmation', () => {
    const onUpdate = vi.fn();
    render(<WizardHarness onUpdate={onUpdate} />);

    expect(screen.getByTestId('rate-mobile-step-1')).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('rate-mobile-next')).toBeDisabled();

    fireEvent.click(screen.getByTestId('field-rate'));
    expect(screen.getByTestId('rate-mobile-next')).toBeEnabled();
    fireEvent.click(screen.getByTestId('rate-mobile-next'));
    expect(screen.getByTestId('rate-mobile-step-2')).toHaveAttribute('aria-current', 'step');

    fireEvent.click(screen.getByTestId('rate-mobile-next'));
    expect(screen.getByTestId('rate-mobile-step-3')).toHaveAttribute('aria-current', 'step');
    fireEvent.click(screen.getByTestId('rate-mobile-update'));
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });
});
