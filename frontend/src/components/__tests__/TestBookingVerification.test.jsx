import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import TestBookingVerification from '../TestBookingVerification';
import { toast } from 'sonner';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

describe('Exely acceptance is separate from discovery', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does not turn an already imported/ACKed booking into a certified child scenario', async () => {
    axios.post.mockResolvedValue({ data: {
      verification_status: 'found', acceptance_status: 'mismatch', lookup_source: 'stored', new_count: 0,
      before_count: 1, after_count: 1, warnings: ['Kişi ayrımı doğrulanmadı'],
      new_reservations: [{ external_id: 'synthetic', guest_name: 'QA', checks: { guest_demographics: 'not_verified' } }],
    } });
    render(<TestBookingVerification />);
    fireEvent.change(screen.getByTestId('test-booking-reservation-id'), { target: { value: 'synthetic' } });
    fireEvent.change(screen.getByLabelText('Beklenen yetişkin sayısı (isteğe bağlı)'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Beklenen çocuk yaşları'), { target: { value: '6' } });
    fireEvent.click(screen.getByTestId('test-booking-verify-btn'));
    await screen.findByText('Kişi bilgileri eşleşmiyor');
    expect(axios.post).toHaveBeenCalledWith('/channel-manager/exely/test-booking/verify', {
      reservation_id: 'synthetic', expected_adults: 2, expected_children_ages: [6],
    }, { headers: {} });
    expect(screen.getByText(/Mevcut PMS kaydı/)).toBeInTheDocument();
    expect(screen.queryByText('Test Rezervasyon Doğrulandı!')).not.toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows found without claiming full acceptance even for an older server response', async () => {
    axios.post.mockResolvedValue({ data: { verification_status: 'found', new_count: 1 } });
    render(<TestBookingVerification />);
    fireEvent.click(screen.getByTestId('test-booking-verify-btn'));
    await screen.findByText('Rezervasyon bulundu — tam kabul bekliyor');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not silently coerce fractional child ages or send expectations without an ID', async () => {
    render(<TestBookingVerification />);
    fireEvent.change(screen.getByLabelText('Beklenen yetişkin sayısı (isteğe bağlı)'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Beklenen çocuk yaşları'), { target: { value: '6.5' } });
    fireEvent.click(screen.getByTestId('test-booking-verify-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(axios.post).not.toHaveBeenCalled();
  });
});
