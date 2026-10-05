import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import WBESettings from '../WBESettings';

describe('WBESettings', () => {
  it('builds the public reservation URL from the active hotel instead of a demo tenant', () => {
    render(<WBESettings tenant={{ id: 'hotel-42', property_name: 'Kanyon Otel', modules: { booking_engine: true } }} />);

    expect(screen.getByDisplayValue(`${window.location.origin}/wbe/hotel-42`)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Canlı sayfayı aç/ })).toHaveAttribute('href', `${window.location.origin}/wbe/hotel-42`);
    expect(screen.queryByDisplayValue(/demo-hotel-123/)).not.toBeInTheDocument();
  });

  it('does not publish a link when hotel context is missing', () => {
    render(<WBESettings tenant={{ modules: { booking_engine: true } }} />);

    expect(screen.getByText(/Otel kimliği oturumdan alınamadığı için/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Kurulum tamamlanınca açılacak/ })).toBeDisabled();
  });
});
