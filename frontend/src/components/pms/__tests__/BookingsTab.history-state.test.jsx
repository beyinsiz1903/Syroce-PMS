import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import BookingsTab from '../BookingsTab';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/components/ui/tabs', () => ({ TabsContent: ({ children }) => <div>{children}</div> }));
vi.mock('@/components/VirtualizedBookingList', () => ({ default: ({ bookings }) => <div data-testid="saved-list">{bookings.map(row => row.id).join(',')}</div> }));
const renderList = props => render(<MemoryRouter><BookingsTab bookings={[{ id: 'saved', status: 'confirmed', room_id: null }]} {...props} /></MemoryRouter>);

describe('full-history loading and retry presentation', () => {
  it('marks refreshing counts as provisional without removing the saved list', () => {
    renderList({ historyLoading: true });
    expect(screen.getByRole('status')).toHaveTextContent('sayılar henüz nihai değil');
    expect(screen.getByTestId('saved-list')).toHaveTextContent('saved');
  });

  it('exposes history failure and a working retry action', () => {
    const retryHistory = vi.fn();
    renderList({ historyError: 'Liste eksik olabilir.', retryHistory });
    expect(screen.getByRole('alert')).toHaveTextContent('Liste eksik olabilir.');
    fireEvent.click(screen.getByRole('button', { name: 'Tam listeyi yeniden yükle' }));
    expect(retryHistory).toHaveBeenCalledOnce();
    expect(screen.getByTestId('saved-list')).toHaveTextContent('saved');
  });

  it('disables duplicate retries while history is loading', () => {
    renderList({ historyLoading: true, historyError: 'Liste eksik olabilir.', retryHistory: vi.fn() });
    expect(screen.getByRole('button', { name: 'Tam listeyi yeniden yükle' })).toBeDisabled();
  });
});
