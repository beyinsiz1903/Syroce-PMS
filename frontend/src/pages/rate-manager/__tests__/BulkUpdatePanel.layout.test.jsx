import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkUpdatePanel } from '../BulkUpdatePanel';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

const fields = ['rate', 'availability', 'min_stay', 'min_los_arrival', 'max_stay', 'cta', 'ctd', 'stop_sell'];
const renderPanel = (enabled = fields) => {
  const update = vi.fn(), apply = vi.fn();
  const Panel = () => {
    const [values, setValues] = useState({ STD: { rate: '100', availability: 0, min_stay: '0', min_los_arrival: '2', max_stay: '7', cta: false, ctd: true, stop_sell: false } });
    return <BulkUpdatePanel roomTypeTree={[{ code: 'STD', name: 'Standart', plans: [{ code: 'BASE', name: 'Base' }] }]}
    roomTypes={[{ code: 'STD', name: 'Standart' }]} ratePlans={[{ code: 'BASE', name: 'Base' }]}
    enabledFields={new Set(enabled)} toggleField={vi.fn()} selections={{ STD: new Set(['BASE']), DLX: new Set(['BASE']) }}
    roomValues={values}
    updateRoomValue={(code, key, value) => {
      update(code, key, value);
      setValues(previous => ({ ...previous, [code]: { ...previous[code], [key]: value } }));
    }} applyToAllSelected={apply} getDefaultValues={() => ({})}
    expandedRoomTypes={new Set(['STD'])} isRoomTypeSelected={() => true} isRoomTypeFullySelected={() => true} isRatePlanSelected={() => true}
    toggleRoomType={vi.fn()} toggleAllRoomTypes={vi.fn()} toggleRatePlan={vi.fn()} pricingSettings={{ STD: 'per_room' }}
    occupancyPricingRules={{ STD: { base_occupancy: 2 } }} getPricingLabel={() => 'Oda bazlı'} togglePricingType={vi.fn()}
    totalSelectedRoomTypes={2} totalSelectedPlans={1} selectedDays={new Set()} allDays dateFrom="2026-11-07" dateTo="2026-11-08"
    currency="USD" currencySymbol="$" channelProvider="exely" activeChannels={[]} selectedChannelCodes={new Set()} />;
  };
  render(<Panel />);
  return { update, apply };
};

describe('wrapping room field editor', () => {
  it.each([['rate'], ['rate', 'availability'], ['rate', 'availability', 'min_stay'], fields].map(enabled => [enabled]))('keeps %j inside a self-wrapping labelled field grid', enabled => {
    renderPanel(enabled);
    expect(screen.getByTestId('room-type-list').className).not.toContain('overflow-x');
    expect(screen.getByTestId('room-field-grid-STD').style.gridTemplateColumns).toContain('auto-fit');
    expect(screen.getByTestId('bulk-update-layout')).toHaveAttribute('data-layout', enabled.length >= 2 ? 'expanded' : 'standard');
    const group = screen.getByRole('group', { name: 'Standart güncellenecek alanlar' });
    expect(group.querySelectorAll('[data-testid^="room-field-"]')).toHaveLength(enabled.length);
  });

  it.each([
    ['rate-input', 'rate', '85'], ['avail-input', 'availability', '0'], ['min-stay-input', 'min_stay', '0'],
    ['min-los-arrival-input', 'min_los_arrival', '3'], ['max-stay-input', 'max_stay', '10'],
  ])('preserves the %s callback and string input contract', (prefix, key, value) => {
    const { update } = renderPanel();
    fireEvent.change(screen.getByTestId(`${prefix}-STD`), { target: { value: '' } });
    fireEvent.change(screen.getByTestId(`${prefix}-STD`), { target: { value } });
    expect(update).toHaveBeenCalledWith('STD', key, value);
  });

  it('preserves true and false toggles, apply-all, and zero in plan summaries', () => {
    const { update, apply } = renderPanel();
    fireEvent.click(screen.getByTestId('cta-STD'));
    expect(update).toHaveBeenLastCalledWith('STD', 'cta', true);
    fireEvent.click(screen.getByTestId('ctd-STD'));
    expect(update).toHaveBeenLastCalledWith('STD', 'ctd', false);
    fireEvent.click(screen.getByTestId('stop-sell-STD'));
    expect(update).toHaveBeenLastCalledWith('STD', 'stop_sell', true);
    fireEvent.click(within(screen.getByTestId('room-type-row-STD')).getByTestId('apply-all-rate'));
    expect(apply).toHaveBeenCalledWith('rate', '100');
    expect(screen.getByTestId('rate-plan-row-STD-BASE')).toHaveTextContent('Net müsait oda: 0');
    expect(screen.getByTestId('rate-plan-row-STD-BASE')).toHaveTextContent('Min. konaklama: 0');
  });
});
