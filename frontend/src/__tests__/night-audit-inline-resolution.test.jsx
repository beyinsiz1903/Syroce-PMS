import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import PreparationTab from '@/components/night-audit/tabs/PreparationTab';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key, fallback) => fallback || _key }),
}));
vi.mock('@/pages/ReservationDetailModal', () => ({
  default: ({ bookingId, onClose, onOperationComplete }) => (
    <div data-testid="inline-reservation-detail">
      <span>{bookingId}</span>
      <button type="button" onClick={onClose}>Kapat</button>
      <button
        type="button"
        onClick={() => onOperationComplete?.({ bookingId, operation: 'completed' })}
      >
        İşlemi tamamla
      </button>
    </div>
  ),
}));

const readyPreview = {
  status: 'ready',
  business_date: '2026-08-24',
  blockers: [],
  warnings: [],
  summary: {
    total_rooms: 10,
    occupied_rooms: 1,
    available_rooms: 9,
    dirty_rooms: 0,
    arrivals_today: 1,
    departures_today: 0,
    inhouse_guests: 1,
  },
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>;
}

function renderTab(preview) {
  get.mockResolvedValueOnce({ data: preview }).mockResolvedValue({ data: readyPreview });
  return render(
    <MemoryRouter initialEntries={['/night-audit']}>
      <LocationProbe />
      <PreparationTab onPreviewLoaded={vi.fn()} />
    </MemoryRouter>,
  );
}

describe('Night Audit inline blocker resolution', () => {
  beforeEach(() => get.mockReset());
  afterEach(() => cleanup());

  it.each([
    ['checkin_or_no_show', 'Check-in / no-show'],
    ['checkout_or_extend', 'Check-out / uzatma'],
  ])('opens %s inside Night Audit without navigating away', async (action, label) => {
    renderTab({
      ...readyPreview,
      status: 'blocked',
      blockers: [{
        category: action,
        count: 1,
        label: 'İşlem bekleyen rezervasyon',
        message: 'Night Audit öncesinde çözülmeli.',
        action,
        items: [{ id: 'booking-123', guest_name: 'Test Misafir', room_no: '201' }],
      }],
    });

    fireEvent.click(await screen.findByTestId(`blocker-${action}`));
    fireEvent.click(await screen.findByRole('button', { name: label }));

    expect(await screen.findByTestId('inline-reservation-detail')).toHaveTextContent('booking-123');
    expect(screen.getByTestId('location')).toHaveTextContent('/night-audit');

    fireEvent.click(screen.getByRole('button', { name: 'İşlemi tamamla' }));
    await waitFor(() => expect(screen.queryByTestId('inline-reservation-detail')).not.toBeInTheDocument());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('location')).toHaveTextContent('/night-audit');
  });
});
