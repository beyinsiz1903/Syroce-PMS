import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencyBookingWidget from '../AgencyBookingWidget';
import apiErrorText from '@/utils/apiErrorText';

vi.mock('axios', () => ({ default: { create: vi.fn() } }));

const hotel = {
  tenant_id: 'hotel-1', hotel_name: 'Test Hotel', city: 'İstanbul', currency: 'EUR',
  available_room_types: [{ room_type: 'Standard', rate_plan_code: 'BB', meal_plan: 'BB', capacity: 2, available_rooms: 1, total_price: 100, nights: 1, currency: 'EUR' }],
};
let client;

beforeEach(() => {
  window.history.replaceState({}, '', '/agency-widget?key=test-public-token');
  Object.defineProperty(document, 'referrer', { configurable: true, value: 'https://agency.example/reservations' });
  client = { get: vi.fn().mockResolvedValue({ data: { agency: { name: 'Test Travel' } } }), post: vi.fn() };
  axios.create.mockReturnValue(client);
});
afterEach(cleanup);

async function openReservation() {
  client.post.mockResolvedValueOnce({ data: { results: [hotel] } });
  render(<AgencyBookingWidget />);
  const search = await screen.findByRole('button', { name: 'Uygun tesisleri ara' });
  await waitFor(() => expect(search).toBeEnabled());
  fireEvent.click(search);
  fireEvent.click(await screen.findByRole('button', { name: 'Rezervasyon yap' }));
  fireEvent.change(screen.getByLabelText('Ad soyad *'), { target: { value: 'Test Guest' } });
}

describe('agency website booking form', () => {
  it.each(['', 'guest@example.com'])('submits an optional email safely: %j', async email => {
    await openReservation();
    fireEvent.change(screen.getByLabelText('E-posta'), { target: { value: email } });
    client.post.mockResolvedValueOnce({ data: { reservation: { confirmation_code: 'TEST-BOOKING' } } });
    fireEvent.click(screen.getByRole('button', { name: 'Rezervasyonu onayla' }));
    expect(await screen.findByText('TEST-BOOKING')).toBeInTheDocument();
    expect(client.post).toHaveBeenLastCalledWith('/marketplace/v1/widget/reservations', expect.objectContaining({
      guest_email: email || null, guest_name: 'Test Guest', rate_plan_code: 'BB', total_amount: 100,
      idempotency_key: expect.any(String),
    }));
    expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({
      headers: { 'X-Widget-Token': 'test-public-token', 'X-Widget-Origin': 'https://agency.example' },
    }));
  });

  it('renders validation details without crashing and reuses the retry key', async () => {
    await openReservation();
    client.post.mockRejectedValueOnce({ response: { data: { detail: [{ loc: ['body', 'guest_email'], msg: 'Geçerli e-posta girin', type: 'value_error' }] } } });
    fireEvent.click(screen.getByRole('button', { name: 'Rezervasyonu onayla' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Geçerli e-posta girin');
    expect(screen.getByRole('alert').closest('form')).toContainElement(screen.getByLabelText('Ad soyad *'));
    const firstKey = client.post.mock.calls.at(-1)[1].idempotency_key;
    client.post.mockResolvedValueOnce({ data: { reservation: { confirmation_code: 'RETRY-OK' } } });
    fireEvent.click(screen.getByRole('button', { name: 'Rezervasyonu onayla' }));
    expect(await screen.findByText('RETRY-OK')).toBeInTheDocument();
    expect(client.post.mock.calls.at(-1)[1].idempotency_key).toBe(firstKey);
  });

  it('renders structured search failures as text', async () => {
    client.post.mockRejectedValueOnce({ response: { data: { detail: { error_code: 'agency_rate_not_shared', message: 'Paylaşılmış fiyat yok' } } } });
    render(<AgencyBookingWidget />);
    const search = screen.getByRole('button', { name: 'Uygun tesisleri ara' });
    await waitFor(() => expect(search).toBeEnabled());
    fireEvent.click(search);
    expect(await screen.findByRole('alert')).toHaveTextContent('Paylaşılmış fiyat yok');
  });

  it('renders structured configuration failures as text', async () => {
    client.get.mockRejectedValueOnce({ response: { data: { detail: { message: 'Web sitesi izni yok' } } } });
    render(<AgencyBookingWidget />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Web sitesi izni yok');
    expect(screen.getByRole('button', { name: 'Uygun tesisleri ara' })).toBeDisabled();
  });
});

describe('widget error text', () => {
  it.each([
    ['Fiyat değişti', 'Fiyat değişti'],
    [[{ msg: 'İlk hata' }, { msg: 'İkinci hata' }], 'İlk hata · İkinci hata'],
    [{ message: 'İzin verilmedi' }, 'İzin verilmedi'],
    [{ error_code: 'unknown' }, 'İşlem tamamlanamadı'],
    [null, 'İşlem tamamlanamadı'],
  ])('safely handles %j', (detail, expected) => {
    expect(apiErrorText({ response: { data: { detail } } }, 'İşlem tamamlanamadı')).toBe(expected);
  });
});
