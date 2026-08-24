import { render, screen } from '@testing-library/react';
import { ChannelList } from '../ChannelList';

describe('ChannelList', () => {
  it('renders only provider-verified active channels passed by the backend', () => {
    render(<ChannelList provider="hotelrunner" channels={[
      { code: 'bookingcom', name: 'Booking.com', status: 'active' },
      { code: 'expedia', name: 'Expedia', status: 'active' },
    ]} />);

    expect(screen.getByTestId('active-channel-summary')).toHaveTextContent("HotelRunner'da etkin (2)");
    expect(screen.getByText('Booking.com')).toBeInTheDocument();
    expect(screen.getByText('Expedia')).toBeInTheDocument();
    expect(screen.queryByText('HRS')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('shows stale state instead of a fabricated catalogue', () => {
    render(<ChannelList provider="hotelrunner" channels={[]} stale />);

    expect(screen.getByTestId('rate-manager-channels-stale')).toHaveTextContent('Aktif kanal listesi yenilenemedi');
    expect(screen.queryByText('Booking.com')).not.toBeInTheDocument();
  });
});
