import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ExelyReadReservationSettings from '../ExelyReadReservationSettings';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const connection = { id: 'conn-a', hotel_code: '501694', mode: 'sandbox', read_reservation_enabled: false };

beforeEach(() => vi.clearAllMocks());

function mount(enabled = false) {
  const onChanged = vi.fn();
  render(<ExelyReadReservationSettings connection={{ ...connection, read_reservation_enabled: enabled }} requestConfig={{}} onChanged={onChanged} />);
  return onChanged;
}

describe('Exely REST read-only setup and reconciliation', () => {
  it('requires explicit scoped storage consent and clears credentials after setup without claiming a PMS correction', async () => {
    post.mockResolvedValue({ data: { success: true, enabled: true, applied: false, rooms: [{ adults: 2, children_ages: [6] }] } });
    const onChanged = mount();
    const save = screen.getByRole('button', { name: 'Okuma bağlantısını doğrula ve kaydet' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Read Reservation client_id'), { target: { value: 'synthetic-client' } });
    fireEvent.change(screen.getByLabelText('Read Reservation client_secret'), { target: { value: 'synthetic-secret' } });
    fireEvent.change(screen.getByLabelText('Doğrulanacak mevcut Exely rezervasyon numarası'), { target: { value: 'synthetic-booking' } });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/channel-manager/exely/read-reservation/connect', {
      client_id: 'synthetic-client', client_secret: 'synthetic-secret', reservation_id: 'synthetic-booking', confirmation: 'ENABLE_READ_RESERVATION:501694',
      test_read_only_consent: 'ALLOW_TEST_READ:501694',
    }, {}));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.getByLabelText('Read Reservation client_secret')).toHaveValue('');
    expect(screen.getByLabelText('Read Reservation client_id')).toHaveValue('');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('status')).toHaveTextContent('PMS kaydı henüz değiştirilmedi');
    expect(screen.getByRole('status')).toHaveTextContent('2 yetişkin · 1 çocuk · yaşlar: 6');
  });

  it('reconciles only an exact entered reservation and shows a readback-verified result', async () => {
    post.mockResolvedValue({ data: { success: true, status: 'verified', rooms: [{ booking_id: 'booking-a', adults: 2, children_ages: [6] }] } });
    mount(true);
    const apply = screen.getByRole('button', { name: 'Kişi ayrımını doğrula ve düzelt' });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Doğrulanacak mevcut Exely rezervasyon numarası'), { target: { value: 'synthetic-booking' } });
    fireEvent.click(apply);
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('tekrar okunarak doğrulandı'));
    expect(post).toHaveBeenCalledWith('/channel-manager/exely/read-reservation/reconcile', { reservation_id: 'synthetic-booking' }, {});
    expect(screen.queryByLabelText('Read Reservation client_secret')).not.toBeInTheDocument();
  });

  it('does not expose arbitrary provider errors, request data or credentials on failure', async () => {
    post.mockRejectedValue({ response: { data: { detail: 'synthetic-secret https://vendor.invalid/token' } } });
    mount(true);
    fireEvent.change(screen.getByLabelText('Doğrulanacak mevcut Exely rezervasyon numarası'), { target: { value: 'synthetic-booking' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kişi ayrımını doğrula ve düzelt' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('EXELY_READ_OPERATION_FAILED'));
    expect(screen.queryByText(/synthetic-secret/)).not.toBeInTheDocument();
    expect(screen.queryByText(/https:\/\/vendor.invalid/)).not.toBeInTheDocument();
  });

  it('can pause automation without deleting credentials or touching SOAP/ARI settings', async () => {
    post.mockResolvedValue({ data: { success: true, enabled: false } });
    mount(true);
    fireEvent.click(screen.getByRole('button', { name: 'Otomatik kişi doğrulamasını durdur' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('durduruldu'));
    expect(post).toHaveBeenCalledExactlyOnceWith('/channel-manager/exely/read-reservation/pause', {}, {});
  });
});
