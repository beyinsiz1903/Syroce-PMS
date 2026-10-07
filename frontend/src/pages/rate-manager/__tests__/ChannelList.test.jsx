import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { ChannelList } from '../ChannelList';

describe('ChannelList', () => {
  it('renders only provider-verified active channels as explicit targets', () => {
    const onToggle = vi.fn();
    const onToggleAll = vi.fn();
    render(<ChannelList provider="hotelrunner" channels={[
      { code: 'bookingcom', name: 'Booking.com', status: 'active' },
      { code: 'expedia', name: 'Expedia', status: 'active' },
    ]} selectedChannelCodes={new Set()} onToggle={onToggle} onToggleAll={onToggleAll} />);

    expect(screen.getByTestId('active-channel-summary')).toHaveTextContent("HotelRunner'da etkin (2)");
    expect(screen.getByText('Booking.com')).toBeInTheDocument();
    expect(screen.getByText('Expedia')).toBeInTheDocument();
    expect(screen.queryByText('HRS')).not.toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')).toHaveLength(3);
    fireEvent.click(screen.getByTestId('channel-checkbox-bookingcom'));
    expect(onToggle).toHaveBeenCalledWith('bookingcom');
    fireEvent.click(screen.getByTestId('channel-select-all'));
    expect(onToggleAll).toHaveBeenCalledTimes(1);
  });

  it('shows stale state instead of a fabricated catalogue', () => {
    render(<ChannelList provider="hotelrunner" channels={[]} stale />);

    expect(screen.getByTestId('rate-manager-channels-stale')).toHaveTextContent('kanal gönderimi kapatıldı');
    expect(screen.getByTestId('rate-manager-no-active-channels')).toBeInTheDocument();
    expect(screen.queryByText('Booking.com')).not.toBeInTheDocument();
  });
});
