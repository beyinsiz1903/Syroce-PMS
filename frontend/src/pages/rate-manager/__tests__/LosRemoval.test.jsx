import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkUpdatePanel } from '@/pages/rate-manager/BulkUpdatePanel';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

const editor = (channelProvider = 'exely', agenciesOnly = false) => {
  const updateRoomValue = vi.fn();
  render(<BulkUpdatePanel
    roomTypeTree={[{ code: 'STD', name: 'Standart', plans: [] }]} roomTypes={[{ code: 'STD' }]} ratePlans={[]}
    enabledFields={new Set(['min_stay', 'min_los_arrival', 'max_stay'])} toggleField={vi.fn()}
    dateFrom="2030-01-01" dateTo="2030-01-01" allDays selectedDays={new Set()}
    selections={{ STD: new Set(['BAR']) }} roomValues={{ STD: { min_stay: '2', min_los_arrival: '', max_stay: '7' } }}
    updateRoomValue={updateRoomValue} getDefaultValues={() => ({})} applyToAllSelected={vi.fn()}
    expandedRoomTypes={new Set()} isRoomTypeSelected={() => true} isRoomTypeFullySelected={() => true}
    pricingSettings={{}} getPricingLabel={() => ''} currencySymbol="$" currency="USD"
    totalSelectedRoomTypes={1} totalSelectedPlans={1} saving={false} loading={false}
    activeChannels={[]} selectedChannelCodes={new Set()} channelProvider={channelProvider} agenciesOnly={agenciesOnly}
  />);
  return updateRoomValue;
};

describe('explicit Exely LOS removal controls', () => {
  it('offers separate removal actions and does not interpret an empty field as removal', () => {
    const update = editor();
    expect(update).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Min. konaklama kısıtını kaldır' }));
    expect(update).toHaveBeenLastCalledWith('STD', 'min_stay', '0');
    fireEvent.click(screen.getByRole('button', { name: 'Varış bazlı min. kısıtını kaldır' }));
    expect(update).toHaveBeenLastCalledWith('STD', 'min_los_arrival', '0');
    fireEvent.click(screen.getByRole('button', { name: 'Max. konaklama kısıtını kaldır' }));
    expect(update).toHaveBeenLastCalledWith('STD', 'max_stay', '0');
    expect(screen.getByTestId('max-stay-input-STD')).toHaveAttribute('min', '0');
  });

  it.each([['hotelrunner', false], ['exely', true]])('does not offer removal for %s / agency-only=%s', (provider, agenciesOnly) => {
    editor(provider, agenciesOnly);
    expect(screen.queryByRole('button', { name: /kısıtını kaldır/ })).not.toBeInTheDocument();
    expect(screen.getByTestId('max-stay-input-STD')).toHaveAttribute('min', '1');
  });
});
