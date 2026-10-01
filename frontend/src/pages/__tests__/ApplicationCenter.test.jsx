import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApplicationCenter from '../ApplicationCenter';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({ hasModule: (key) => key === 'pms' }) }));

describe('ApplicationCenter', () => {
  beforeEach(() => { navigate.mockClear(); localStorage.clear(); });

  it('shows authorized modules and launches the real workspace route', () => {
    render(<ApplicationCenter tenant={{ property_name: 'Denizli Oteli' }} />);
    expect(screen.getByText('PMS Çekirdek')).toBeInTheDocument();
    expect(screen.queryByText('İnsan Kaynakları (İK)')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('launch-pms'));
    expect(navigate).toHaveBeenCalledWith('/app/reservation-calendar');
  });

  it('stores favorites and filters to them', () => {
    render(<ApplicationCenter tenant={{ property_name: 'Denizli Oteli' }} />);
    fireEvent.click(screen.getByRole('button', { name: /PMS Çekirdek favorilere ekle/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Favoriler' }));
    expect(screen.getByText('PMS Çekirdek')).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem('syroce.application-center.favorites'))).toContain('pms');
  });
});
