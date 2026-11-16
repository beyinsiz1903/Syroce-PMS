import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import ReservationChanges from '@/components/ReservationChanges';
afterEach(cleanup);
describe('provider reservation change summary', () => {
  it('renders old/new values with a bounded bell preview', () => {
    render(<ReservationChanges recorded changes={[
      { label: 'Giriş tarihi', from: '2026-11-23', to: '2026-11-24' },
      { label: 'Ön ödeme', from: '0 USD', to: '160 USD' },
    ]} limit={1} />);
    expect(screen.getByText(/2026-11-23 → 2026-11-24/)).toBeInTheDocument();
    expect(screen.getByText(/\+1 değişiklik/)).toBeInTheDocument();
    expect(screen.queryByText('160 USD')).not.toBeInTheDocument();
  });
  it('distinguishes historical missing logs from no tracked changes', () => {
    const { rerender } = render(<ReservationChanges />);
    expect(screen.getByText(/eski bildirimde/)).toBeInTheDocument();
    rerender(<ReservationChanges recorded />);
    expect(screen.getByText(/alanlarında değişiklik yok/)).toBeInTheDocument();
  });
});
