import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Dashboard from '@/pages/Dashboard';

vi.mock('axios', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: {} })) },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }),
}));

vi.mock('@/context/CurrencyContext', () => ({
  useCurrency: () => ({ format: (value) => String(value), symbol: '₺' }),
}));

vi.mock('@/components/PmsLiteOnboarding', () => ({
  default: () => null,
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.hash}</output>;
}

describe('DashboardLite quick actions', () => {
  it('uses client-side navigation instead of a full page reload', () => {
    render(
      <MemoryRouter initialEntries={['/app/dashboard']}>
        <Dashboard user={{ name: 'Test', tenant_id: 'tenant-1' }} tenant={{ id: 'tenant-1', subscription_plan: 'pms_lite' }} />
        <LocationProbe />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.openCalendar' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/app/reservation-calendar');
  });
});
